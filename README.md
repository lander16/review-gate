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

> Set up Review Gate for my current coding harness. Follow [SETUP.md](SETUP.md), install the skill at the scope I choose, and draft my private reviewer configuration. Use synthetic inputs for verification and tell me which sign-ins, isolation checks, or provider approvals are still needed.

## Configure live reviewers

Live review requires a separately qualified isolation launcher. The project currently supplies the launch protocol and offline tests. Qualify the launcher and each model route with synthetic data before allowing real repository content. The macOS provider auth and network boundary still need end-to-end verification.

The launcher protocol is `LAUNCHER PROFILE -- BINARY ARGS...`. It must enforce a filesystem allowlist and provider-only egress, run with dedicated authentication and state, exclude user and project instructions, disable extensions and model tools, propagate exit status, and keep the reviewer and descendants under the same boundary and lifecycle. It must handle both version probes and reviews, preserve stdin and stdout, and allow the process only its designated scratch directory, required runtime, and dedicated profile. A shell forwarding wrapper is unsuitable for live review. Verify the boundary using independent negative probes for reads, writes, and network access.

The external TOML configuration defaults to `~/.config/review-gate/config.toml`. Pin known model IDs and the exact qualified CLI version token. Profiles are assigned and provisioned by the launcher. Each route requires two distinct reviewer families and distinct state profiles.

Start with [config.example.toml](config.example.toml).

Use `codex`, `agy`, `claude`, or `opencode` for the adapter. OpenCode profiles pin an `opencode-go/<model-id>`. The service names track the destination receiving the packet. Family describes underlying model lineage. Approve every destination explicitly for the repo. Keep the configuration and reports outside the repo. Treat both reports and provider session state as sensitive and remove them according to your retention policy.

Exit 0 means two valid responses without reported blockers. Exit 1 means a reported blocker, material limitation, or masked staged change. Exit 2 means the review could not complete safely or validly. The report retains any valid partial reviewer result and records omissions. Compare the resolved base against the effective worktree, including untracked source. Inspect material omitted binaries and lockfiles separately.
