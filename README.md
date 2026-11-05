# Review Gate

Get two independent model reviews before you implement a plan or hand off a code change. Choose Codex, Antigravity, Claude Code, or OpenCode as your primary. Review Gate selects two reviewer models from different families than the primary and each other.

## Quick start

Install once from a checkout of this private repository. This example uses Python 3.11 or later and `uv`.

```sh
gh repo clone lander16/review-gate
cd review-gate
uv tool install .
```

In the repository you want to review, run the setup command for the agent doing the work. Setup finds the reviewer executables on your PATH. Each `--allow` explicitly authorizes the named service to receive review packets from this repository.

| Primary agent | Default reviewers | Setup command |
| --- | --- | --- |
| Codex with an OpenAI model | Gemini and Claude via `agy` | `review-gate setup --primary codex --allow antigravity` |
| Antigravity with a Gemini model | OpenAI via Codex and Claude via `agy` | `review-gate setup --primary antigravity --allow openai --allow antigravity` |
| Claude Code with a Claude model | OpenAI via Codex and Gemini via `agy` | `review-gate setup --primary claude --allow openai --allow antigravity` |
| OpenCode with a Qwen model, for example | Gemini and Claude via `agy` | `review-gate setup --primary opencode --primary-family qwen --allow antigravity` |

Use the family of the model actually doing the work. For example, if Antigravity is running a Claude model, pass `--primary antigravity --primary-family claude`. OpenCode always needs the family when you first set it up. The same `plan` and `diff` commands work with all four harnesses.

The default routes use only `agy` or Codex as reviewers. Sign in to the reviewer CLIs normally. If your account offers Claude through `agy`, you can get a Claude review without installing Claude Code. Omit `--allow` to inspect the route before approving it. Use a synthetic review to check the selected models before sending real work. See [Agent-assisted setup](#agent-assisted-setup).

From the repository root, put the requirements in `task.md`. Then use:

```sh
review-gate plan plan.md     # Before editing, with your proposed plan in plan.md
review-gate diff             # After editing, to review changes since HEAD
```

## When and how to use it

### Review a plan before changing code

Use a plan review when an implementation has meaningful design choices, such as changing an interface, migrating data, or coordinating changes across services. Give reviewers enough information to spot missing requirements and risky assumptions.

For example, if the task is to stop expired sessions from being refreshed, `task.md` should say what must happen for expired and valid sessions. Put the proposed code changes and tests in `plan.md`. Add relevant existing code when a claim depends on an interface:

```sh
review-gate plan plan.md --context src/session.py --context tests/test_session.py
```

Use `--task docs/session-requirements.md` if the brief lives elsewhere. Context paths are relative to the repository root. Revise the plan when a finding exposes a real gap.

### Review the implementation after running tests

Use a diff review after you make the change and run the relevant local tests. Choose the base that represents what you want to review:

| Goal | Command |
| --- | --- |
| Review current edits before committing | `review-gate diff` |
| Review the branch and current edits since it split from `origin/main` | `review-gate diff --base "$(git merge-base HEAD origin/main)"` |
| Compare the working tree directly with a specific commit or ref | `review-gate diff --base abc1234` |

The packet compares the selected base with the effective working tree. It includes staged and unstaged changes and non-ignored untracked files. Review the report's omissions, especially if a binary fixture or lockfile matters to the task. Use the same requirements file you used for the plan.

### Read the results

The command prints the path to a private `report.json`. Open `summary.txt` beside it for the readable findings. Check the cited evidence and decide which findings to act on. After fixing a verified blocker, run the relevant tests and review the updated work.

| Exit | Meaning |
| --- | --- |
| 0 | Both reviewers returned valid results with no reported blocker or material limitation |
| 1 | A reviewer reported a blocker or material limitation, or the snapshot found a staged change hidden by the worktree |
| 2 | The review could not complete, for example because a reviewer failed or the repository lacks approval |

An exit of 0 still leaves you responsible for any omissions. If a reviewer fails, the report keeps any valid result from the other reviewer.

## Agent-assisted setup

Open the checkout in your coding agent and say:

> Set up Review Gate for this harness using [SETUP.md](SETUP.md). Install the skill at the scope I choose and verify both reviewers with a synthetic task.

Once installed, use `$review-gate` in Codex or `/review-gate` in Antigravity or Claude Code. In OpenCode, ask the agent to use the `review-gate` skill by name. For example:

- “Use Review Gate to check the plan for this task before implementation.”
- “Use Review Gate to review my branch against its merge base with `origin/main`. Verify each finding against the code and tests.”

### Install the skill manually

Copy the entire [skills/review-gate](skills/review-gate) folder to one of the directories below. Project paths are relative to the repository where you want to use the skill.

| Harness | Project | Personal |
| --- | --- | --- |
| Codex Desktop / CLI | `.agents/skills/` | `~/.agents/skills/` |
| Antigravity IDE / `agy` | `.agents/skills/` | `~/.gemini/config/skills/` |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |
| OpenCode | `.opencode/skills/` | `~/.config/opencode/skills/` |

For a personal Codex install, run these commands from the Review Gate checkout. Check for an existing skill before replacing it.

```sh
mkdir -p "$HOME/.agents/skills"
cp -R skills/review-gate "$HOME/.agents/skills/"
```

Start a new agent session if the skill is missing. See the official skill guides for [Codex](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills), [Antigravity](https://antigravity.google/docs/skills), [Claude Code](https://code.claude.com/docs/en/skills), and [OpenCode](https://opencode.ai/docs/skills/).

## Choose reviewer models

`setup` prints the selected profile names and model IDs. Each `[reviewers.NAME]` profile in `~/.config/review-gate/config.toml` pins a CLI, service, model family, and exact model ID. By default, both phases use the same pair. The initial `agy` profiles use Gemini 4 Argon Medium and Claude Sonnet 5.5 Medium. The default Codex reviewer uses `gpt-6.1-sol`.

To use different models for planning and code review, replace the existing route array for your primary model family with a two-phase table. This example keeps Gemini the same and uses a higher-effort Claude profile for plans:

```toml
[routes.openai]
plan = ["gemini-agy", "claude-plan"]
diff = ["gemini-agy", "claude-agy"]

[reviewers.claude-plan]
adapter = "agy"
service = "antigravity"
family = "claude"
model = "claude-sonnet-5-5-high"
binary = "/absolute/path/to/agy"
version = "1.5.0"
```

Keep the existing `gemini-agy` and `claude-agy` profiles. Remove the old `openai = [...]` line under `[routes]` before adding `[routes.openai]`. Use the same binary path and version as your working `claude-agy` profile, and check model IDs with `agy models`. Run `review-gate setup` to see both pairs and the required service approvals. The report records the exact model ID passed to each reviewer.

For a one-off change, pass two existing profile names. This keeps the saved defaults:

```sh
review-gate diff --reviewer gemini-agy --reviewer claude-plan
```

Each run still needs two distinct reviewer families and repository approval for both services.

## Configuration and sharing

- To approve another repository, run `review-gate setup --allow antigravity` there if your saved route uses only Antigravity. For an Antigravity primary using Codex and a Claude model through `agy`, use `review-gate setup --primary antigravity --allow openai --allow antigravity`.
- `setup` keeps existing routes and approvals. It saves the primary harness and family as your defaults. Override them for one review with `--primary` and `--primary-family`.
- Edit `~/.config/review-gate/config.toml` to customize the two reviewers for a primary family. You can use the Claude Code CLI or an OpenCode Go model as a reviewer by defining a profile and adding it to the route. Use `agy models` for available models. [config.example.toml](config.example.toml) shows the format for custom routes. For older configs, set `mode = "native"` and remove the legacy launcher and reviewer profile fields. To revoke an approval, remove that service from the repository's `approved_services` entry.
- Native mode relies on CLI tool restrictions and has no OS-level filesystem or network allowlist. Antigravity uses its normal login and may write session state in its usual directories. Keep the config and reports outside the reviewed repo. Stronger isolation is tracked in [issue #1](https://github.com/lander16/review-gate/issues/1).

To run the offline tests from the checkout, use `uv run --extra test pytest -q`.
