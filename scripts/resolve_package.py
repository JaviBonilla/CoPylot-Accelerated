"""Resolve an immutable package artifact from a successful GitHub Actions Build."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess


BUILDS = {
    "build-linux-cpu.yml": ("cpu", ("linux-x86_64",)),
    "build-linux-cuda.yml": ("cuda", ("linux-x86_64",)),
    "build-windows-cpu.yml": ("cpu", ("windows-x86_64",)),
    "build-macos-cpu.yml": ("cpu", ("macos-x86_64", "macos-arm64")),
}


def api(path, collection=None):
    args = ["--paginate", "--slurp"] if collection else []
    response = json.loads(subprocess.check_output(["gh", "api", *args, path]))
    if collection:
        return [item for page in response for item in page[collection]]
    return response


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def resolve(repo, workflow, override="", *, request=api):
    backend, platforms = BUILDS[workflow]
    base = f"repos/{repo}/actions"
    if override:
        if not re.fullmatch(r"[1-9][0-9]*", override):
            raise ValueError("The optional Build Run ID must be a positive integer")
        runs = [request(f"{base}/runs/{override}")]
    else:
        runs = request(f"{base}/workflows/{workflow}/runs?"
                       "branch=main&event=workflow_dispatch&status=success&per_page=100", "workflow_runs")

    now = datetime.now(timezone.utc)
    candidates = []
    rejected = []
    for run in runs:
        run_id = run.get("id")
        attempt = run.get("run_attempt")
        revision = run.get("head_sha") or ""
        path = (run.get("path") or "").split("@", 1)[0]
        if (not isinstance(run_id, int) or run_id < 1
                or (override and str(run_id) != override)
                or (run.get("head_repository") or {}).get("full_name", "").lower() != repo.lower()
                or path != f".github/workflows/{workflow}" or run.get("head_branch") != "main"
                or run.get("event") != "workflow_dispatch"
                or (run.get("status"), run.get("conclusion")) != ("completed", "success")
                or not isinstance(attempt, int) or attempt < 1
                or not re.fullmatch(r"[0-9a-f]{40}", revision)):
            rejected.append(f"run {run_id} is not a successful main Build of {workflow} with valid provenance")
            continue

        run_path = f"{base}/runs/{run_id}"
        available = request(f"{run_path}/artifacts?per_page=100", "artifacts")
        artifacts = {}
        for platform in platforms:
            name = f"hermite-optics-{backend}-{platform}-{run_id}-{attempt}"
            matches = []
            for artifact in available:
                if (artifact.get("name") != name or artifact.get("expired") is not False
                        or not artifact.get("expires_at") or timestamp(artifact["expires_at"]) <= now):
                    continue
                provenance = artifact.get("workflow_run")
                if provenance is not None and (provenance.get("id"), provenance.get("head_sha"),
                                               provenance.get("head_branch")) != (run_id, revision, "main"):
                    continue
                if isinstance(artifact.get("id"), int) and artifact["id"] > 0:
                    matches.append(artifact["id"])
            if len(matches) != 1:
                rejected.append(f"run {run_id} attempt {attempt} needs one unexpired artifact named {name}")
                break
            artifacts[platform] = {"name": name, "id": str(matches[0])}
        if len(artifacts) != len(platforms):
            continue

        # The runs endpoint does not expose a completion timestamp. Use the last
        # job to finish in this attempt, including the last job in the macOS matrix.
        jobs = request(f"{run_path}/attempts/{attempt}/jobs?per_page=100", "jobs")
        if not jobs or any(job.get("status") != "completed" or not job.get("completed_at") for job in jobs):
            rejected.append(f"run {run_id} attempt {attempt} has no confirmed job completion time")
            continue
        completed = max(timestamp(job["completed_at"]) for job in jobs)
        candidates.append((completed, run_id, attempt, revision, artifacts))

    if not candidates:
        selection = f"Build Run ID {override}" if override else f"{workflow} on main"
        details = "\n".join(rejected[:10])
        raise ValueError(f"No suitable successful Build for {selection}" + (f"\n{details}" if details else ""))

    _, run_id, attempt, revision, artifacts = max(candidates, key=lambda candidate: candidate[:3])
    return {"run_id": run_id, "attempt": attempt, "revision": revision, "artifacts": artifacts}


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    try:
        build = resolve(repo, os.environ["BUILD_WORKFLOW"], os.environ.get("BUILD_RUN_ID", ""))
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from None
    print(f"Build {build['run_id']} attempt {build['attempt']} at {build['revision']}")
    print(f"{os.environ['GITHUB_SERVER_URL']}/{repo}/actions/runs/{build['run_id']}/attempts/{build['attempt']}")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        for key in ("run_id", "attempt", "revision"):
            print(f"{key}={build[key]}", file=output)
        artifact_ids = {}
        for platform, artifact in build["artifacts"].items():
            print(f"{platform}: {artifact['name']} (artifact ID {artifact['id']})")
            artifact_ids[platform] = artifact["id"]
        print(f"artifact_ids={json.dumps(artifact_ids, separators=(',', ':'))}", file=output)


if __name__ == "__main__":
    main()
