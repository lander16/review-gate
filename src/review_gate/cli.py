import argparse
from pathlib import Path
import subprocess
import sys

from .config import PRIMARY, load
from .report import exit_code, private_directory, write_report
from .runners import review
from .setup import configure
from .snapshot import GateError, capture, digest


def parser():
    default = Path.home() / ".config" / "review-gate"
    cli = argparse.ArgumentParser(description="Run an independent plan or code review round")
    commands = cli.add_subparsers(dest="phase", required=True)
    plan = commands.add_parser("plan", help="Review a proposed implementation plan")
    diff = commands.add_parser("diff", help="Review worktree changes relative to a base commit")
    setup = commands.add_parser("setup", help="Configure a default harness and approve services")
    for command in (plan, diff, setup):
        command.add_argument("--primary", choices=PRIMARY, help="primary coding harness")
        command.add_argument("--primary-family", help="family of the active model, required for OpenCode on first setup")
        command.add_argument("--config", type=Path, default=default / "config.toml")
    for command in (plan, diff):
        command.add_argument("--task", type=Path, default=Path("task.md"),
                             help="task file relative to this directory (default: task.md)")
        command.add_argument("--reports", type=Path, default=default / "runs")
    plan_path = plan.add_mutually_exclusive_group(required=True)
    plan_path.add_argument("file", nargs="?", type=Path, help="proposed plan file")
    plan_path.add_argument("--plan", type=Path, help="proposed plan file (named form)")
    plan.add_argument("--context", action="append", default=[], metavar="PATH")
    diff.add_argument("--base", default="HEAD", help="comparison commit (default: HEAD)")
    setup.add_argument("--allow", action="append", default=[], metavar="SERVICE",
                       help="approve this repository for the named reviewer service (repeatable)")
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    root = Path.cwd().resolve()
    if args.phase == "setup":
        try:
            configure(args, root)
            return 0
        except (GateError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"Setup failed: {exc}", file=sys.stderr)
            return 2
    if args.phase == "plan":
        args.plan = args.plan or args.file
    packet = {"phase": args.phase}
    reviewers, results = [], []
    packet_hash = None
    error = None
    code = 2
    try:
        root, packet, packet_bytes = capture(args, root)
        packet_hash = digest(packet_bytes)
        reviewers = load(args.config, root, args.primary_family, primary=args.primary)
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
