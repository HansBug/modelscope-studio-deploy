# ModelScope Config Rules

Checked against official ModelScope docs on 2026-04-17:

- https://www.modelscope.cn/docs/studios/studio-card
- https://www.modelscope.cn/docs/studios/create
- https://www.modelscope.cn/docs/studios/quick-create
- https://www.modelscope.cn/docs/studios/docker
- https://modelscope.cn/api/v1/studios/deploy_schema.json

Use this reference when preparing files for ModelScope Studio so the app does not fail due to metadata or deployment config drift.

## 1. README Front Matter

ModelScope parses Studio card metadata from the `README.md` file.
The official Studio card doc says the YAML header should be placed at the top of `README.md` and delimited by `---`.

Official example fields:

```yaml
---
domain:
- cv
tags:
- demo
datasets:
  train:
  - modelscope/coco_2014_caption
models:
- damo/speech_charctc_kws_phone-xiaoyunxiaoyun
license: Apache License 2.0
deployspec:
  entry_file: app.py
---
```

Documented field meanings:

- `domain`: Studio domain, such as `cv`, `nlp`, `audio`, `multi-modal`, `AutoML`, or a custom value
- `license`: open-source license string, for example `Apache License 2.0`, `MIT`, `GPL-3.0`
- `language`: supported language types for the Studio, when relevant
- `tags`: custom tags used for discovery/filtering
- `datasets`: related datasets
- `models`: related models
- `deployspec.entry_file`: runtime entry file

## 2. Minimal README Template

Use this as the safest default template when a project does not already have ModelScope card metadata:

```markdown
---
domain:
- nlp
tags:
- gradio
- demo
license: Apache License 2.0
deployspec:
  entry_file: app.py
---

# Project Title

Short description of the Studio and how to use it.
```

Inference from the official docs:

- the Studio card page shows `deployspec.entry_file` as the structured YAML form
- the create page informally mentions modifying the YAML header `entry_file` field
- prefer `deployspec.entry_file`, because that is the fully documented card schema example

## 3. Runtime File Expectations

From the official create doc:

- `README.md` is required
- runtime entry file defaults:
  - Gradio or Streamlit: `app.py`
  - Static HTML: `index.html`
- you can override the entry file through README front matter using `deployspec.entry_file`
- `requirements.txt` is where extra Python dependencies are declared

Practical rule for this skill:

- if the project already has a valid runtime entry file and README, preserve them
- if you introduce README front matter, keep it simple and only add fields you can support confidently

## 4. Quick Create Config

ModelScope also documents a separate `ms_deploy.json` file for the site-side "快速创建并部署" flow.
This is not the same thing as README front matter.

Officially documented keys include:

- `sdk_type`: one of `gradio`, `streamlit`, `static`, `docker`
- `sdk_version`: SDK version from the deployment schema
- `base_image`: base image version from the deployment schema for Gradio/Streamlit
- `resource_configuration`: currently documented quick-create values include `platform/2v-cpu-16g-mem`, `xgpu/8v-cpu-32g-mem-16g`, `xgpu/8v-cpu-64g-mem-48g`
- `environment_variables`: list entries of the form `{"name": "...", "value": "..."}`
- `port`: required for `docker`, currently must be `7860`

For exact enumerations, consult the live schema:

- https://modelscope.cn/api/v1/studios/deploy_schema.json

## 5. Docker-Specific Rules

From the official Docker Studio doc:

- bind the service to `0.0.0.0`
- use port `7860`
- do not bind your service to `8080`; the platform already uses it internally
- reserved headers:
  - `Authorization`
  - `X-modelscope-*`
  - `X-studio-*`

## 6. Skill Defaults

For this skill, the safest default behavior is:

- do not invent complex README front matter unless needed
- if you add front matter, use the minimal template above
- if the app depends on a non-default entry file, set `deployspec.entry_file`
- when using quick-create mode in the future, validate `ms_deploy.json` against the official schema first
