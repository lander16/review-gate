# Agent-assisted Review Gate setup

Use this runbook when the user asks you to set up Review Gate. Keep install status and live review readiness separate.

1. Identify the primary harness, project or personal skill scope, and target repository. Use the install instructions in [README.md](README.md). Check for an existing skill before replacing files. Verify `review-gate plan --help` and `review-gate diff --help` from the shell the agent will use.
2. Inventory installed runners with `command -v` and their `--version` commands. Use `agy models` or `opencode models opencode-go` where available to identify candidates. Confirm exact model IDs through the isolated profiles during qualification. Select two different model families other than the primary. Claude Code and OpenCode are optional. Two independently launched `agy` profiles can use different families.
3. Draft a TOML file from [config.example.toml](config.example.toml) outside the repository. Preserve existing routes and approval entries. Use absolute paths and distinct state profiles. Keep the config private. Leave `approved_services` empty for new real repositories until the user explicitly approves each recipient service. Keep credentials in their dedicated profiles.
4. Check that an isolation launcher has been independently qualified under the contract in the README. If one is missing or either profile requires interactive sign-in, report those prerequisites and keep the configuration as a draft. Avoid reusing the main agent's profile or bypassing isolation to get a test to pass.
5. Once the launcher and profiles are ready, create a temporary directory for synthetic task and plan files. Use a separate smoke config whose only approval is the synthetic directory's absolute path. Run the command below with the real primary harness and a private report directory outside the synthetic directory. A valid result from each reviewer qualifies the adapter and model pair for synthetic review. Inspect the report to distinguish a review finding from a failed run.
6. After qualification and explicit approval for the target repository and services, write or update `~/.config/review-gate/config.toml`. Summarize the installed skill path, the selected route, and any remaining prerequisites.

```sh
review-gate plan --task task.md --plan plan.md --primary codex \
  --config /absolute/path/to/smoke-config.toml \
  --reports /absolute/path/to/private-smoke-reports
```

For the smoke test, use a task such as “Add two integers and support negative inputs” and a plan such as “Return the sum and test zero and negative values.” Run the command from the synthetic directory.
