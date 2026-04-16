# AGENTS.md

This repository publishes a Codex skill.
Treat it as both:

- the installable skill payload for Codex
- the public GitHub source of truth for that payload

## Purpose

`modelscope-studio-deploy` exists to make ModelScope Studio deployment repeatable and low-friction.
It should work especially well for:

- "I only have an `ms-...` key, deploy a toy app for me"
- "Update this existing Studio without deleting unexpected remote files"

The repository has three layers that must stay aligned:

1. skill instructions in `SKILL.md`
2. helper references in `references/`
3. deterministic helpers in `scripts/`

`agents/openai.yaml` must also stay aligned with the actual behavior and invocation style.

## Public Contract

These behaviors are effectively the contract of this skill:

- accept a full ModelScope access key of the form `ms-...`
- support both new Studio creation and existing Studio reuse
- default to non-destructive overlay updates
- only delete remote files when `--sync-delete` is explicitly requested
- prefer `--ephemeral-worktree` for safe automation
- return a fresh tokenized `share_url`, not just the bare `.ms.show` URL
- if the user did not provide a source directory and wants a demo or smoke test, generate a temporary toy app immediately
- do not search broad unrelated directories trying to guess a source tree unless the user explicitly asked for a specific existing project

If you change one of these, update the docs and call it out in the commit.

## File Responsibilities

- `SKILL.md`
  Core invocation rules for Codex.
- `agents/openai.yaml`
  UI-facing skill metadata and default explicit invocation prompt.
- `references/workflow.md`
  Operational path for common deployment flows.
- `references/troubleshooting.md`
  Failure handling and operator guidance.
- `scripts/materialize_toy_gradio_app.py`
  Generates a minimal Gradio app when a demo source tree is needed immediately.
- `scripts/modelscope_studio_deploy.py`
  Implements login, create/reuse, git push, restart, wait, verify, and URL return.

## Documentation Sync Rules

When runtime behavior changes, review all of these:

- `SKILL.md`
- `README.md`
- `AGENTS.md`
- `references/workflow.md`
- `references/troubleshooting.md`
- `agents/openai.yaml`

If the change affects install or invocation, update the copy-paste prompt in `README.md`.

## Validation Expectations

Before pushing a functional change, at minimum do all of these:

- `python3 -m py_compile scripts/modelscope_studio_deploy.py scripts/materialize_toy_gradio_app.py`
- `python3 scripts/materialize_toy_gradio_app.py --output-dir /tmp/modelscope-skill-smoke --variant echo --title "Smoke Demo" --force`
- `python3 scripts/modelscope_studio_deploy.py --help`
- `python3 scripts/modelscope_studio_deploy.py deploy --help`

For behavior changes, also do real end-to-end checks:

- one direct CLI deployment against ModelScope
- one `codex exec` deployment using `$modelscope-studio-deploy`
- when reuse behavior changes, verify that remote-only files survive the default overlay path

## What Not To Do

- Do not add dependencies unless the deployment or verification path truly requires them.
- Do not silently change default behavior from overlay to destructive sync.
- Do not optimize for the bare `.ms.show` URL and forget the tokenized URL.
- Do not let the skill wander into large filesystem searches when the task is simply "deploy a toy app".
