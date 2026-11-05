from dataclasses import dataclass
import os
from pathlib import Path
import tomllib

from .snapshot import GateError

PRIMARY = {"codex": "openai", "antigravity": "gemini", "claude": "claude", "opencode": None}
ADAPTERS = {"codex", "agy", "claude", "opencode"}


@dataclass(frozen=True)
class Reviewer:
    name: str
    adapter: str
    service: str
    family: str
    model: str
    binary: str
    version: str


def absolute(value):
    return isinstance(value, str) and Path(value).is_absolute()


def config_path(path, root):
    path = path.expanduser().resolve()
    if path.is_relative_to(root.resolve()):
        raise GateError("Reviewer configuration must be outside the reviewed repository")
    return path


def read_config(path):
    if not path.is_file():
        raise GateError("Reviewer config is missing. Run review-gate setup first.")
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o022:
        raise GateError("Reviewer configuration must be user-owned and private from edits")
    with path.open("rb") as source:
        return tomllib.load(source)


def route_reviewers(config, root, family):
    try:
        names = config["routes"][family]
        if not isinstance(names, list) or len(names) != 2:
            raise GateError("Configure exactly two reviewers")
        if config.get("mode") != "native" or "launcher" in config:
            raise GateError("Set mode = 'native' and remove legacy launcher and profile fields")
        reviewers = [Reviewer(name, **config["reviewers"][name]) for name in names]
        for reviewer in reviewers:
            if (reviewer.adapter not in ADAPTERS or not absolute(reviewer.binary)
                    or Path(reviewer.binary).resolve().is_relative_to(root)
                    or not Path(reviewer.binary).is_file()
                    or not os.access(reviewer.binary, os.X_OK)
                    or not all(isinstance(value, str) and value and not value.startswith("-")
                               for value in (reviewer.name, reviewer.service,
                                             reviewer.family, reviewer.model, reviewer.version))):
                raise GateError("Invalid reviewer configuration")
            if reviewer.adapter == "opencode" and not reviewer.model.startswith("opencode-go/"):
                raise GateError("OpenCode profiles must pin an OpenCode Go model")
        if len({family.casefold(), *(reviewer.family.casefold() for reviewer in reviewers)}) != 3:
            raise GateError("The primary and both reviewers must use distinct model families")
        return reviewers
    except (KeyError, TypeError, AttributeError) as exc:
        raise GateError("Missing or invalid reviewer routes or profiles. Run review-gate setup.") from exc


def approved_services(config, root):
    approvals = config.get("approved_services", {})
    if not hasattr(approvals, "get"):
        raise GateError("Approved services must be a table of repository paths")
    approved = approvals.get(str(root.resolve()), [])
    if not isinstance(approved, list) or not all(isinstance(service, str) for service in approved):
        raise GateError("Repository approvals must be a list of service names")
    return set(approved)


def primary_family(config, primary, family):
    if family is None:
        saved = config.get("default_primary")
        primary = primary or saved
        if not isinstance(primary, str) or primary not in PRIMARY:
            raise GateError("Choose a coding harness with --primary or save one with review-gate setup")
        if primary == saved:
            family = config.get("default_primary_family")
        if family is None:
            family = PRIMARY[primary]
        if family is None:
            raise GateError("OpenCode requires --primary-family with the family of its active model")
    if not isinstance(family, str) or not family or family.startswith("-") or any(
        char.isspace() for char in family
    ):
        raise GateError("Specify a valid model family with --primary-family")
    return family


def load(path, root, family=None, *, primary=None):
    config = read_config(config_path(path, root))
    family = primary_family(config, primary, family)
    reviewers = route_reviewers(config, root, family)
    approved = approved_services(config, root)
    required = {r.service for r in reviewers}
    if not required.issubset(approved):
        raise GateError("Approve this repository first. See review-gate setup --help. "
                        f"Required services: {', '.join(sorted(required))}")
    return reviewers
