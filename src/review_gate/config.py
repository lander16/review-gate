from dataclasses import dataclass
import os
from pathlib import Path
import tomllib

from .snapshot import GateError

PRIMARY = {"codex": "openai", "antigravity": "gemini", "claude": "claude"}
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
    profile: str


def absolute(value):
    return isinstance(value, str) and Path(value).is_absolute()


def load(path, root, family):
    path = path.expanduser().resolve()
    if path.is_relative_to(root.resolve()):
        raise GateError("Reviewer configuration must be outside the reviewed repository")
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o022:
        raise GateError("Reviewer configuration must be user-owned and private from edits")
    with path.open("rb") as source:
        config = tomllib.load(source)
    try:
        names = config["routes"][family]
        launcher = config["launcher"]
        if (not absolute(launcher) or Path(launcher).resolve().is_relative_to(root)
                or not os.access(launcher, os.X_OK)):
            raise GateError("A qualified isolation launcher is required")
        if not isinstance(names, list) or len(names) != 2:
            raise GateError("Configure exactly two reviewers")
        reviewers = [Reviewer(name, **config["reviewers"][name]) for name in names]
        for reviewer in reviewers:
            if (reviewer.adapter not in ADAPTERS or not absolute(reviewer.binary)
                    or Path(reviewer.binary).resolve().is_relative_to(root)
                    or not all(isinstance(value, str) and value and not value.startswith("-")
                               for value in (reviewer.name, reviewer.profile, reviewer.service,
                                             reviewer.family, reviewer.model, reviewer.version))):
                raise GateError("Invalid reviewer configuration")
            if reviewer.adapter == "opencode" and not reviewer.model.startswith("opencode-go/"):
                raise GateError("OpenCode profiles must pin an OpenCode Go model")
        if len({family, *(reviewer.family for reviewer in reviewers)}) != 3:
            raise GateError("The primary and both reviewers must use distinct model families")
        if len({reviewer.profile for reviewer in reviewers}) != 2:
            raise GateError("Use separate isolated state profiles for both reviewers")
        approved = config.get("approved_services", {}).get(str(root.resolve()), [])
        if not isinstance(approved, list) or any(r.service not in approved for r in reviewers):
            raise GateError("Approve this repository for both reviewer services first")
        return launcher, reviewers
    except (KeyError, TypeError) as exc:
        raise GateError("Missing or invalid reviewer routes or profiles") from exc
