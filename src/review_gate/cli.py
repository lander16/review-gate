import argparse
from pathlib import Path
import subprocess
import sys

from .config import PRIMARY, load
from .report import exit_code, private_directory, write_report
from .runners import review
from .snapshot import GateError, capture, digest


def parser():
    default = Path.home() / ".config" / "review-gate"
    cli = argparse.ArgumentParser(description="Run an independent plan or code review round")
    commands = cli.add_subparsers(dest="phase", required=True)
    plan = commands.add_parser("plan", help="Review a proposed implementation plan")
    diff = commands.add_parser("diff", help="Review worktree changes relative to a base commit")
    for command in (plan, diff):
        command.add_argument("--task", required=True, type=Path)
        command.add_argument("--primary", required=True, choices=PRIMARY)
        command.add_argument("--primary-family")
        command.add_argument("--config", type=Path, default=default / "config.toml")
        command.add_argument("--reports", type=Path, default=default / "runs")
    plan.add_argument("--plan", required=True, type=Path)
    plan.add_argument("--context", action="append", default=[])
    diff.add_argument("--base", required=True)
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    root = Path.cwd().resolve()
    packet = {"phase": args.phase}
    reviewers, results = [], []
    packet_hash = None
    error = None
    code = 2
    try:
        root, packet, packet_bytes = capture(args, root)
        packet_hash = digest(packet_bytes)
        reviewers = load(args.config, root, args.primary_family or PRIMARY[args.primary])
        private_directory(args.reports, root)
        results = review(reviewers, packet, packet_bytes)
        code = exit_code(results)
        if code == 0 and any(item.get("masked_staged") for item in packet.get("changes", [])):
            code = 1
    except GateError as exc:
        error = str(exc)
    except FileNotFoundError:
        error = "Reviewer config, input, or executable is missing"
    except KeyboardInterrupt:
        error = "Review cancelled"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        error = "Could not read a review input, configuration, or Git response"
    if error:
        print(error, file=sys.stderr)
    try:
        path = write_report(args.reports, root, packet, packet_hash,
                            reviewers, results, code, error)
    except (GateError, OSError) as exc:
        print(f"Could not save private report: {exc}", file=sys.stderr)
        return 2
    print(path)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
