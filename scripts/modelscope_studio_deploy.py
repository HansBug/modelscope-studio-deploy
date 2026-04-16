#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests


DEFAULT_ENDPOINT = "https://www.modelscope.cn"
DEFAULT_ACCESS_KEY_ENV = "MODELSCOPE_ACCESS_KEY"
DEFAULT_SDK_TYPE = "gradio"
SUPPORTED_SDK_TYPES = ("gradio", "streamlit", "static", "docker")
DEFAULT_VERIFY_MODE = "config"
DEFAULT_TIMEOUT = 30
DEFAULT_REQUEST_RETRIES = 3
STATUS_RUNNING = "Running"
STATUS_CREATING = "Creating"
NON_FATAL_RESET_MESSAGES = (
    "数据变更中",
    "Please wait",
)
FATAL_STATUSES = {
    "Failed",
    "Error",
    "DeployFailed",
    "CreateFailed",
}


class DeploymentError(RuntimeError):
    pass


@dataclass
class CommandResult:
    stdout: str
    stderr: str


@dataclass(frozen=True)
class SecretSpec:
    name: str
    value: str
    source: str


def _read_access_key(arg_value: str | None, env_name: str) -> str:
    access_key = arg_value or os.environ.get(env_name)
    if not access_key:
        raise DeploymentError(
            f"ModelScope access key is required. Pass --access-key or set {env_name}."
        )
    return access_key.strip()


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> CommandResult:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        cmd = " ".join(args)
        raise DeploymentError(
            f"Command failed ({proc.returncode}): {cmd}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return CommandResult(stdout=proc.stdout, stderr=proc.stderr)


def _json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def _append_query(url: str, **params: str) -> str:
    parts = urlsplit(url)
    current = dict(parse_qsl(parts.query, keep_blank_values=True))
    current.update(params)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(current),
            parts.fragment,
        )
    )


def _default_worktree(namespace: str, studio_name: str) -> Path:
    root = Path.home() / ".cache" / "codex-modelscope-studios"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{namespace}-{studio_name}"


def _git_remote(endpoint: str, namespace: str, studio_name: str, access_key: str | None = None) -> str:
    split = urlsplit(endpoint)
    if access_key:
        netloc = f"oauth2:{access_key}@{split.netloc}"
    else:
        netloc = split.netloc
    return urlunsplit((split.scheme, netloc, f"/studios/{namespace}/{studio_name}.git", "", ""))


def _copy_source_tree(source_dir: Path, repo_dir: Path, *, sync_delete: bool) -> dict[str, list[str]]:
    if not source_dir.is_dir():
        raise DeploymentError(f"Source directory does not exist: {source_dir}")

    created_or_updated: list[str] = []
    skipped = {".git", "__pycache__", ".DS_Store"}

    source_entries: set[str] = set()
    for src in source_dir.rglob("*"):
        rel = src.relative_to(source_dir)
        if any(part in skipped for part in rel.parts):
            continue
        source_entries.add(rel.as_posix())
        dst = repo_dir / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        created_or_updated.append(rel.as_posix())

    deleted: list[str] = []
    if sync_delete:
        for dst in sorted(repo_dir.rglob("*"), reverse=True):
            rel = dst.relative_to(repo_dir)
            if any(part in skipped for part in rel.parts):
                continue
            rel_key = rel.as_posix()
            if rel_key not in source_entries:
                if dst.is_file() or dst.is_symlink():
                    dst.unlink()
                    deleted.append(rel_key)
                elif dst.is_dir():
                    try:
                        dst.rmdir()
                        deleted.append(rel_key)
                    except OSError:
                        pass

    return {
        "copied": sorted(set(created_or_updated)),
        "deleted": sorted(set(deleted)),
    }


def _parse_assignment(raw: str, *, option_name: str) -> tuple[str, str]:
    name, separator, value = raw.partition("=")
    if not separator:
        raise DeploymentError(f"{option_name} expects NAME=VALUE format, got: {raw}")
    name = name.strip()
    if not name:
        raise DeploymentError(f"{option_name} requires a non-empty name: {raw}")
    return name, value


def _normalize_secret_specs(secret_specs: Iterable[SecretSpec]) -> list[SecretSpec]:
    deduped: dict[str, SecretSpec] = {}
    for spec in secret_specs:
        deduped[spec.name] = spec
    return list(deduped.values())


def _collect_secret_specs(args: argparse.Namespace) -> list[SecretSpec]:
    secret_specs: list[SecretSpec] = []
    for raw in args.secret or []:
        name, value = _parse_assignment(raw, option_name="--secret")
        secret_specs.append(SecretSpec(name=name, value=value, source="literal"))
    for raw in args.secret_from_env or []:
        name, env_name = _parse_assignment(raw, option_name="--secret-from-env")
        if env_name not in os.environ:
            raise DeploymentError(
                f"Environment variable {env_name} is not set for --secret-from-env {name}={env_name}."
            )
        secret_specs.append(SecretSpec(name=name, value=os.environ[env_name], source=f"env:{env_name}"))
    return _normalize_secret_specs(secret_specs)


def _env_name(entry: dict[str, Any]) -> str:
    return str(entry.get("VariableName") or entry.get("Name") or "").strip()


def _env_id(entry: dict[str, Any]) -> int | None:
    value = entry.get("VariableId")
    if value is None:
        value = entry.get("Id")
    if value is None:
        return None
    return int(value)


def _sanitize_env_entry(entry: dict[str, Any]) -> dict[str, Any]:
    safe_entry = {key: value for key, value in entry.items() if key != "Value"}
    if "VariableName" not in safe_entry and entry.get("Name"):
        safe_entry["VariableName"] = entry["Name"]
    variable_id = _env_id(entry)
    if variable_id is not None and "VariableId" not in safe_entry:
        safe_entry["VariableId"] = variable_id
    return safe_entry


class ModelScopeStudioClient:
    def __init__(self, access_key: str, *, endpoint: str = DEFAULT_ENDPOINT) -> None:
        self.access_key = access_key
        self.endpoint = endpoint.rstrip("/")
        self.api_base = f"{self.endpoint}/api"
        self.session = requests.Session()
        self.username: str | None = None

    def login(self) -> dict[str, Any]:
        data = self._request("POST", "/v1/login", json_body={"AccessToken": self.access_key})
        username = data.get("Username") or data.get("username")
        if not username:
            raise DeploymentError("ModelScope login succeeded but username was missing.")
        self.username = username
        return data

    def _headers(self, method: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            csrf = self.session.cookies.get("csrf_token")
            if csrf:
                headers["X-CSRF-TOKEN"] = requests.utils.unquote(csrf)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        raw_response: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Any:
        url = path if path.startswith("http") else f"{self.api_base}{path}"
        response = None
        for attempt in range(1, DEFAULT_REQUEST_RETRIES + 1):
            try:
                response = self.session.request(
                    method=method.upper(),
                    url=url,
                    json=json_body,
                    params=params,
                    headers=self._headers(method),
                    timeout=timeout,
                )
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                if attempt >= DEFAULT_REQUEST_RETRIES:
                    raise DeploymentError(
                        f"Request to ModelScope failed after {attempt} attempts: {method.upper()} {url} ({exc})"
                    ) from exc
                time.sleep(attempt)
            except requests.exceptions.RequestException as exc:
                raise DeploymentError(f"Request to ModelScope failed: {method.upper()} {url} ({exc})") from exc

        if response is None:
            raise DeploymentError(f"Request to ModelScope did not return a response: {method.upper()} {url}")
        if raw_response:
            return response

        try:
            payload = response.json()
        except ValueError:
            if response.ok:
                return response.text
            raise DeploymentError(f"Non-JSON error from ModelScope ({response.status_code}): {response.text}")

        success = payload.get("Success", response.ok)
        code = payload.get("Code")
        if not response.ok or success is False:
            message = payload.get("Message") or response.text
            raise DeploymentError(f"ModelScope API error ({response.status_code}, code={code}): {message}")
        return payload.get("Data")

    def get_studio(self, namespace: str, studio_name: str) -> dict[str, Any] | None:
        response = self._request(
            "GET",
            f"/v1/studio/{namespace}/{studio_name}",
            raw_response=True,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.status_code == 404:
            return None
        if not response.ok or (payload and payload.get("Success") is False):
            message = payload.get("Message") if payload else response.text
            code = payload.get("Code") if payload else "unknown"
            raise DeploymentError(
                f"Failed to fetch studio {namespace}/{studio_name} "
                f"({response.status_code}, code={code}): {message}"
            )
        if payload is None:
            raise DeploymentError("ModelScope studio detail returned a non-JSON success response.")
        return payload.get("Data")

    def get_status(self, namespace: str, studio_name: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/studio/{namespace}/{studio_name}/status")

    def get_logs(self, namespace: str, studio_name: str) -> list[str]:
        try:
            data = self._request(
                "PUT",
                f"/v1/studio/{namespace}/{studio_name}/log",
                json_body={"Path": namespace, "Name": studio_name},
            )
        except DeploymentError as exc:
            text = str(exc)
            if "studio instance does not exist" in text:
                return []
            raise
        return list(data.get("Logs") or [])

    def list_envs(self, namespace: str, studio_name: str) -> list[dict[str, Any]]:
        data = self._request("GET", f"/v1/studio/{namespace}/{studio_name}/envs")
        envs = data.get("EnvironmentVariables") or []
        return [dict(entry) for entry in envs]

    def _put_env(self, namespace: str, studio_name: str, payload: dict[str, Any]) -> Any:
        return self._request("PUT", f"/v1/studio/{namespace}/{studio_name}/envs", json_body=payload)

    def apply_envs(
        self,
        namespace: str,
        studio_name: str,
        secret_specs: Iterable[SecretSpec],
    ) -> list[dict[str, Any]]:
        secret_specs = _normalize_secret_specs(secret_specs)
        if not secret_specs:
            return []

        existing = {
            _env_name(entry): entry
            for entry in self.list_envs(namespace, studio_name)
            if _env_name(entry)
        }
        results: list[dict[str, Any]] = []
        for spec in secret_specs:
            current = existing.get(spec.name)
            if current is None:
                payload = {
                    "Operation": "add",
                    "VariableName": spec.name,
                    "VariableValue": spec.value,
                }
                action = "add"
            else:
                variable_id = _env_id(current)
                if variable_id is None:
                    raise DeploymentError(
                        f"ModelScope env listing did not include VariableId for existing secret {spec.name}."
                    )
                payload = {
                    "Operation": "modify",
                    "VariableId": variable_id,
                    "VariableName": spec.name,
                    "VariableValue": spec.value,
                }
                action = "modify"

            self._put_env(namespace, studio_name, payload)
            refreshed = {
                _env_name(entry): entry
                for entry in self.list_envs(namespace, studio_name)
                if _env_name(entry)
            }
            current = refreshed.get(spec.name)
            if current is None:
                raise DeploymentError(f"Secret {spec.name} was updated but could not be listed afterwards.")
            existing = refreshed
            results.append(
                {
                    "name": spec.name,
                    "action": action,
                    "source": spec.source,
                    "variable_id": _env_id(current),
                }
            )
        return results

    def delete_env(self, namespace: str, studio_name: str, name: str) -> dict[str, Any]:
        current = None
        for entry in self.list_envs(namespace, studio_name):
            if _env_name(entry) == name:
                current = entry
                break

        if current is None:
            return {
                "name": name,
                "deleted": False,
                "reason": "not-found",
            }

        variable_id = _env_id(current)
        if variable_id is None:
            raise DeploymentError(f"ModelScope env listing did not include VariableId for secret {name}.")
        self._put_env(
            namespace,
            studio_name,
            {
                "VariableId": variable_id,
                "Operation": "delete",
                "VariableName": name,
            },
        )
        return {
            "name": name,
            "deleted": True,
            "variable_id": variable_id,
        }

    def get_default_sdk_version(self, sdk_type: str) -> str:
        data = self._request("GET", f"/v1/studios/sdk-version/{sdk_type}")
        versions = data.get("Versions") or []
        for version in versions:
            if version.get("Tag") == "default" and not version.get("Hidden"):
                return version["Version"]
        for version in versions:
            if not version.get("Hidden"):
                return version["Version"]
        raise DeploymentError(f"No usable SDK versions returned for {sdk_type}.")

    def get_default_instance_type_id(self) -> int:
        data = self._request("GET", "/v1/studios/free_instance")
        free_instances = data.get("FreeInstanceType") or []
        if not free_instances:
            raise DeploymentError("ModelScope did not return any free studio instance types.")
        return int(free_instances[0]["Id"])

    def create_studio(
        self,
        *,
        namespace: str,
        studio_name: str,
        sdk_type: str,
        sdk_version: str,
        instance_type_id: int,
        instance_number: int,
        visibility: int,
        deployed_by_user: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "Path": namespace,
            "Name": studio_name,
            "Visibility": visibility,
            "DeployedByUser": deployed_by_user,
            "InstanceTypeId": instance_type_id,
            "InstanceNumber": instance_number,
            "SdkType": sdk_type,
            "SdkVersion": sdk_version,
        }
        return self._request("POST", "/v1/studios", json_body=payload)

    def reset_restart(self, namespace: str, studio_name: str) -> None:
        try:
            self._request("PUT", f"/v1/studio/{namespace}/{studio_name}/reset_restart", json_body={})
        except DeploymentError as exc:
            text = str(exc)
            if any(fragment in text for fragment in NON_FATAL_RESET_MESSAGES):
                return
            raise

    def get_studio_token(self) -> str:
        data = self._request("GET", "/v1/studios/token")
        token = data.get("Token") or ""
        if not token:
            raise DeploymentError("ModelScope returned an empty studio token.")
        return token


def _ensure_repo(
    *,
    endpoint: str,
    namespace: str,
    studio_name: str,
    access_key: str,
    worktree: Path,
) -> Path:
    token_remote = _git_remote(endpoint, namespace, studio_name, access_key)
    clean_remote = _git_remote(endpoint, namespace, studio_name, None)

    if (worktree / ".git").exists():
        status = _run(["git", "status", "--porcelain"], cwd=worktree)
        if status.stdout.strip():
            raise DeploymentError(f"Existing worktree is dirty and cannot be reused safely: {worktree}")
        _run(["git", "remote", "set-url", "origin", clean_remote], cwd=worktree)
        _run(["git", "fetch", token_remote, "master"], cwd=worktree)
        _run(["git", "checkout", "master"], cwd=worktree)
        _run(["git", "pull", "--ff-only", token_remote, "master"], cwd=worktree)
        return worktree

    worktree.parent.mkdir(parents=True, exist_ok=True)
    if worktree.exists():
        shutil.rmtree(worktree)
    _run(["git", "clone", token_remote, str(worktree)])
    _run(["git", "remote", "set-url", "origin", clean_remote], cwd=worktree)
    return worktree


def _commit_and_push(
    *,
    repo_dir: Path,
    endpoint: str,
    namespace: str,
    studio_name: str,
    access_key: str,
    commit_message: str,
) -> dict[str, Any]:
    status = _run(["git", "status", "--porcelain"], cwd=repo_dir)
    if not status.stdout.strip():
        head = _run(["git", "rev-parse", "HEAD"], cwd=repo_dir)
        return {
            "changed": False,
            "commit": head.stdout.strip(),
        }

    _run(["git", "config", "user.name", namespace], cwd=repo_dir)
    _run(
        [
            "git",
            "config",
            "user.email",
            f"{namespace.lower()}@users.noreply.modelscope.cn",
        ],
        cwd=repo_dir,
    )
    _run(["git", "add", "-A"], cwd=repo_dir)
    _run(["git", "commit", "-m", commit_message], cwd=repo_dir)
    token_remote = _git_remote(endpoint, namespace, studio_name, access_key)
    _run(["git", "push", token_remote, "HEAD:master"], cwd=repo_dir)
    head = _run(["git", "rev-parse", "HEAD"], cwd=repo_dir)
    return {
        "changed": True,
        "commit": head.stdout.strip(),
    }


def _wait_for_status(
    client: ModelScopeStudioClient,
    *,
    namespace: str,
    studio_name: str,
    target_status: str,
    timeout_seconds: int,
    poll_interval: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last: dict[str, Any] | None = None
    while time.time() < deadline:
        last = client.get_status(namespace, studio_name)
        status = last.get("Status")
        if status == target_status:
            return last
        if status in FATAL_STATUSES:
            logs = client.get_logs(namespace, studio_name)
            raise DeploymentError(
                f"Studio entered fatal status {status}.\nRecent logs:\n" + "\n".join(logs[-40:])
            )
        time.sleep(poll_interval)
    logs = client.get_logs(namespace, studio_name)
    raise DeploymentError(
        f"Timed out waiting for studio {namespace}/{studio_name} to reach {target_status}. "
        f"Last status: {last}\nRecent logs:\n" + "\n".join(logs[-40:])
    )


def _verify_config_url(config_url: str, timeout: int) -> dict[str, Any]:
    response = requests.get(config_url, timeout=timeout)
    try:
        payload = response.json()
    except ValueError:
        raise DeploymentError(f"Config endpoint returned non-JSON data ({response.status_code}): {response.text}")
    if response.status_code != 200:
        raise DeploymentError(f"Config endpoint failed ({response.status_code}): {payload}")
    return payload


def _verify_share_url(share_url: str, timeout: int) -> dict[str, Any]:
    response = requests.get(share_url, timeout=timeout)
    if response.status_code != 200:
        raise DeploymentError(f"Share URL failed ({response.status_code}): {response.text[:500]}")
    title_match = re.search(r"<title>(.*?)</title>", response.text, flags=re.IGNORECASE | re.DOTALL)
    title = None
    if title_match:
        title = re.sub(r"\s+", " ", title_match.group(1)).strip()
    return {
        "status_code": response.status_code,
        "content_type": response.headers.get("Content-Type"),
        "title": title,
        "body_preview": response.text[:500],
    }


def _run_fast_verification(*, sdk_type: str, urls: dict[str, str], timeout: int) -> dict[str, Any]:
    if sdk_type == "static":
        page_payload = _verify_share_url(urls["share_url"], timeout=timeout)
        return {
            "verification_target": "share_url",
            "page_status_code": page_payload.get("status_code"),
            "page_content_type": page_payload.get("content_type"),
            "page_title": page_payload.get("title"),
        }

    config_payload = _verify_config_url(urls["config_url"], timeout=timeout)
    return {
        "verification_target": "config_url",
        "config_title": config_payload.get("title"),
        "config_version": config_payload.get("version"),
    }


def _browser_check(share_url: str, timeout_seconds: int) -> dict[str, Any]:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
    except ImportError as exc:
        raise DeploymentError("Browser verification requires selenium to be installed.") from exc

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,1200")

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(share_url)
        deadline = time.time() + timeout_seconds
        body_text = ""
        while time.time() < deadline:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            title = driver.title
            if "Could not load this space." in body_text:
                raise DeploymentError(f"Browser verification failed: {body_text}")
            placeholder_titles = {
                "魔搭社区 - 创空间 - Gradio",
                "魔搭社区 - 创空间 - Streamlit",
                "魔搭社区 - 创空间 - Static",
                "魔搭社区 - 创空间 - Docker",
            }
            if body_text.strip() and (
                title not in placeholder_titles
                or len(body_text.strip().splitlines()) > 1
                or len(body_text.strip()) > 80
            ):
                return {
                    "title": title,
                    "body_preview": body_text[:500],
                }
            time.sleep(2)
        raise DeploymentError(
            f"Browser verification timed out. Last title={driver.title!r}, body={body_text[:500]!r}"
        )
    finally:
        driver.quit()


def _build_share_urls(detail: dict[str, Any], studio_token: str) -> dict[str, str]:
    independent_url = (detail.get("IndependentUrl") or "").rstrip("/")
    if not independent_url:
        raise DeploymentError("Studio detail did not include IndependentUrl.")
    share_url = _append_query(independent_url, studio_token=studio_token, backend_url="/")
    config_url = _append_query(f"{independent_url}/config", studio_token=studio_token)
    return {
        "bare_url": independent_url,
        "share_url": share_url,
        "config_url": config_url,
    }


def _resolve_sdk_version(client: ModelScopeStudioClient, requested: str, sdk_type: str) -> str:
    if requested == "default":
        return client.get_default_sdk_version(sdk_type)
    return requested


def _deploy(args: argparse.Namespace) -> dict[str, Any]:
    access_key = _read_access_key(args.access_key, args.access_key_env)
    client = ModelScopeStudioClient(access_key, endpoint=args.endpoint)
    login_data = client.login()
    namespace = args.namespace or client.username
    if not namespace:
        raise DeploymentError("Namespace is required and could not be derived from the login response.")
    secret_specs = _collect_secret_specs(args)

    sdk_version = _resolve_sdk_version(client, args.sdk_version, args.sdk_type)
    instance_type_id = args.instance_type_id or client.get_default_instance_type_id()

    detail = client.get_studio(namespace, args.studio_name)
    created = False
    if detail is None:
        if args.reuse_mode == "must-exist":
            raise DeploymentError(f"Studio does not exist: {namespace}/{args.studio_name}")
        client.create_studio(
            namespace=namespace,
            studio_name=args.studio_name,
            sdk_type=args.sdk_type,
            sdk_version=sdk_version,
            instance_type_id=instance_type_id,
            instance_number=args.instance_number,
            visibility=args.visibility,
        )
        created = True
        detail = client.get_studio(namespace, args.studio_name)
    elif args.reuse_mode == "must-create":
        raise DeploymentError(f"Studio already exists: {namespace}/{args.studio_name}")

    if detail is None:
        raise DeploymentError("Studio creation returned success but studio details were unavailable.")
    status_before = client.get_status(namespace, args.studio_name)

    worktree = Path(args.worktree) if args.worktree else _default_worktree(namespace, args.studio_name)
    temp_worktree = False
    if args.worktree is None and args.ephemeral_worktree:
        temp_worktree = True
        worktree = Path(tempfile.mkdtemp(prefix=f"modelscope-{namespace}-{args.studio_name}-"))

    try:
        repo_dir = _ensure_repo(
            endpoint=args.endpoint,
            namespace=namespace,
            studio_name=args.studio_name,
            access_key=access_key,
            worktree=worktree,
        )
        source_changes = _copy_source_tree(
            Path(args.source_dir),
            repo_dir,
            sync_delete=args.sync_delete,
        )
        git_result = _commit_and_push(
            repo_dir=repo_dir,
            endpoint=args.endpoint,
            namespace=namespace,
            studio_name=args.studio_name,
            access_key=access_key,
            commit_message=args.commit_message,
        )
        secret_changes = client.apply_envs(namespace, args.studio_name, secret_specs)
    finally:
        if temp_worktree:
            shutil.rmtree(worktree, ignore_errors=True)

    should_restart = (
        args.start_mode != "skip"
        and (
            created
            or git_result.get("changed", False)
            or bool(secret_changes)
            or status_before.get("Status") != STATUS_RUNNING
        )
    )
    if should_restart:
        client.reset_restart(namespace, args.studio_name)
        status_data = _wait_for_status(
            client,
            namespace=namespace,
            studio_name=args.studio_name,
            target_status=STATUS_RUNNING,
            timeout_seconds=args.wait_timeout,
            poll_interval=args.poll_interval,
        )
    else:
        status_data = client.get_status(namespace, args.studio_name)

    detail = client.get_studio(namespace, args.studio_name) or detail
    studio_token = client.get_studio_token()
    urls = _build_share_urls(detail, studio_token)
    sdk_type = detail.get("SdkType") or args.sdk_type

    verification: dict[str, Any] = {"mode": args.verify_mode}
    if args.verify_mode in {"config", "browser"}:
        verification.update(
            _run_fast_verification(
                sdk_type=sdk_type,
                urls=urls,
                timeout=args.request_timeout,
            )
        )
    if args.verify_mode == "browser":
        verification["browser"] = _browser_check(urls["share_url"], timeout_seconds=args.browser_timeout)

    return {
        "created": created,
        "namespace": namespace,
        "studio_name": args.studio_name,
        "username": login_data.get("Username") or namespace,
        "sdk_type": sdk_type,
        "sdk_version": detail.get("SdkVersion") or sdk_version,
        "status": status_data.get("Status"),
        "instance_type_id": detail.get("InstanceTypeId"),
        "source_changes": source_changes,
        "git": git_result,
        "secrets": {
            "applied": secret_changes,
            "count": len(secret_changes),
            "restart_required": bool(secret_changes),
        },
        "restart_triggered": should_restart,
        "urls": urls,
        "studio_token": studio_token,
        "verification": verification,
    }


def _info(args: argparse.Namespace) -> dict[str, Any]:
    access_key = _read_access_key(args.access_key, args.access_key_env)
    client = ModelScopeStudioClient(access_key, endpoint=args.endpoint)
    client.login()
    namespace = args.namespace or client.username
    if not namespace:
        raise DeploymentError("Namespace is required and could not be derived from the login response.")
    detail = client.get_studio(namespace, args.studio_name)
    if detail is None:
        raise DeploymentError(f"Studio does not exist: {namespace}/{args.studio_name}")
    token = client.get_studio_token()
    urls = _build_share_urls(detail, token)
    status = client.get_status(namespace, args.studio_name)
    return {
        "namespace": namespace,
        "studio_name": args.studio_name,
        "status": status.get("Status"),
        "detail": detail,
        "urls": urls,
        "studio_token": token,
    }


def _start(args: argparse.Namespace) -> dict[str, Any]:
    access_key = _read_access_key(args.access_key, args.access_key_env)
    client = ModelScopeStudioClient(access_key, endpoint=args.endpoint)
    client.login()
    namespace = args.namespace or client.username
    if not namespace:
        raise DeploymentError("Namespace is required and could not be derived from the login response.")
    client.reset_restart(namespace, args.studio_name)
    status = _wait_for_status(
        client,
        namespace=namespace,
        studio_name=args.studio_name,
        target_status=STATUS_RUNNING,
        timeout_seconds=args.wait_timeout,
        poll_interval=args.poll_interval,
    )
    return {
        "namespace": namespace,
        "studio_name": args.studio_name,
        "status": status.get("Status"),
    }


def _verify(args: argparse.Namespace) -> dict[str, Any]:
    access_key = _read_access_key(args.access_key, args.access_key_env)
    client = ModelScopeStudioClient(access_key, endpoint=args.endpoint)
    client.login()
    namespace = args.namespace or client.username
    if not namespace:
        raise DeploymentError("Namespace is required and could not be derived from the login response.")
    detail = client.get_studio(namespace, args.studio_name)
    if detail is None:
        raise DeploymentError(f"Studio does not exist: {namespace}/{args.studio_name}")
    token = client.get_studio_token()
    urls = _build_share_urls(detail, token)
    sdk_type = detail.get("SdkType") or ""
    result: dict[str, Any] = {
        "namespace": namespace,
        "studio_name": args.studio_name,
        "sdk_type": sdk_type,
        "urls": urls,
        "studio_token": token,
    }
    result.update(
        _run_fast_verification(
            sdk_type=sdk_type,
            urls=urls,
            timeout=args.request_timeout,
        )
    )
    if args.verify_mode == "browser":
        result["browser"] = _browser_check(urls["share_url"], timeout_seconds=args.browser_timeout)
    return result


def _logs(args: argparse.Namespace) -> dict[str, Any]:
    access_key = _read_access_key(args.access_key, args.access_key_env)
    client = ModelScopeStudioClient(access_key, endpoint=args.endpoint)
    client.login()
    namespace = args.namespace or client.username
    if not namespace:
        raise DeploymentError("Namespace is required and could not be derived from the login response.")
    logs = client.get_logs(namespace, args.studio_name)
    if args.tail is not None and args.tail >= 0:
        logs = logs[-args.tail :]
    return {
        "namespace": namespace,
        "studio_name": args.studio_name,
        "line_count": len(logs),
        "logs": logs,
    }


def _checkout(args: argparse.Namespace) -> dict[str, Any]:
    access_key = _read_access_key(args.access_key, args.access_key_env)
    client = ModelScopeStudioClient(access_key, endpoint=args.endpoint)
    client.login()
    namespace = args.namespace or client.username
    if not namespace:
        raise DeploymentError("Namespace is required and could not be derived from the login response.")
    detail = client.get_studio(namespace, args.studio_name)
    if detail is None:
        raise DeploymentError(f"Studio does not exist: {namespace}/{args.studio_name}")

    worktree = Path(args.worktree) if args.worktree else _default_worktree(namespace, args.studio_name)
    repo_dir = _ensure_repo(
        endpoint=args.endpoint,
        namespace=namespace,
        studio_name=args.studio_name,
        access_key=access_key,
        worktree=worktree,
    )
    head = _run(["git", "rev-parse", "HEAD"], cwd=repo_dir)
    status = _run(["git", "status", "--porcelain"], cwd=repo_dir)
    return {
        "namespace": namespace,
        "studio_name": args.studio_name,
        "worktree": str(repo_dir),
        "commit": head.stdout.strip(),
        "dirty": bool(status.stdout.strip()),
        "sdk_version": detail.get("SdkVersion"),
    }


def _secrets_list(args: argparse.Namespace) -> dict[str, Any]:
    access_key = _read_access_key(args.access_key, args.access_key_env)
    client = ModelScopeStudioClient(access_key, endpoint=args.endpoint)
    client.login()
    namespace = args.namespace or client.username
    if not namespace:
        raise DeploymentError("Namespace is required and could not be derived from the login response.")
    envs = client.list_envs(namespace, args.studio_name)
    return {
        "namespace": namespace,
        "studio_name": args.studio_name,
        "environment_variables": [_sanitize_env_entry(entry) for entry in envs],
        "total_count": len(envs),
    }


def _secrets_upsert(args: argparse.Namespace) -> dict[str, Any]:
    access_key = _read_access_key(args.access_key, args.access_key_env)
    client = ModelScopeStudioClient(access_key, endpoint=args.endpoint)
    client.login()
    namespace = args.namespace or client.username
    if not namespace:
        raise DeploymentError("Namespace is required and could not be derived from the login response.")

    if args.value is not None:
        secret_spec = SecretSpec(name=args.name, value=args.value, source="literal")
    else:
        if args.value_from_env not in os.environ:
            raise DeploymentError(f"Environment variable {args.value_from_env} is not set.")
        secret_spec = SecretSpec(
            name=args.name,
            value=os.environ[args.value_from_env],
            source=f"env:{args.value_from_env}",
        )

    applied = client.apply_envs(namespace, args.studio_name, [secret_spec])
    return {
        "namespace": namespace,
        "studio_name": args.studio_name,
        "secret": applied[0],
    }


def _secrets_delete(args: argparse.Namespace) -> dict[str, Any]:
    access_key = _read_access_key(args.access_key, args.access_key_env)
    client = ModelScopeStudioClient(access_key, endpoint=args.endpoint)
    client.login()
    namespace = args.namespace or client.username
    if not namespace:
        raise DeploymentError("Namespace is required and could not be derived from the login response.")
    result = client.delete_env(namespace, args.studio_name, args.name)
    return {
        "namespace": namespace,
        "studio_name": args.studio_name,
        "secret": result,
    }


def _add_common_auth_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--access-key", help="ModelScope access key. Defaults to MODELSCOPE_ACCESS_KEY.")
    parser.add_argument(
        "--access-key-env",
        default=DEFAULT_ACCESS_KEY_ENV,
        help=f"Environment variable used when --access-key is omitted. Default: {DEFAULT_ACCESS_KEY_ENV}",
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help=f"ModelScope endpoint. Default: {DEFAULT_ENDPOINT}")
    parser.add_argument("--namespace", help="Studio namespace. Defaults to the logged-in username.")
    parser.add_argument("--studio-name", required=True, help="Studio name.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, update, start, and verify a ModelScope Studio app.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    deploy = subparsers.add_parser("deploy", help="Create or reuse a studio, push files, start it, and verify it.")
    _add_common_auth_flags(deploy)
    deploy.add_argument("--source-dir", required=True, help="Directory whose contents should be copied into the studio repo.")
    deploy.add_argument(
        "--reuse-mode",
        default="create-or-reuse",
        choices=["create-or-reuse", "must-exist", "must-create"],
        help="How to handle an existing studio.",
    )
    deploy.add_argument(
        "--sdk-version",
        default="default",
        help="SDK version to create with. Use 'default' to query the current platform default.",
    )
    deploy.add_argument(
        "--sdk-type",
        default=DEFAULT_SDK_TYPE,
        choices=SUPPORTED_SDK_TYPES,
        help=f"Studio SDK type used on creation. Default: {DEFAULT_SDK_TYPE}",
    )
    deploy.add_argument("--instance-type-id", type=int, help="Override the instance type id used during studio creation.")
    deploy.add_argument("--instance-number", type=int, default=1, help="Studio instance count used during studio creation.")
    deploy.add_argument("--visibility", type=int, default=1, help="ModelScope visibility int. Public is currently 1.")
    deploy.add_argument(
        "--worktree",
        help="Existing git worktree to reuse. Defaults to ~/.cache/codex-modelscope-studios/<namespace>-<studio>.",
    )
    deploy.add_argument(
        "--ephemeral-worktree",
        action="store_true",
        help="Use a temporary clone and delete it after the deployment completes.",
    )
    deploy.add_argument(
        "--sync-delete",
        action="store_true",
        help="Delete repo files that are absent from --source-dir. Default behavior only overlays changes.",
    )
    deploy.add_argument(
        "--commit-message",
        default="Deploy ModelScope Studio app via Codex skill",
        help="Git commit message used when repo contents changed.",
    )
    deploy.add_argument(
        "--start-mode",
        default="reset-restart",
        choices=["reset-restart", "skip"],
        help="Whether to trigger the instance start after pushing.",
    )
    deploy.add_argument(
        "--verify-mode",
        default=DEFAULT_VERIFY_MODE,
        choices=["none", "config", "browser"],
        help="How to verify the final deployment.",
    )
    deploy.add_argument(
        "--secret",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Add or update a Studio secret before restart. May be repeated.",
    )
    deploy.add_argument(
        "--secret-from-env",
        action="append",
        default=[],
        metavar="REMOTE_NAME=LOCAL_ENV",
        help="Add or update a Studio secret from a local environment variable. May be repeated.",
    )
    deploy.add_argument("--wait-timeout", type=int, default=900, help="Seconds to wait for the studio to reach Running.")
    deploy.add_argument("--poll-interval", type=int, default=10, help="Polling interval in seconds while waiting.")
    deploy.add_argument("--request-timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP timeout used for config verification.")
    deploy.add_argument("--browser-timeout", type=int, default=45, help="Seconds allowed for browser verification.")
    deploy.set_defaults(handler=_deploy)

    info = subparsers.add_parser("info", help="Fetch studio detail plus a fresh tokenized access URL.")
    _add_common_auth_flags(info)
    info.set_defaults(handler=_info)

    start = subparsers.add_parser("start", help="Trigger reset_restart and wait for Running.")
    _add_common_auth_flags(start)
    start.add_argument("--wait-timeout", type=int, default=900, help="Seconds to wait for Running.")
    start.add_argument("--poll-interval", type=int, default=10, help="Polling interval in seconds while waiting.")
    start.set_defaults(handler=_start)

    verify = subparsers.add_parser("verify", help="Verify a running studio and return a tokenized access URL.")
    _add_common_auth_flags(verify)
    verify.add_argument(
        "--verify-mode",
        default=DEFAULT_VERIFY_MODE,
        choices=["config", "browser"],
        help="Verification depth to run.",
    )
    verify.add_argument("--request-timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP timeout used for config verification.")
    verify.add_argument("--browser-timeout", type=int, default=45, help="Seconds allowed for browser verification.")
    verify.set_defaults(handler=_verify)

    logs = subparsers.add_parser("logs", help="Fetch recent runtime logs.")
    _add_common_auth_flags(logs)
    logs.add_argument("--tail", type=int, default=200, help="Number of log lines to keep from the end.")
    logs.set_defaults(handler=_logs)

    checkout = subparsers.add_parser("checkout", help="Clone or update the Studio git repo into a local worktree.")
    _add_common_auth_flags(checkout)
    checkout.add_argument(
        "--worktree",
        help="Local worktree path. Defaults to ~/.cache/codex-modelscope-studios/<namespace>-<studio>.",
    )
    checkout.set_defaults(handler=_checkout)

    secrets = subparsers.add_parser("secrets", help="Manage Studio environment variables.")
    secret_subparsers = secrets.add_subparsers(dest="secrets_command", required=True)

    secrets_list = secret_subparsers.add_parser("list", help="List Studio environment variables without secret values.")
    _add_common_auth_flags(secrets_list)
    secrets_list.set_defaults(handler=_secrets_list)

    secrets_upsert = secret_subparsers.add_parser("upsert", help="Add or update a Studio environment variable.")
    _add_common_auth_flags(secrets_upsert)
    secrets_upsert.add_argument("--name", required=True, help="Environment variable name.")
    value_group = secrets_upsert.add_mutually_exclusive_group(required=True)
    value_group.add_argument("--value", help="Literal environment variable value.")
    value_group.add_argument("--value-from-env", help="Read the secret value from a local environment variable.")
    secrets_upsert.set_defaults(handler=_secrets_upsert)

    secrets_delete = secret_subparsers.add_parser("delete", help="Delete a Studio environment variable by name.")
    _add_common_auth_flags(secrets_delete)
    secrets_delete.add_argument("--name", required=True, help="Environment variable name.")
    secrets_delete.set_defaults(handler=_secrets_delete)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        result = args.handler(args)
    except DeploymentError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(_json_dump(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
