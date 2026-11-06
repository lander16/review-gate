import fcntl
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

import tomlkit

from .config import (
    PHASES, PRIMARY, approved_services, config_path, primary_family, read_config, route_reviewers,
)
from .runners import run_process
from .snapshot import GateError, repository_root

DEFAULT_MODELS = {
    "gemini": ("agy", "antigravity", "gemini-4-argon-medium"),
    "claude": ("agy", "antigravity", "claude-sonnet-5-5-medium"),
    "openai": ("codex", "openai", "gpt-6.1-sol"),
}
VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+][\w.-]+)?")


def save(path, config):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(tomlkit.dumps(config))
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def detect(adapter, root):
    found = shutil.which(adapter)
    if not found:
        raise GateError(f"Install {adapter} or configure a custom reviewer route")
    binary = Path(found).absolute()
    if binary.resolve().is_relative_to(root):
        raise GateError(f"The {adapter} executable must be outside the reviewed repository")
    with tempfile.TemporaryDirectory(prefix="review-gate-setup-") as temporary:
        directory = Path(temporary)
        stdout, stderr = run_process([str(binary), "--version"], b"", directory,
                                     timeout=15, extra_env={"HOME": temporary})
    version = next((token for token in (stdout + stderr).decode(errors="replace").split()
                    if VERSION.fullmatch(token)), None)
    if version is None:
        raise GateError(f"Could not detect the installed {adapter} version")
    return str(binary), version


def discover_reviewers(config, family, root):
    available = []
    failures = {}
    versions = {}
    reviewers = config.setdefault("reviewers", {})
    for other, (adapter, service, model) in DEFAULT_MODELS.items():
        if other == family.casefold():
            continue
        name = f"{other}-{adapter}"
        if name not in reviewers:
            if adapter in failures:
                continue
            if adapter not in versions:
                try:
                    versions[adapter] = detect(adapter, root)
                except GateError as exc:
                    failures[adapter] = str(exc)
                    continue
                except (OSError, subprocess.TimeoutExpired):
                    failures[adapter] = f"Could not run {adapter} --version"
                    continue
            binary, version = versions[adapter]
            reviewers[name] = dict(adapter=adapter, service=service, family=other,
                                   model=model, binary=binary, version=version)
        available.append(name)
        if len(available) == 2:
            break
    if not available:
        raise GateError("No eligible reviewer found. " + ". ".join(failures.values()))
    config["routes"].setdefault(family, available[:1])


def configure(args, cwd):
    root = repository_root(cwd)
    path = config_path(args.config, root)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.with_name(f".{path.name}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            read_config(path)
            config = tomlkit.parse(path.read_text(encoding="utf-8"))
        else:
            config = tomlkit.document()
            config["mode"] = "native"
        if config.get("mode") != "native" or "launcher" in config:
            raise GateError("Migrate the legacy config to native mode before running setup")
        primary = args.primary or config.get("default_primary")
        if not isinstance(primary, str) or primary not in PRIMARY:
            raise GateError("Choose your coding harness with --primary on first setup")
        family = primary_family(config, primary, args.primary_family)
        routes = config.setdefault("routes", {})
        route = routes.get(family)
        built_in_names = {f"{other}-{adapter}" for other, (adapter, _, _) in DEFAULT_MODELS.items()}
        if family not in routes or (
            isinstance(route, list) and len(route) == 1 and isinstance(route[0], str) and route[0] in built_in_names
        ):
            discover_reviewers(config, family, root)
        pairs = {phase: route_reviewers(config, root, family, phase) for phase in PHASES}
        required = {reviewer.service for pair in pairs.values() for reviewer in pair}
        allowed = set(args.allow)
        default_names = {reviewer.name for pair in pairs.values() for reviewer in pair}
        alternatives = []
        for name in config["reviewers"]:
            if name in default_names:
                continue
            try:
                alternatives.extend(route_reviewers(config, root, family, names=[name]))
            except GateError:
                continue
        available_services = required | {reviewer.service for reviewer in alternatives}
        if allowed and not required.issubset(allowed):
            raise GateError(f"Pass --allow for at least these services: {', '.join(sorted(required))}")
        if not allowed.issubset(available_services):
            raise GateError(f"No eligible reviewer profile for: {', '.join(sorted(allowed - available_services))}")
        config["default_primary"] = primary
        config["default_primary_family"] = family
        approvals = config.setdefault("approved_services", {})
        approved = approved_services(config, root) | allowed
        if allowed:
            approvals[str(root)] = sorted(approved)
        save(path, config)
    if pairs["plan"] == pairs["diff"]:
        pairs = {"plan and diff": pairs["plan"]}
    for phase, pair in pairs.items():
        print(f"{phase}:")
        for reviewer in pair:
            effort = f", effort {reviewer.effort}" if reviewer.effort else ""
            print(f"  {reviewer.name}: {reviewer.model} via {reviewer.service} "
                  f"({reviewer.adapter} {reviewer.version}{effort})")
    for reviewer in alternatives:
        effort = f", effort {reviewer.effort}" if reviewer.effort else ""
        print(f"Optional reviewer {reviewer.name}: {reviewer.model} via {reviewer.service}{effort}")
    print(f"Saved {path}")
    if not required.issubset(approved):
        flags = [flag for service in sorted(required) for flag in ("--allow", service)]
        command = ["review-gate", "setup", *flags]
        if args.config != Path.home() / ".config" / "review-gate" / "config.toml":
            command.extend(("--config", str(path)))
        print(f"To approve this directory, run {shlex.join(command)}")
    else:
        print(f"Approved for this directory: {', '.join(sorted(required))}")
