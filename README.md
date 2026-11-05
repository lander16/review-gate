# Review Gate

Run one independent cross-model review round for a plan or a Git change set.

```sh
review-gate plan --task docs/task.md --plan docs/plan.md --primary codex \
  --context src/session.py
review-gate diff --task docs/task.md --base origin/main --primary antigravity
```

The shared skill in `skills/review-gate/SKILL.md` describes the two checkpoints and how to reconcile findings. Use it inside your existing harness.

## Install the CLI and skill

Clone the private repository with an account that has access.

```sh
gh repo clone lander16/review-gate
cd review-gate
```

Use Python 3.11 or later. With `uv`, run `uv tool install .` from the checkout and make sure the tool directory is on the agent's PATH. To run the tests in a separate virtual environment, use `python3 -m venv .venv`, `.venv/bin/python -m pip install -e '.[test]'`, and `.venv/bin/python -m pytest -q`.

Copy the entire `skills/review-gate` folder to one of these skill directories. Project paths are relative to the repository where you want to use the skill.

| Harness | Project | Personal |
| --- | --- | --- |
| Codex Desktop / CLI | `.agents/skills/` | `~/.agents/skills/` |
| Antigravity IDE / `agy` | `.agents/skills/` | `~/.gemini/config/skills/` |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |

For example, from the Review Gate checkout, install the personal Codex skill with these commands.

```sh
mkdir -p "$HOME/.agents/skills"
cp -R skills/review-gate "$HOME/.agents/skills/"
review-gate --help
```

Check for an existing copy before replacing it. Start a new agent session if the skill is missing. Ask for `$review-gate` in Codex or `/review-gate` in Antigravity or Claude Code. See the official [Codex](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills), [Antigravity](https://antigravity.google/docs/skills), and [Claude Code](https://code.claude.com/docs/en/skills) skill guides.

## Agent-assisted setup

Open the checkout in your coding agent and give it this prompt:

> Set up Review Gate for my current coding harness. Follow [SETUP.md](SETUP.md), install the skill at the scope I choose, and configure my native reviewers. Use synthetic inputs for verification and tell me which sign-ins or provider approvals are still needed.

## Configure live reviewers

Review Gate calls your installed CLI binaries directly. Set `mode = "native"` in `~/.config/review-gate/config.toml` and start with [config.example.toml](config.example.toml). If you used the initial config template, remove its `launcher` and reviewer `profile` fields. Each route requires two reviewer families distinct from each other and from the primary.

For a Codex primary, sign in to Antigravity once and use two explicit `agy` models, one Gemini and one Claude. Run `agy models` to find the model IDs available to your account. The example routes both reviewers through Antigravity. Installing Claude Code is optional.

Native mode starts each review in a fresh working directory and applies the configured CLI tool controls. Antigravity and Claude Code use the normal login and OS keychain. Antigravity can load user-level configuration and write session state in its usual directories. Review Gate supplies per-run deny rules for file tools, shell commands, URLs, and MCP calls. Codex and OpenCode use temporary homes with copies of their standard local credential files. Sign in with the standard CLI profile first. Account, CLI version, and model availability can vary. Run a synthetic review after configuring or updating a route.

Native mode relies on each CLI's restrictions and does not provide an OS-level filesystem or network allowlist. Use it with trusted binaries and repositories you explicitly approve for the selected services. Keep the config and reports outside the reviewed repository. The optional stronger isolation design is tracked in [issue #1](https://github.com/lander16/review-gate/issues/1).

Use `codex`, `agy`, `claude`, or `opencode` for the adapter. OpenCode profiles pin an `opencode-go/<model-id>`. The service names track the destination receiving the packet. Family describes underlying model lineage. Approve each service under `approved_services` before sending repository content.

Exit 0 means two valid responses without reported blockers. Exit 1 means a reported blocker, material limitation, or masked staged change. Exit 2 means the review could not complete safely or validly. The report retains any valid partial reviewer result and records omissions. Compare the resolved base against the effective worktree, including untracked source. Inspect material omitted binaries and lockfiles separately.
