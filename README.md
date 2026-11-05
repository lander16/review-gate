# Review Gate

Get two independent model reviews before you implement a plan or hand off a code change. Review Gate uses the coding CLIs you already have. With Codex as the primary agent, Antigravity can provide both Gemini and Claude reviews through one existing `agy` login.

## Quick start

Install once from a checkout of this private repository. This example uses Python 3.11 or later and `uv`.

```sh
gh repo clone lander16/review-gate
cd review-gate
uv tool install .
```

In the repository you want to review, run setup. It finds the reviewer executables on your PATH and saves the route in your private user config. With `--allow`, you explicitly authorize the named service to receive review packets from this repository.

```sh
review-gate setup --primary codex --allow antigravity
```

Sign in to `agy` normally if you haven't already. Claude Code is optional. Setup saves candidate model IDs and the detected CLI versions. Run a synthetic review to confirm that your account can use the selected models before sending real work. To preview the route and see which approvals it needs, run `review-gate setup` without `--allow`. See [Agent-assisted setup](#agent-assisted-setup) for a synthetic test.

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

Once installed, use `$review-gate` in Codex or `/review-gate` in Antigravity or Claude Code. For example:

- “Use Review Gate to check the plan for this task before implementation.”
- “Use Review Gate to review my branch against its merge base with `origin/main`. Verify each finding against the code and tests.”

### Install the skill manually

Copy the entire [skills/review-gate](skills/review-gate) folder to one of the directories below. Project paths are relative to the repository where you want to use the skill.

| Harness | Project | Personal |
| --- | --- | --- |
| Codex Desktop / CLI | `.agents/skills/` | `~/.agents/skills/` |
| Antigravity IDE / `agy` | `.agents/skills/` | `~/.gemini/config/skills/` |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |

For a personal Codex install, run these commands from the Review Gate checkout. Check for an existing skill before replacing it.

```sh
mkdir -p "$HOME/.agents/skills"
cp -R skills/review-gate "$HOME/.agents/skills/"
```

Start a new agent session if the skill is missing. See the official skill guides for [Codex](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills), [Antigravity](https://antigravity.google/docs/skills), and [Claude Code](https://code.claude.com/docs/en/skills).

## Configuration and sharing

- To approve another repository, run `review-gate setup --allow antigravity` there if your saved route uses only Antigravity. For an Antigravity primary using Codex and a Claude model through `agy`, use `review-gate setup --primary antigravity --allow openai --allow antigravity`.
- `setup` keeps existing routes and approvals. It saves the primary as your default. Override it for one review with `--primary`. Use `--primary-family` if your harness is running a model outside its usual family.
- Edit `~/.config/review-gate/config.toml` for custom models, runner versions, and approvals. Use `agy models` for available models. [config.example.toml](config.example.toml) shows the format for custom routes. For older configs, set `mode = "native"` and remove the legacy launcher and reviewer profile fields. To revoke an approval, remove that service from the repository's `approved_services` entry.
- Native mode relies on CLI tool restrictions and has no OS-level filesystem or network allowlist. Antigravity uses its normal login and may write session state in its usual directories. Keep the config and reports outside the reviewed repo. Stronger isolation is tracked in [issue #1](https://github.com/lander16/review-gate/issues/1).

To run the offline tests from the checkout, use `uv run --extra test pytest -q`.
