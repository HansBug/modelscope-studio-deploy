# Workflow

## Inputs To Collect

- ModelScope access key: the full `ms-...` token
- target Studio name
- optional namespace
  - if omitted, the deploy script derives it from the login response
- source directory
  - optional if the task is a toy/demo deployment and you can materialize one

If the user did not explicitly provide a source directory, do not search broad parts of `/home`, cached worktrees, or unrelated repos trying to guess one.
For demo and smoke-test requests, immediately materialize a temporary toy app and deploy that.

## Fastest Safe Path

Use this path unless the user asked for something else:

1. If no source app is provided and the user wants a demo or toy app, generate one:

```bash
python3 scripts/materialize_toy_gradio_app.py \
  --output-dir /tmp/modelscope-toy-app \
  --variant echo \
  --title "Codex Toy Demo"
```

2. Deploy with non-destructive reuse semantics:

```bash
python3 scripts/modelscope_studio_deploy.py deploy \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name> \
  --source-dir <source-dir> \
  --reuse-mode create-or-reuse \
  --ephemeral-worktree \
  --verify-mode config
```

3. Return the tokenized `share_url`, not only the bare `.ms.show` URL.

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

Verify the Studio after it is running:

```bash
python3 scripts/modelscope_studio_deploy.py verify \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name <studio-name> \
  --verify-mode config
```

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
  '$modelscope-studio-deploy 用这个 ms key 部署一个 Gradio 玩具应用到 HansBug/codex-skill-demo，并返回 fresh tokenized share_url。key: ms-...'
```

## Notes

- Pushing git content alone is not enough. The Studio must also be started with `reset_restart`.
- Expect status to move through `Empty` or `Creating` before `Running`.
- The script already queries the current default Gradio SDK version and the free instance type when needed.
