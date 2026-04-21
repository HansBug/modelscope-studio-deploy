# modelscope-studio-deploy

`modelscope-studio-deploy` is an agent skill for deploying and updating ModelScope Studio apps with a full ModelScope access key such as `ms-...`. It works with both OpenAI Codex CLI (`$modelscope-studio-deploy`) and Anthropic Claude Code (`/modelscope-studio-deploy`, or auto-triggered from the description).

It is designed for two common cases:

- deploy your own local source tree to ModelScope Studio
- check out and safely update an existing ModelScope Studio without destructive sync by default

The repository contains the skill prompt, helper references, and one execution-oriented utility:

- `scripts/modelscope_studio_deploy.py`

## What It Does

- logs in to ModelScope with a full `ms-...` access key
- creates a new Studio when needed
- reuses an existing Studio when requested
- checks out the current Studio repo into a local worktree
- lists, upserts, and deletes Studio secrets
- clones the Studio git repo, overlays new files, commits, and pushes
- triggers `reset_restart`
- waits for the Studio to reach `Running`
- fetches a fresh Studio token
- returns tokenized `share_url` and `config_url`
- verifies the deployed app through `/config`

## Design Choices

- `scripts/` only contains ModelScope interaction components
- your app source should come from your own repo, working directory, or files the agent prepares outside these scripts
- default lifecycle: `create-or-reuse`
- default update mode: non-destructive overlay
- destructive deletion requires explicit `--sync-delete`
- the final answer should always prefer a fresh tokenized `share_url` over the bare `.ms.show` URL

## Repository Layout

```text
.
├── SKILL.md
├── AGENTS.md
├── CLAUDE.md -> AGENTS.md        # symlink, so both agents see the same project instruction
├── README.md
├── agents/
│   └── openai.yaml               # Codex-only UI metadata; Claude Code ignores it
├── references/
│   ├── modelscope_configs.md
│   ├── troubleshooting.md
│   └── workflow.md
└── scripts/
    └── modelscope_studio_deploy.py
```

## ModelScope Config Rules

Before editing app packaging files for ModelScope Studio, read `references/modelscope_configs.md`.
That reference consolidates the official documentation rules this skill relies on:

- `README.md` card metadata must live in YAML front matter at the top of the file, delimited by `---`
- default entry file is `app.py` for Gradio or Streamlit and `index.html` for static apps
- use `deployspec.entry_file` in README front matter when the runtime starts from a non-default file such as `main.py`
- quick-create uses `ms_deploy.json`, not README front matter
- Docker apps must bind to `0.0.0.0:7860`

## Installation

### Codex CLI

Install it into the Codex local skills directory:

```bash
git clone https://github.com/HansBug/modelscope-studio-deploy "${CODEX_HOME:-$HOME/.codex}/skills/modelscope-studio-deploy"
```

Then invoke it explicitly as `$modelscope-studio-deploy`.

### Claude Code

Install it into the Claude local skills directory:

```bash
git clone https://github.com/HansBug/modelscope-studio-deploy "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/modelscope-studio-deploy"
```

Then invoke it explicitly as `/modelscope-studio-deploy`, or let Claude Code auto-trigger it from the `description` in `SKILL.md`.

### Shared Clone (Both)

If you want one working copy that serves both CLIs, clone the repo once and symlink it into each skills directory:

```bash
git clone https://github.com/HansBug/modelscope-studio-deploy ~/src/modelscope-studio-deploy
ln -s ~/src/modelscope-studio-deploy "${CODEX_HOME:-$HOME/.codex}/skills/modelscope-studio-deploy"
ln -s ~/src/modelscope-studio-deploy "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/modelscope-studio-deploy"
```

## Copy-Paste Install Prompt

### For Codex

Paste this into Codex if you want it to install or update the skill and run a minimal smoke check:

```text
Install or update the GitHub repo https://github.com/HansBug/modelscope-studio-deploy into my Codex skills directory as modelscope-studio-deploy, then run a minimal validation.

Requirements:
- install to "${CODEX_HOME:-$HOME/.codex}/skills/modelscope-studio-deploy"
- if the repo already exists there, pull the latest main branch instead of recloning
- use `SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/modelscope-studio-deploy"` for validation commands
- run:
  1. python3 -m py_compile "$SKILL_DIR/scripts/modelscope_studio_deploy.py"
  2. python3 "$SKILL_DIR/scripts/modelscope_studio_deploy.py" --help
  3. python3 "$SKILL_DIR/scripts/modelscope_studio_deploy.py" deploy --help
  4. python3 "$SKILL_DIR/scripts/modelscope_studio_deploy.py" checkout --help
  5. python3 "$SKILL_DIR/scripts/modelscope_studio_deploy.py" secrets list --help
- tell me the exact commands you ran and the result
```

### For Claude Code

Paste this into Claude Code if you want it to install or update the skill and run a minimal smoke check:

```text
Install or update the GitHub repo https://github.com/HansBug/modelscope-studio-deploy into my Claude Code skills directory as modelscope-studio-deploy, then run a minimal validation.

Requirements:
- install to "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/modelscope-studio-deploy"
- if the repo already exists there, pull the latest main branch instead of recloning
- use `SKILL_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/modelscope-studio-deploy"` for validation commands
- run:
  1. python3 -m py_compile "$SKILL_DIR/scripts/modelscope_studio_deploy.py"
  2. python3 "$SKILL_DIR/scripts/modelscope_studio_deploy.py" --help
  3. python3 "$SKILL_DIR/scripts/modelscope_studio_deploy.py" deploy --help
  4. python3 "$SKILL_DIR/scripts/modelscope_studio_deploy.py" checkout --help
  5. python3 "$SKILL_DIR/scripts/modelscope_studio_deploy.py" secrets list --help
- tell me the exact commands you ran and the result
```

## Direct CLI Usage

Check out the current Studio repo into a local worktree for inspection or editing:

```bash
python3 scripts/modelscope_studio_deploy.py checkout \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name my-demo
```

Deploy a source tree and upload secrets in the same run:

```bash
MODELSCOPE_ACCESS_KEY="$MODELSCOPE_ACCESS_KEY" \
python3 scripts/modelscope_studio_deploy.py deploy \
  --studio-name my-demo \
  --source-dir /path/to/source-dir \
  --reuse-mode create-or-reuse \
  --ephemeral-worktree \
  --secret LLM_BASE_URL=https://example.com/v1 \
  --secret LLM_MODEL=gpt-5.4 \
  --secret LLM_WIRE_API=responses \
  --secret-from-env LLM_API_KEY=OPENAI_API_KEY \
  --verify-mode config
```

Manage Studio secrets directly:

```bash
python3 scripts/modelscope_studio_deploy.py secrets list \
  --access-key "$MODELSCOPE_ACCESS_KEY" \
  --studio-name my-demo
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

For `static` Studios, `verify --verify-mode config` automatically falls back to checking the tokenized `share_url` itself because `/config` is not consistently available there.

## Exec Examples

### Codex

```bash
codex exec --skip-git-repo-check -C /path/to/workdir \
  '$modelscope-studio-deploy 用我当前工作目录里的源码部署到 HansBug/my-demo；如果创空间已存在，先 checkout 当前 repo 供我对比或合并；必要时上传 ModelScope secrets；然后返回 fresh tokenized share_url。key: ms-...'
```

### Claude Code

```bash
claude -p --permission-mode bypassPermissions \
  '/modelscope-studio-deploy 用我当前工作目录里的源码部署到 HansBug/my-demo；如果创空间已存在，先 checkout 当前 repo 供我对比或合并；必要时上传 ModelScope secrets；然后返回 fresh tokenized share_url。key: ms-...'
```

## Notes

- for automated shell assembly, prefer `MODELSCOPE_ACCESS_KEY=... python3 scripts/modelscope_studio_deploy.py ...` over embedding a long `--access-key ms-...` literal into a complex quoted command
- pushing code alone is not enough; the runtime also needs `reset_restart`
- the bare `.ms.show` URL may not work immediately without a fresh `studio_token`
- if you author a temporary Gradio smoke app during validation, prefer compatibility-safe APIs or pin the version you need; ModelScope images and mirrors may lag the latest Gradio keyword surface
- deletion through the tested token type should not be assumed available
- this repo publishes the skill itself to GitHub; ModelScope is only the deployment target used for validation
