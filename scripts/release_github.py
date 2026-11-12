"""GitHub REST operations used by the binary release workflows."""

from datetime import datetime, timezone
import hashlib
from http.client import HTTPException
import io
import json
import os
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import zipfile


class EvidenceError(ValueError):
    """A run or artifact cannot be used as release evidence."""


class ApiError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class GitHub:
    def __init__(self):
        self.repo = os.environ["GITHUB_REPOSITORY"]
        self.server = os.environ["GITHUB_SERVER_URL"]
        self.base = f'{os.environ["GITHUB_API_URL"]}/repos/{self.repo}'
        self.token = os.environ["GITHUB_TOKEN"]

    def request(self, path, *, payload=None, upload=None, version="2026-03-10", binary=False):
        url = path if upload is not None else f"{self.base}/{path}"
        label = urlsplit(url).path
        content = upload if upload is not None else (json.dumps(payload).encode() if payload is not None else None)
        method = "GET" if content is None else "POST"
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": version}
        if content is not None:
            headers["Content-Type"] = "application/octet-stream" if upload is not None else "application/json"
        request = Request(url, content, headers, method=method)
        # Download redirects use a short-lived signed URL. Keep the token on the API origin.
        request.add_unredirected_header("Authorization", f"Bearer {self.token}")
        for attempt in range(4):
            try:
                with urlopen(request, timeout=30) as response:
                    data = response.read()
                return data if binary else json.loads(data) if data else None
            except (json.JSONDecodeError, UnicodeError):
                raise ApiError(f"{method} {label}: GitHub returned invalid JSON") from None
            except HTTPError as error:
                status = error.code
                retry_after = error.headers.get("Retry-After")
                reset = error.headers.get("X-RateLimit-Reset")
                message = b""
                if status == 403 and error.fp is not None:
                    message = error.read(4096).lower()
                rate_limited = (status == 429 or (status == 403 and
                                (retry_after or error.headers.get("X-RateLimit-Remaining") == "0"
                                 or b"secondary rate limit" in message)))
                error.close()
                delay = 2 ** attempt
                if rate_limited:
                    if retry_after and retry_after.isdecimal():
                        delay = int(retry_after)
                    elif reset and reset.isdecimal() and error.headers.get("X-RateLimit-Remaining") == "0":
                        delay = max(1, int(reset) - int(time.time()) + 1)
                    else:
                        delay = 60
                if attempt < 3 and delay <= 60 and (rate_limited or (method == "GET" and status >= 500)):
                    time.sleep(delay)
                    continue
                reason = " (rate limited; retry later)" if rate_limited else ""
                raise ApiError(f"{method} {label}: HTTP {status}{reason}", status) from None
            except (OSError, HTTPException) as error:
                # Writes with an ambiguous outcome must never be retried automatically.
                if method == "GET" and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise ApiError(f"{method} {label}: {type(error).__name__}; check connectivity and GitHub status") from None

    def items(self, path, key=None):
        separator = "&" if "?" in path else "?"
        for page in range(1, 101):
            response = self.request(f"{path}{separator}per_page=100&page={page}")
            entries = response[key] if key else response
            yield from entries
            if len(entries) < 100:
                return
        raise ApiError(f"Pagination limit reached for {path}")

    def dispatch(self, workflow, inputs=None):
        body = {"ref": "main", "return_run_details": True}
        if inputs is not None:
            body["inputs"] = inputs
        # This API version exposes the explicit return_run_details option.
        result = self.request(f"actions/workflows/{workflow}/dispatches",
                              payload=body, version="2022-11-28")
        run_id = (result or {}).get("workflow_run_id")
        if type(run_id) is not int or run_id <= 0:
            raise ApiError(f"{workflow} dispatch returned no run ID; inspect Actions before dispatching again")
        return run_id

    def artifact(self, run, name):
        run_id = run["run_id"]
        matches = [entry for entry in self.items(f"actions/runs/{run_id}/artifacts", "artifacts")
                   if entry.get("name") == name]
        if len(matches) != 1:
            raise EvidenceError(f"Run {run_id} must contain exactly one {name} artifact")
        artifact = matches[0]
        expires = artifact.get("expires_at")
        if artifact.get("expired") is not False or not expires:
            raise EvidenceError(f"Artifact {name} has expired or has no expiration date")
        try:
            expiration = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as error:
            raise EvidenceError(f"Artifact {name} has an invalid expiration date") from error
        if expiration.tzinfo is None or expiration <= datetime.now(timezone.utc):
            raise EvidenceError(f"Artifact {name} has expired")
        provenance = artifact.get("workflow_run")
        if provenance is not None and (provenance.get("id"), provenance.get("head_sha"),
                                       provenance.get("head_branch")) != (run_id, run["source_revision"], "main"):
            raise EvidenceError(f"Artifact {name} has inconsistent run provenance")
        if type(artifact.get("id")) is not int or artifact["id"] <= 0:
            raise EvidenceError(f"Artifact {name} has no valid ID")
        return artifact

    def download(self, artifact):
        artifact_id = artifact["id"]
        data = self.request(f"actions/artifacts/{artifact_id}/zip", binary=True)
        if artifact.get("digest") != f"sha256:{hashlib.sha256(data).hexdigest()}":
            raise EvidenceError(f"Artifact {artifact_id} has a missing or incorrect GitHub SHA-256 digest")
        try:
            return zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as error:
            raise EvidenceError(f"Artifact {artifact_id} is not a valid ZIP") from error

    def upload(self, release, file):
        path = f"{self.base.removeprefix('https://api.github.com')}/releases/{release['id']}/assets"
        expected = f"https://uploads.github.com{path}"
        if release.get("upload_url", "").split("{", 1)[0] != expected:
            raise ApiError("GitHub returned an unexpected release upload endpoint")
        query = urlencode({"name": file.name})
        return self.request(f"{expected}?{query}", upload=file.read_bytes())

    def run_url(self, run_id, attempt=None):
        url = f"{self.server}/{self.repo}/actions/runs/{run_id}"
        return f"{url}/attempts/{attempt}" if attempt else url
