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

## Deletion Is Not Available Through This Token

Observed behavior:

- deletion calls can fail with a token capability error

Action:

- do not rely on API deletion in this skill
- prefer reusing existing test Studios for repeated iterations
