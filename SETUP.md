# Agent-assisted Review Gate setup

Use this when the user asks you to install or configure Review Gate.

1. Identify the primary harness and whether the skill should be personal or project-specific. Use the install instructions in [README.md](README.md). Check for an existing skill before replacing it. Verify `review-gate --help` from the shell the agent will use.
2. Run `review-gate setup --primary HARNESS` with the actual primary harness. Use `--primary-family FAMILY` when the harness is OpenCode or the active model differs from the harness's default family. This saves the default route without approving the current repo or making model calls. Review the selected services and model IDs. If needed, use the CLI's normal sign-in and model list to find available models. Edit the user config for custom routes or updated version pins. Use the README's [reviewer model guide](README.md#choose-reviewer-models) when the user wants different models or reviewer counts for plans and diffs. Keep credentials out of the chat and config.
3. To test, create a temporary directory with a synthetic `task.md` and `plan.md`. For example, ask for addition of two integers including negative values, and plan to return the sum and test zero and negative inputs. From the synthetic directory, run setup with one `--allow` per service in the route. Run the plan review and confirm every selected reviewer returned a valid result.
4. From the target repo, add approvals only for the services the user explicitly authorized. Summarize the skill installation path and show the shortest plan and diff commands for that repo.

For the default Codex route, the synthetic test commands are:

```sh
review-gate setup --primary codex --allow antigravity
review-gate plan plan.md
```

Use a separate config via `--config PATH` on both commands if you want to keep synthetic approvals out of your main config.
