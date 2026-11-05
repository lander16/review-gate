# Agent-assisted Review Gate setup

Use this runbook when the user asks you to set up Review Gate. Keep install status and live review readiness separate.

1. Identify the primary harness, project or personal skill scope, and target repository. Use the install instructions in [README.md](README.md). Check for an existing skill before replacing files. Verify `review-gate plan --help` and `review-gate diff --help` from the shell the agent will use.
2. Inventory the installed CLIs with `command -v` and their `--version` commands. Use `agy models` or `opencode models opencode-go` where available. For a Codex primary, start with one Gemini and one Claude model through `agy` when available. If a reviewer needs sign-in, ask the user to sign in through the CLI. Keep credential contents out of the chat and configuration.
3. Draft native TOML from [config.example.toml](config.example.toml) outside the reviewed repository. Pin executable paths, versions, services, and exact model IDs. Preserve existing routes and approval entries. Remove the legacy launcher and profile fields if migrating. Leave new real repositories unapproved until the user explicitly approves each service.
4. Create a temporary synthetic directory with task and plan files. Use a separate smoke config whose only approval is the synthetic directory's absolute path. Run the command below with the actual primary harness and a private report directory outside the synthetic directory. Inspect both reviewer results. A valid blocker is a review outcome, while a runner error means the setup needs attention.
5. After qualification, write or update `~/.config/review-gate/config.toml`. Record only the real repository/service approvals the user gave. Summarize the installed skill path, selected route, and any remaining prerequisites.

```sh
review-gate plan --task task.md --plan plan.md --primary codex \
  --config /absolute/path/to/smoke-config.toml \
  --reports /absolute/path/to/private-smoke-reports
```

For the smoke test, use a task such as “Add two integers and support negative inputs” and a plan such as “Return the sum and test zero and negative values.” Run the command from the synthetic directory.
