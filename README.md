# modelscope-studio-deploy

`modelscope-studio-deploy` is a Codex skill for deploying and updating Gradio apps on ModelScope Studio with a full ModelScope access key such as `ms-...`.

It is designed for two common cases:

- create and deploy a brand-new Gradio toy/demo app when the user only gives an access key
- update an existing ModelScope Studio safely without destructive sync by default

The repository contains the skill prompt, helper references, and two small Python utilities:

- `scripts/modelscope_studio_deploy.py`
- `scripts/materialize_toy_gradio_app.py`

## What It Does

- logs in to ModelScope with a full `ms-...` access key
- creates a new Studio when needed
- reuses an existing Studio when requested
- clones the Studio git repo, overlays new files, commits, and pushes
- triggers `reset_restart`
- waits for the Studio to reach `Running`
- fetches a fresh Studio token
- returns tokenized `share_url` and `config_url`
- verifies the deployed app through `/config`

## Design Choices

- default lifecycle: `create-or-reuse`
- default update mode: non-destructive overlay
- destructive deletion requires explicit `--sync-delete`
- when the user did not provide a source directory and only wants a demo, the skill should generate a temporary toy Gradio app immediately instead of searching unrelated directories
- the final answer should always prefer a fresh tokenized `share_url` over the bare `.ms.show` URL

## Repository Layout

```text
.
├── SKILL.md
├── AGENTS.md
├── README.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── troubleshooting.md
│   └── workflow.md
└── scripts/
    ├── materialize_toy_gradio_app.py
    └── modelscope_studio_deploy.py
```

## Installation

Install it into the Codex local skills directory:

```bash
git clone https://github.com/HansBug/modelscope-studio-deploy "${CODEX_HOME:-$HOME/.codex}/skills/modelscope-studio-deploy"
```

Then invoke it explicitly as `$modelscope-studio-deploy`.

## Copy-Paste Install Prompt

Paste this into Codex if you want it to install or update the skill and run a minimal smoke check:

```text
Install or update the GitHub repo https://github.com/HansBug/modelscope-studio-deploy into my Codex skills directory as modelscope-studio-deploy, then run a minimal validation.

Requirements:
- install to "${CODEX_HOME:-$HOME/.codex}/skills/modelscope-studio-deploy"
- if the repo already exists there, pull the latest main branch instead of recloning
- use `SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/modelscope-studio-deploy"` for validation commands
- run:
  1. python3 "$SKILL_DIR/scripts/materialize_toy_gradio_app.py" --output-dir /tmp/modelscope-skill-smoke --variant echo --title "Smoke Demo" --force
  2. python3 -m py_compile "$SKILL_DIR/scripts/modelscope_studio_deploy.py" "$SKILL_DIR/scripts/materialize_toy_gradio_app.py"
  3. python3 "$SKILL_DIR/scripts/modelscope_studio_deploy.py" --help
  4. python3 "$SKILL_DIR/scripts/modelscope_studio_deploy.py" deploy --help
- confirm that /tmp/modelscope-skill-smoke/app.py and /tmp/modelscope-skill-smoke/requirements.txt exist
- tell me the exact commands you ran and the result
```

## Direct CLI Usage

Generate a toy app:

```bash
python3 scripts/materialize_toy_gradio_app.py \
  --output-dir /tmp/modelscope-toy-app \
  --variant echo \
  --title "Codex Toy Demo" \
  --force
```

Deploy it:

```bash
python3 scripts/modelscope_studio_deploy.py deploy \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name my-demo \
  --source-dir /tmp/modelscope-toy-app \
  --reuse-mode create-or-reuse \
  --ephemeral-worktree \
  --verify-mode config
```

Inspect fresh URLs:

```bash
python3 scripts/modelscope_studio_deploy.py info \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name my-demo
```

Fetch recent logs:

```bash
python3 scripts/modelscope_studio_deploy.py logs \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name my-demo \
  --tail 200
```

## Codex Exec Example

```bash
codex exec --skip-git-repo-check -C /path/to/workdir \
  '$modelscope-studio-deploy 使用我的 ms key 部署一个 Gradio 玩具应用到 HansBug/my-demo，并返回 fresh tokenized share_url。key: ms-...'
```

## Notes

- pushing code alone is not enough; the runtime also needs `reset_restart`
- the bare `.ms.show` URL may not work immediately without a fresh `studio_token`
- deletion through the tested token type should not be assumed available
- this repo publishes the skill itself to GitHub; ModelScope is only the deployment target used for validation
