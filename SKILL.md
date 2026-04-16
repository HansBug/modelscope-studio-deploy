---
name: modelscope-studio-deploy
description: Deploy or update ModelScope 创空间 / Studio apps with a ModelScope `ms-...` access key, including creating a new Studio, checking out an existing Studio repo, safely reusing an existing Studio without destructive sync by default, uploading or managing Studio secrets, starting the instance, verifying it, and returning a fresh tokenized access URL. Use when the task is to deploy the user's own source tree to `www.modelscope.cn` or to operate on an existing ModelScope Studio safely.
---

# ModelScope Studio Deploy

Use this skill when the goal is to push an app to ModelScope 创空间 and hand back a working access link.
The authoritative automation lives in `scripts/modelscope_studio_deploy.py`.

Read [references/workflow.md](references/workflow.md) before the first deployment in a session.
Read [references/modelscope_configs.md](references/modelscope_configs.md) before modifying `README.md`, choosing a non-default entry file, or using quick-create config files.
Read [references/troubleshooting.md](references/troubleshooting.md) when the Studio is stuck, verification fails, or an existing repo has surprising contents.

## Default Behavior

- Treat the full `ms-...` access key as the credential. Do not assume a short git token will work.
- When translating a user-provided key into shell commands, prefer exporting it as `MODELSCOPE_ACCESS_KEY` and letting the script read the default env var instead of embedding a long literal `--access-key` in complex shell commands.
- Default to `create-or-reuse` for the Studio lifecycle.
- Default to non-destructive overlay updates. Do not pass `--sync-delete` unless the user explicitly wants the remote repo to exactly mirror the local source directory.
- Prefer `--ephemeral-worktree` unless you intentionally want to preserve a local clone.
- Treat this skill as a ModelScope toolbox. The scripts should stay focused on ModelScope operations rather than generating fixed demo apps.
- If the user already has a local source tree, deploy that.
- If the user wants to edit an existing Studio, use `checkout` first and then work from the checked-out repo.
- If the app needs secrets, upload them with `--secret`, `--secret-from-env`, or the `secrets` subcommands. For automation, prefer `--secret-from-env` for sensitive values instead of embedding them into long shell command literals.
- After pushing code, start the Studio, wait for `Running`, then verify it.
- Always return the fresh tokenized `share_url`. The bare `.ms.show` URL is not enough for reliable access and may 403 on `/config`.

## Source Handling

Do not search broad unrelated directories trying to guess a source tree.
Work with a user-provided path, the current working directory, or a repo checked out from ModelScope.
If source needs to be authored from scratch, do that outside the ModelScope scripts and then deploy the resulting directory.

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

Check out an existing Studio repo locally:

```bash
python3 scripts/modelscope_studio_deploy.py checkout \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name>
```

Inspect current detail and fresh URLs:

```bash
python3 scripts/modelscope_studio_deploy.py info \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name>
```

Manage Studio secrets directly:

```bash
python3 scripts/modelscope_studio_deploy.py secrets list \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name>

python3 scripts/modelscope_studio_deploy.py secrets upsert \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name> \
  --name LLM_API_KEY \
  --value-from-env AIROUTER_API_KEY
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
- whether secrets were applied
- the fresh tokenized `share_url`
- the `config_url`

If the user asks for the bare link, include it only alongside a warning that the fresh tokenized link is the one that is expected to work immediately.
