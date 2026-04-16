---
name: modelscope-studio-deploy
description: Deploy or update Gradio apps on ModelScope 创空间 / Studio with a ModelScope `ms-...` access key, including creating a new Studio, safely reusing an existing Studio without destructive sync by default, starting the instance, verifying it, and returning a fresh tokenized access URL. Use when the task is to deploy a Gradio demo to `www.modelscope.cn`, especially when only an access key is provided or when an existing Studio already has content that must be preserved.
---

# ModelScope Studio Deploy

Use this skill when the goal is to push a Gradio app to ModelScope 创空间 and hand back a working access link.
The authoritative automation lives in:

- `scripts/modelscope_studio_deploy.py`
- `scripts/materialize_toy_gradio_app.py`

Read [references/workflow.md](references/workflow.md) before the first deployment in a session.
Read [references/troubleshooting.md](references/troubleshooting.md) when the Studio is stuck, verification fails, or an existing repo has surprising contents.

## Default Behavior

- Treat the full `ms-...` access key as the credential. Do not assume a short git token will work.
- Default to `create-or-reuse` for the Studio lifecycle.
- Default to non-destructive overlay updates. Do not pass `--sync-delete` unless the user explicitly wants the remote repo to exactly mirror the local source directory.
- Prefer `--ephemeral-worktree` unless you intentionally want to preserve a local clone.
- If the user did not explicitly provide a source path, do not scan the whole filesystem for one. Materialize a temporary toy app immediately when the request is for a demo, toy app, smoke test, or quick deployment.
- After pushing code, start the Studio, wait for `Running`, then verify it.
- Always return the fresh tokenized `share_url`. The bare `.ms.show` URL is not enough for reliable access and may 403 on `/config`.

## If The User Only Gives An Access Key

Do not block on missing app source if the request is for a toy app, smoke test, hello-world demo, or quick deployment.
Do not spend time searching unrelated directories for historical source trees unless the user explicitly asked for a specific existing project.
Materialize a minimal Gradio demo with `scripts/materialize_toy_gradio_app.py`, deploy it, and report the final tokenized URL.

## Standard Commands

Create or reuse a Studio and deploy:

```bash
python3 scripts/modelscope_studio_deploy.py deploy \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name> \
  --source-dir <source-dir> \
  --reuse-mode create-or-reuse \
  --ephemeral-worktree \
  --verify-mode config
```

Create a toy app first when no source tree exists:

```bash
python3 scripts/materialize_toy_gradio_app.py \
  --output-dir /tmp/modelscope-toy-app \
  --variant echo \
  --title "My Toy Demo"
```

Inspect current detail and fresh URLs:

```bash
python3 scripts/modelscope_studio_deploy.py info \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name>
```

Fetch runtime logs:

```bash
python3 scripts/modelscope_studio_deploy.py logs \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name> \
  --tail 200
```

## Output Requirements

Every successful deployment response should surface:

- `namespace`
- `studio_name`
- `status`
- whether the Studio was created or reused
- the fresh tokenized `share_url`
- the `config_url`

If the user asks for the bare link, include it only alongside a warning that the fresh tokenized link is the one that is expected to work immediately.
