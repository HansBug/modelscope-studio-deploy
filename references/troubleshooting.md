# Troubleshooting

## Bare URL Does Not Work

Symptom:

- the bare `.ms.show` page or `/config` returns `403`

Action:

- fetch a fresh Studio token and use the tokenized `share_url` or `config_url`
- the deploy and info commands already do this

## Status Stays `Empty`

Symptom:

- code was pushed but the Studio status remains `Empty`

Cause:

- git push alone does not start the runtime

Action:

- run `start`
- or redeploy with the default `reset-restart` start mode

## `studio instance does not exist`

Symptom:

- log retrieval returns `studio instance does not exist`

Meaning:

- the runtime has not been created yet

Action:

- this is usually non-fatal before the first successful start
- retry after `reset_restart`

## Existing Worktree Is Dirty

Symptom:

- the deploy script refuses to reuse a local worktree

Action:

- prefer `--ephemeral-worktree`
- or clean the local clone intentionally before reuse

## Existing Studio Has Extra Files

Default behavior is safe overlay:

- local files are copied on top of the repo
- remote-only files are preserved

If exact mirroring is required:

- rerun with `--sync-delete`

## README Front Matter Is Wrong Or Missing

Symptom:

- the Studio card metadata looks wrong
- the wrong file is used as the runtime entrypoint

Action:

- read `references/modelscope_configs.md`
- keep README front matter at the top of `README.md`, delimited by `---`
- prefer `deployspec.entry_file` when the app does not start from the default file

## Docker App Does Not Come Up

Symptom:

- Docker Studio starts but the app is unreachable

Action:

- confirm the service binds to `0.0.0.0`
- confirm the service listens on `7860`
- do not bind to `8080`; ModelScope already uses it internally

## Long `Creating`

`Creating` can last for a while on ModelScope free instances.

Action:

- wait longer
- inspect with `info`
- read recent runtime output with `logs`
- if necessary, rerun `start`

## Browser Verification Fails

Symptom:

- `verify --verify-mode browser` fails before opening the app

Action:

- confirm selenium and Chrome/Chromium support are available
- fall back to `verify --verify-mode config` if a browser is not needed

## Static Studio `/config` Returns 404

Symptom:

- `verify --verify-mode config` fails against `/config` for a `static` Studio

Meaning:

- ModelScope static pages may not expose the same `/config` endpoint behavior as Gradio or Streamlit

Action:

- use a recent version of this skill; it automatically falls back to tokenized `share_url` accessibility checks for `static`
- if validating manually, fetch the tokenized `share_url` itself and confirm the expected HTML title or body

## Gradio App Fails On A Newer Keyword

Symptom:

- the runtime fails during app startup with a `TypeError` about an unexpected Gradio keyword argument
- one observed case was `ChatInterface.__init__() got an unexpected keyword argument 'type'`

Meaning:

- the ModelScope image or mirror may be behind the Gradio API surface your temporary app assumed

Action:

- simplify the app to compatibility-safe arguments
- or pin the specific Gradio version your code expects in `requirements.txt`
- then redeploy and rerun `start` or `verify`

## Deletion Is Not Available Through This Token

Observed behavior:

- deletion calls can fail with a token capability error

Action:

- do not rely on API deletion in this skill
- prefer reusing existing test Studios for repeated iterations
