import json
import os
from pathlib import Path
import tempfile

from .snapshot import GateError


def exit_code(results):
    if any(result["status"] != "ok" for result in results):
        return 2
    for result in results:
        payload = result["result"]
        if (any(finding["severity"] == "blocker" for finding in payload["findings"])
                or any(item["material"] for item in payload["limitations"])):
            return 1
    return 0


def private_directory(parent, root):
    parent = parent.expanduser().resolve()
    if parent.is_relative_to(root.resolve()):
        raise GateError("Report directory must be outside the reviewed repository")
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o077:
        raise GateError("Report directory must be private (mode 0700)")
    return parent


def write_report(parent, root, packet, packet_hash, reviewers, results, code, error=None):
    parent = private_directory(parent, root)
    folder = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    public = [{"name": r.name, "adapter": r.adapter, "service": r.service,
               "family": r.family, "model": r.model, "version": r.version, "effort": r.effort}
              for r in reviewers]
    omissions = [{"path": change["path"], "reason": change["omitted"],
                  "base": change["base"], "worktree": change["worktree"]}
                 for change in packet.get("changes", []) if "omitted" in change]
    report = {"version": 1, "mode": "native", "phase": packet.get("phase"), "base": packet.get("base"),
              "packet_sha256": packet_hash, "exit_code": code, "error": error,
              "omissions": omissions, "reviewers": [
                  info | result for info, result in zip(public, results)
              ]}
    path = folder / "report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n")
    summary = [f"Review exit code {code}"]
    if error:
        summary.append(error)
    for item in report["reviewers"]:
        summary.append(f"{item['name']} ({item['family']} via {item['service']}): {item['status']}")
        if item["status"] != "ok":
            summary.append(f"  {item['reason']}")
            continue
        for finding in item["result"]["findings"]:
            anchor = finding["evidence"]
            summary.append(f"  {finding['severity']}: {finding['title']} "
                           f"({anchor['path']} {anchor['side']}:{anchor['start']})")
            summary.append(f"    {finding['consequence']}")
        for limit in item["result"]["limitations"]:
            summary.append(f"  Limitation (material={limit['material']}): {limit['description']}")
    for item in omissions:
        summary.append(f"Omitted {item['path']}: {item['reason']}")
    safe_summary = "".join(
        char if char in "\n\t" or char.isprintable() else ascii(char)[1:-1]
        for char in "\n".join(summary)
    )
    (folder / "summary.txt").write_text(safe_summary + "\n")
    return path
