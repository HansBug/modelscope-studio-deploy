# Workflow

## Inputs To Collect

- ModelScope access key: the full `ms-...` token
- target Studio name
- optional namespace
  - if omitted, the deploy script derives it from the login response
- source directory
  - or an existing Studio worktree obtained through `checkout`

If the user did not explicitly provide a source directory, do not search broad parts of `/home`, cached worktrees, or unrelated repos trying to guess one.
Use the current working tree, a user-provided path, or a repo obtained through `checkout`.
Before changing `README.md`, `deployspec.entry_file`, or quick-create config files, read `references/modelscope_configs.md`.
When invoking the deploy script from a shell assembled by Codex, prefer `MODELSCOPE_ACCESS_KEY=... python3 ...` over embedding a long `--access-key ms-...` literal into a heavily quoted command. Prefer `--secret-from-env` for sensitive values for the same reason.

## Fastest Safe Path

Use this path unless the user asked for something else:

1. If the user wants to operate on an existing Studio repo, check it out first:

```bash
python3 scripts/modelscope_studio_deploy.py checkout \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name>
```

2. Prepare or edit the source tree outside the ModelScope scripts.

3. If the app needs Studio secrets, add them during deploy or manage them separately:

```bash
python3 scripts/modelscope_studio_deploy.py secrets upsert \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name> \
  --name <secret-name> \
  --value-from-env <local-env-name>
```

4. Deploy with non-destructive reuse semantics:

```bash
python3 scripts/modelscope_studio_deploy.py deploy \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name> \
  --source-dir <source-dir> \
  --reuse-mode create-or-reuse \
  --ephemeral-worktree \
  --verify-mode config
```

Add `--secret` and `--secret-from-env` when the runtime needs ModelScope secrets.

5. Return the tokenized `share_url`, not only the bare `.ms.show` URL.

## Existing Studio With Content

When the Studio already exists, assume the current remote repo may contain files the user still wants.

- Default behavior: overlay the local files on top of the repo and keep remote-only files
- Only use `--sync-delete` when the user explicitly wants the remote repo to exactly match the new source directory
- If the user insists the Studio must already exist, use `--reuse-mode must-exist`
- If the user insists on creating a brand-new Studio and failing otherwise, use `--reuse-mode must-create`

## Useful Subcommands

Inspect detail and get fresh URLs:

```bash
python3 scripts/modelscope_studio_deploy.py info \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name>
```

Start or restart the instance and wait for `Running`:

```bash
python3 scripts/modelscope_studio_deploy.py start \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name>
```

Fetch recent logs:

```bash
python3 scripts/modelscope_studio_deploy.py logs \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name> \
  --tail 200
```

Manage secrets directly:

```bash
python3 scripts/modelscope_studio_deploy.py secrets list \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name>
```

Verify the Studio after it is running:

```bash
python3 scripts/modelscope_studio_deploy.py verify \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name> \
  --verify-mode config
```

For `static` Studios, the script automatically validates the tokenized `share_url` itself because ModelScope may not expose a usable `/config` endpoint there.

Use browser verification only when deeper proof is needed and selenium is available:

```bash
python3 scripts/modelscope_studio_deploy.py verify \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name> \
  --verify-mode browser
```

## Codex Exec Example

```bash
codex exec --skip-git-repo-check -C /home/hansbug \
  '$modelscope-studio-deploy 用我的本地源码目录部署到 HansBug/codex-skill-demo；如果创空间已存在，先 checkout 当前 repo；必要时上传 ModelScope secrets；然后返回 fresh tokenized share_url。key: ms-...'
```

## Notes

- Pushing git content alone is not enough. The Studio must also be started with `reset_restart`.
- Expect status to move through `Empty` or `Creating` before `Running`.
- The script already queries the current default SDK version for the requested `sdk_type` and the free instance type when needed.
- If you create a temporary Gradio app just to validate the deployment path, keep it conservative: avoid newly added `ChatInterface` kwargs unless you also pin a compatible Gradio version in `requirements.txt`.
