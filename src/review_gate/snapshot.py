import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess

CAP = 128 * 1024
FILE_CAP = 8 * 1024 * 1024
GENERATED = {"uv.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
             "poetry.lock", "Cargo.lock", "Gemfile.lock", "composer.lock"}
SECRET = re.compile(
    rb"-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:gh[pousr]_[A-Za-z0-9]{20,}|"
    rb"AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{20,})\b|"
    rb"(?i:(?:api[_-]?key|password|secret|token)\s*[:=]\s*['\"][^'\r\n\"]{8,}['\"])"
)


class GateError(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    parts = PurePosixPath(name).parts
    if not parts or name.startswith("/") or any(
        part.lower() in {"..", ".git"} or part.lower().startswith(".env")
        or part.lower() in {"id_rsa", "id_ed25519", "credentials.json", "auth.json"}
        or part.lower().endswith((".pem", ".p12", ".key"))
        for part in parts
    ) or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise GateError("Unsafe or secret-sensitive input path")
    return parts


def scan(data):
    if SECRET.search(data):
        raise GateError("Possible secret in review input")


def read_file(root, name, missing=False):
    parts = safe_name(name)
    directory = os.open(root, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise GateError("Review input must be a regular file")
            data = stream.read(FILE_CAP + 1)
            after = os.fstat(stream.fileno())
            if fingerprint(before) != fingerprint(after):
                raise GateError("Review input changed during capture")
        if len(data) > FILE_CAP:
            raise GateError("Review file exceeds the capture limit")
        scan(data)
        mode = "100755" if before.st_mode & stat.S_IXUSR else "100644"
        return data, mode, fingerprint(before)
    except FileNotFoundError:
        if missing:
            return None
        raise GateError("Review input file was not found") from None
    except OSError:
        raise GateError("Could not safely open review input") from None
    finally:
        os.close(directory)


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def git(root, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
               GIT_NO_LAZY_FETCH="1", GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.devnull)
    result = subprocess.run(
        ["git", "--no-pager", "-c", "core.fsmonitor=false", "-C", str(root), *args],
        env=env, capture_output=True, timeout=30,
    )
    if result.returncode:
        raise GateError("Git could not inspect the selected repository or base")
    return result.stdout


def names(data):
    return {entry.decode("utf-8") for entry in data.split(b"\0") if entry}


def state(root, base):
    common = ("--no-ext-diff", "--no-textconv", "--no-renames",
              "--ignore-submodules=none", "--name-only", "-z")
    index = git(root, "ls-files", "--stage", "-z")
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    staged = git(root, "diff", "--cached", *common, base, "--")
    unstaged = git(root, "diff", *common, "--")
    return index, untracked, staged, unstaged


def metadata(raw, tree=False):
    result = {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        header, path = row.split(b"\t", 1)
        mode, second, third = header.decode("ascii").split()
        if not tree and third != "0":
            raise GateError("Resolve unmerged index entries before review")
        result[path.decode("utf-8")] = (mode, third if tree else second)
    return result


def base_file(root, entry):
    if not entry:
        return None
    mode, oid = entry
    if mode not in {"100644", "100755"}:
        raise GateError("Changed symlinks and submodules require manual review")
    if int(git(root, "cat-file", "-s", oid)) > FILE_CAP:
        raise GateError("Base file exceeds the capture limit")
    data = git(root, "cat-file", "blob", oid)
    scan(data)
    return data, mode


def document(root, name, side):
    data, _, stamp = read_file(root, name)
    if b"\0" in data:
        raise GateError("Plan and context inputs must be UTF-8 text")
    return {"path": name, "side": side, "text": data.decode("utf-8")}, stamp


def describe(version):
    if version is None:
        return None
    data, mode = version[:2]
    return {"size": len(data), "sha256": digest(data), "mode": mode}


def change(path, old, current, index_entry, staged, unstaged):
    before, after = describe(old), describe(current)
    masked = before == after and staged
    result = {"path": path, "base": before, "worktree": after,
              "staged": staged, "unstaged": unstaged, "masked_staged": masked,
              "index_oid": index_entry[1] if index_entry else None}
    if masked:
        return result | {"omitted": "masked staged change"}
    data = [entry[0] if entry else b"" for entry in (old, current)]
    if PurePosixPath(path).name in GENERATED:
        return result | {"omitted": "generated lockfile"}
    try:
        lines = [item.decode("utf-8").splitlines(keepends=True) for item in data]
    except UnicodeDecodeError:
        return result | {"omitted": "binary or non-UTF-8"}
    if any(b"\0" in item for item in data):
        return result | {"omitted": "binary"}
    result["patch"] = list(difflib.unified_diff(*lines, fromfile="base", tofile="worktree"))
    result["line_counts"] = {"base": len(lines[0]), "worktree": len(lines[1])}
    return result


def diff_packet(root, base_ref):
    base = git(root, "rev-parse", "--verify", "--end-of-options",
               base_ref + "^{commit}").decode("ascii").strip()
    config = git(root, "config", "--null", "--name-only", "--list")
    if any(key.startswith(b"filter.") for key in config.split(b"\0")):
        raise GateError("Custom Git content filters require manual review")
    flags = git(root, "ls-files", "-v", "-z")
    if any(row and (row[:1] == b"S" or row[:1].islower()) for row in flags.split(b"\0")):
        raise GateError("Sparse or assume-unchanged worktrees require manual review")
    initial = state(root, base)
    index, untracked, staged, unstaged = initial
    index = metadata(index)
    staged, unstaged = names(staged), names(unstaged)
    tree = metadata(git(root, "ls-tree", "-r", "-z", base), tree=True)
    paths = staged | unstaged | names(untracked)
    changes = []
    captured = {}
    for path in sorted(paths):
        safe_name(path)
        entry = index.get(path)
        if entry and entry[0] not in {"100644", "100755"}:
            raise GateError("Changed symlinks and submodules require manual review")
        old = base_file(root, tree.get(path))
        current = read_file(root, path, missing=True)
        captured[path] = describe(current), current[2] if current else None
        if describe(old) != describe(current) or path in staged:
            changes.append(change(path, old, current, entry, path in staged, path in unstaged))
    def recheck():
        if state(root, base) != initial:
            raise GateError("Git state changed during capture")
        for path, expected in captured.items():
            current = read_file(root, path, missing=True)
            if (describe(current), current[2] if current else None) != expected:
                raise GateError("Worktree changed during capture")
    return base, changes, recheck


def repository_root(cwd, *, required=False):
    try:
        return Path(os.fsdecode(git(cwd, "rev-parse", "--show-toplevel").rstrip(b"\n"))).resolve()
    except GateError:
        if required:
            raise
        return cwd


def capture(args, cwd):
    root = repository_root(cwd, required=args.phase == "diff" or bool(getattr(args, "context", [])))
    task_path = Path(os.path.abspath(cwd / args.task))
    task_root = Path(task_path.anchor)
    task_name = str(task_path.relative_to(task_root))
    task, task_stamp = document(task_root, task_name, "task")
    task["path"] = "task"
    packet = {"version": 1, "phase": args.phase, "documents": [task]}
    checks = [(task_root, task_name, task_stamp)]
    if args.phase == "plan":
        plan_path = Path(os.path.abspath(cwd / args.plan))
        plan_root = Path(plan_path.anchor)
        plan_name = str(plan_path.relative_to(plan_root))
        plan, stamp = document(plan_root, plan_name, "plan")
        plan["path"] = "plan"
        packet["documents"].append(plan)
        checks.append((plan_root, plan_name, stamp))
        for name in sorted(set(args.context)):
            context, stamp = document(root, name, "context")
            packet["documents"].append(context)
            checks.append((root, name, stamp))
    else:
        base, changes, recheck = diff_packet(root, args.base)
        packet.update(base=base, changes=changes)
        recheck()
    for directory, name, stamp in checks:
        if read_file(directory, name)[2] != stamp:
            raise GateError("Review documents changed during capture")
    encoded = json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > CAP:
        raise GateError("Review packet exceeds the 128 KiB limit")
    return root, packet, encoded
