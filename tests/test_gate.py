import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from review_gate.cli import main
from review_gate.runners import normalize, run_process, validate, visible_lines
from review_gate.snapshot import GateError, capture
from review_gate.cli import parser


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def repo(tmp_path):
    root = (tmp_path / "repo").resolve()
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Review Gate Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "task.md").write_text("Fix the behavior.\n")
    (root / "plan.md").write_text("Update the implementation and tests.\n")
    (root / "existing.py").write_text("old = 1\n")
    (root / "deleted.py").write_text("gone = True\n")
    (root / ".gitignore").write_text("ignored*\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    return root


def args(*values):
    return parser().parse_args([*values, "--task", "task.md", "--primary", "codex"])


def test_plan_context(repo):
    _, packet, encoded = capture(args("plan", "--plan", "plan.md", "--context", "existing.py"), repo)
    assert json.loads(encoded) == packet
    assert [doc["side"] for doc in packet["documents"]] == ["task", "plan", "context"]
    assert packet["documents"][2]["text"] == "old = 1\n"


def test_diff_covers_effective_worktree(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "committed.py").write_text("committed = True\n")
    git(repo, "add", "committed.py")
    git(repo, "commit", "-qm", "branch change")
    (repo / "added.py").write_text("staged = True\n")
    git(repo, "add", "added.py")
    (repo / "existing.py").write_text("new = 2\n")
    (repo / "deleted.py").unlink()
    (repo / "untracked.py").write_text("untracked = True\n")
    (repo / "ignored.py").write_text("ignored = True\n")
    (repo / "logo.png").write_bytes(b"\x00PNG")
    (repo / "uv.lock").write_text("lock content\n")
    before = (repo / ".git/index").read_bytes()
    _, packet, _ = capture(args("diff", "--base", base), repo)
    changes = {change["path"]: change for change in packet["changes"]}
    assert set(changes) == {"committed.py", "added.py", "existing.py", "deleted.py",
                            "untracked.py", "logo.png", "uv.lock"}
    assert changes["existing.py"]["patch"][-2:] == ["-old = 1\n", "+new = 2\n"]
    assert changes["deleted.py"]["worktree"] is None
    assert changes["logo.png"]["omitted"] == "binary"
    assert changes["uv.lock"]["omitted"] == "generated lockfile"
    assert (repo / ".git/index").read_bytes() == before


def test_masked_staged_change(repo):
    path = repo / "existing.py"
    path.write_text("staged = 2\n")
    git(repo, "add", path.name)
    path.write_text("old = 1\n")
    _, packet, _ = capture(args("diff", "--base", "HEAD"), repo)
    assert packet["changes"][0]["masked_staged"]


@pytest.mark.parametrize("unsafe", ["symlink", "secret", "deleted_secret"])
def test_unsafe_input(repo, unsafe):
    if unsafe == "symlink":
        (repo / "symlink.py").symlink_to("/etc/passwd")
    elif unsafe == "secret":
        (repo / ".env.local").write_text("password=hidden\n")
    else:
        path = repo / "existing.py"
        path.write_text('password = "synthetic-12345"\n')
        git(repo, "add", path.name)
        git(repo, "commit", "-qm", "synthetic secret fixture")
        path.unlink()
    with pytest.raises(GateError):
        capture(args("diff", "--base", "HEAD"), repo)


def test_snapshot_rejects_capture_race(repo, monkeypatch):
    from review_gate import snapshot
    path = repo / "new.py"
    path.write_text("before\n")
    original = snapshot.read_file
    calls = 0

    def mutate(root, name, missing=False):
        nonlocal calls
        if name == path.name:
            calls += 1
            if calls == 2:
                path.write_text("after\n")
        return original(root, name, missing)

    monkeypatch.setattr(snapshot, "read_file", mutate)
    with pytest.raises(GateError, match="changed"):
        capture(args("diff", "--base", "HEAD"), repo)


@pytest.fixture
def launch(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    home = root / "user-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    fake = root / "reviewer"
    fake.write_text(f"#!{sys.executable}\n" + '''
import hashlib
import json
from pathlib import Path
import sys
import time

if sys.argv[-1] == "--version":
    print("fake 1.0")
    raise SystemExit
import os

profile = sys.argv[sys.argv.index("--model") + 1]
assert Path.home() == Path(__file__).parent / "user-home"
assert Path.cwd() != Path.home()
assert os.environ["AGY_CLI_DISABLE_AUTO_UPDATE"] == "true"
assert Path(sys.argv[sys.argv.index("--log-file") + 1]).parent.resolve() == Path.cwd()
settings = json.loads(sys.argv[sys.argv.index("--settings") + 1])
assert "command(*)" in settings["permissions"]["deny"]
packet = sys.stdin.buffer.read()
peers = Path(__file__).parent
(peers / (profile + ".ready")).touch()
deadline = time.monotonic() + 3
while len(list(peers.glob("*.ready"))) != 2:
    if time.monotonic() > deadline:
        raise SystemExit(3)
    time.sleep(0.01)
if profile == "bad":
    print(json.dumps({"event": "result", "result": {"status": "ERROR"}}))
    raise SystemExit
finding = {
    "severity": "blocker" if profile == "block" else "advisory",
    "title": hashlib.sha256(packet).hexdigest(),
    "consequence": "Synthetic finding",
    "evidence": {"path": "task", "side": "task", "start": 1, "end": 1},
}
result = {"status": "SUCCESS", "structured_output": {"findings": [finding], "limitations": []}}
print(json.dumps({"event": "result", "result": result}))
''')
    fake.chmod(0o700)
    return fake


def configure(repo, launch, second):
    config = launch.with_name("config.toml")
    config.write_text(f'''
mode = "native"
[routes]
openai = ["a", "b"]
[approved_services]
{json.dumps(str(repo))} = ["antigravity"]
[reviewers.a]
adapter = "agy"
service = "antigravity"
family = "gemini"
model = "first"
binary = {json.dumps(str(launch))}
version = "1.0"
[reviewers.b]
adapter = "agy"
service = "antigravity"
family = "claude"
model = {json.dumps(second)}
binary = {json.dumps(str(launch))}
version = "1.0"
''')
    return config


@pytest.mark.parametrize(("second", "expected"), [("second", 0), ("block", 1), ("bad", 2)])
def test_cli_parallel_identical_packets_and_partial_failure(repo, launch, second, expected, monkeypatch):
    monkeypatch.chdir(repo)
    config = configure(repo, launch, second)
    reports = launch.with_name("reports")
    code = main(["plan", "--task", "task.md", "--plan", "plan.md", "--primary", "codex",
                 "--config", str(config), "--reports", str(reports)])
    assert code == expected
    report = json.loads(next(reports.glob("*/report.json")).read_text())
    first, other = report["reviewers"]
    assert first["status"] == "ok"
    if second == "bad":
        assert other["status"] == "error"
    else:
        assert first["result"]["findings"][0]["title"] == other["result"]["findings"][0]["title"]


def test_cli_diff(repo, launch, monkeypatch):
    monkeypatch.chdir(repo)
    (repo / "existing.py").write_text("changed = 42\n")
    config = configure(repo, launch, "second")
    reports = launch.with_name("reports")
    assert main(["diff", "--task", "task.md", "--base", "HEAD", "--primary", "codex",
                 "--config", str(config), "--reports", str(reports)]) == 0
    report = json.loads(next(reports.glob("*/report.json")).read_text())
    assert report["base"] == git(repo, "rev-parse", "HEAD")


def test_same_family_fails_before_launch(repo, launch, monkeypatch):
    monkeypatch.chdir(repo)
    config = configure(repo, launch, "second")
    config.write_text(config.read_text().replace('family = "claude"', 'family = "gemini"'))
    assert main(["plan", "--task", "task.md", "--plan", "plan.md", "--primary", "codex",
                 "--config", str(config), "--reports", str(launch.with_name("reports"))]) == 2
    assert not list(launch.parent.glob("*.ready"))


def test_timeout(tmp_path):
    start = time.monotonic()
    with pytest.raises(GateError, match="timed out"):
        run_process([sys.executable, "-c", "import time; time.sleep(60)"],
                    b"", tmp_path, timeout=0.15)
    assert time.monotonic() - start < 3


def test_output_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("review_gate.runners.OUTPUT_CAP", 1024)
    with pytest.raises(GateError, match="output limit"):
        run_process([sys.executable, "-c", "print('x' * 10000)"], b"", tmp_path)


def test_invalid_anchor(repo):
    _, packet, _ = capture(args("plan", "--plan", "plan.md"), repo)
    payload = {"limitations": [], "findings": [{
        "severity": "blocker", "title": "Invalid", "consequence": "A problem",
        "evidence": {"path": "task", "side": "task", "start": 2, "end": 2},
    }]}
    with pytest.raises(GateError, match="outside the packet"):
        validate(payload, visible_lines(packet))


def test_malformed_and_provider_error():
    with pytest.raises(ValueError):
        normalize("agy", b"{not JSON}", None)
    with pytest.raises(GateError):
        normalize("agy", b'{"event":"result","result":{"status":"ERROR"}}', None)


@pytest.mark.parametrize(("adapter", "stdout"), [
    ("agy", b'{"event":"result","result":{"status":"SUCCESS","structured_output":{"findings":[],"limitations":[]}}}'),
    ("claude", b'{"type":"result","subtype":"success","structured_output":{"findings":[],"limitations":[]}}'),
    ("opencode", b'{"type":"text","part":{"text":"{\\"findings\\":[],\\"limitations\\":[]}"}}\n'
                 b'{"type":"step_finish","part":{"reason":"stop"}}'),
    ("codex", b'{"type":"turn.completed"}'),
])
def test_normalize_adapter_contract(adapter, stdout, tmp_path):
    final = tmp_path / "final.json"
    final.write_text('{"findings":[],"limitations":[]}')
    payload, _ = normalize(adapter, stdout, final)
    assert payload == {"findings": [], "limitations": []}
