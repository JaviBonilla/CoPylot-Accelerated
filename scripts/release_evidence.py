"""Check that one set of native packages has matching build and validation evidence."""

import hashlib
import json
import re
import tarfile
import zipfile

from package_names import WRAPPER, build_artifact_name, native_library, package_identity, package_variant
from release_github import EvidenceError
from resolve_package import BUILDS
from verify_package import archive_files


GLOBAL_WORKFLOW = "build-validate-all.yml"
WORKFLOW_NAMES = {"build-linux-cpu.yml": "Linux · CPU", "build-linux-cuda.yml": "Linux · CUDA",
                  "build-windows-cpu.yml": "Windows · CPU", "build-macos-cpu.yml": "macOS · CPU"}


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def positive_id(value):
    return type(value) is int and value > 0


def checked_json(data):
    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"Duplicate JSON field {key}")
            result[key] = value
        return result

    try:
        return json.loads(data, object_pairs_hook=unique_fields)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise EvidenceError("Invalid JSON evidence") from error


def same_json(actual, expected):
    # Python treats True and 1 as equal. Artifact IDs and attempts must be JSON integers.
    return json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)


def run_identity(run, repo, workflow, run_id, attempt, revision):
    path = (run.get("path") or "").split("@", 1)[0]
    repository = (run.get("head_repository") or {}).get("full_name", "")
    require((run.get("id"), run.get("run_attempt"), run.get("head_sha")) == (run_id, attempt, revision)
            and (path, repository.lower(), run.get("head_branch"), run.get("event"))
            == (f".github/workflows/{workflow}", repo.lower(), "main", "workflow_dispatch"),
            f"Run {run_id} does not match {workflow} attempt {attempt} on main at {revision}")


def successful_run(api, workflow, run_id, attempt, revision, run=None):
    require(positive_id(run_id) and positive_id(attempt) and isinstance(revision, str)
            and re.fullmatch(r"[0-9a-f]{40}", revision), f"Invalid run identity for {workflow}")
    if run is None:
        run = api.request(f"actions/runs/{run_id}")
    run_identity(run, api.repo, workflow, run_id, attempt, revision)
    require((run.get("status"), run.get("conclusion")) == ("completed", "success"),
            f"{workflow} run {run_id} attempt {attempt} is not successful ({run.get('conclusion')})")


def jobs_for(api, run_id, attempt, revision, role, platforms, optional_gpu=False):
    jobs = list(api.items(f"actions/runs/{run_id}/attempts/{attempt}/jobs", "jobs"))

    def record(name, matches, conclusion="success"):
        require(len(matches) == 1, f"Run {run_id} attempt {attempt} needs exactly one {name} job")
        job, = matches
        require(positive_id(job.get("id")) and (job.get("run_id"), job.get("head_sha"),
                job.get("status"), job.get("conclusion")) == (run_id, revision, "completed", conclusion),
                f"Run {run_id} job {name}: expected {conclusion} at {revision}, got {job.get('conclusion')}")
        return {"id": job["id"], "conclusion": conclusion}

    expected = {}
    for platform in platforms:
        name = f"{role} ({platform})" if len(platforms) > 1 else role
        expected[platform] = record(name, [job for job in jobs if job.get("name") == name])
    if role == "runtime":
        expected["resolve"] = record("resolve", [job for job in jobs if job.get("name") == "resolve"])
    gpu = [job for job in jobs if job.get("name") == "gpu"]
    if optional_gpu and gpu:
        expected["gpu"] = record("gpu", gpu, conclusion="skipped")
    require(len(expected) == len(jobs) and len({job["id"] for job in expected.values()}) == len(jobs),
            f"Run {run_id} attempt {attempt} has unexpected or duplicate jobs")
    return expected


def package_files(names, read, identity):
    archive = identity["archive"]
    sidecar = f"{archive}.sha256"
    require(sorted(names) == sorted(["artifact.json", archive, sidecar]), f"Unexpected members for {archive}")
    require(same_json(checked_json(read("artifact.json")), identity), f"Identity mismatch for {archive}")
    data = read(archive)
    digest = hashlib.sha256(data).hexdigest()
    require(read(sidecar).split() == [digest.encode("ascii"), archive.encode("ascii")],
            f"Archive SHA-256 mismatch for {archive}")
    return data, digest


def check_package_metadata(path, identity, backend):
    archive = identity["archive"]
    prefix = archive.removesuffix(".tar.gz").removesuffix(".zip")
    os_name, architecture = identity["platform"].split("-", 1)
    library = native_library(os_name)
    expected = ("BUILD.json", library, WRAPPER, "python/copylot.py")
    try:
        members = [(name.removeprefix(f"{prefix}/"), data) for name, data in archive_files(path)
                   if name.startswith(f"{prefix}/") and name.removeprefix(f"{prefix}/") in expected]
    except (ValueError, tarfile.TarError, zipfile.BadZipFile, OSError, EOFError) as error:
        raise EvidenceError(f"Cannot read the native archive {archive}: {error}") from error
    require(sorted(name for name, _ in members) == sorted(expected),
            f"Missing or duplicate BUILD.json, native library or Python modules in {archive}")
    metadata = checked_json(dict(members)["BUILD.json"])
    variant = package_variant(identity["platform"], backend)
    expected_cuda = ("13.0.88", "89") if backend == "cuda" else ("", "")
    require(isinstance(metadata, dict) and metadata.get("source_dirty_at_configure") is False
            and (metadata.get("source_revision"), metadata.get("os"), metadata.get("architecture"),
                 metadata.get("library"), metadata.get("variant"), metadata.get("cuda_toolkit"),
                 metadata.get("cuda_architecture"))
            == (identity["source_revision"], os_name, architecture, library, variant, *expected_cuda),
            f"Native archive metadata differs from the expected platform, library, backend or source for {archive}")


def validation_receipt(identity, artifact_id, digest, run_id, attempt, revision):
    return {"schema": 1, "package": identity, "build_artifact_id": artifact_id, "sha256": digest,
            "validate_run_id": run_id, "validate_run_attempt": attempt,
            "validation_revision": revision, "status": "success"}


def validation_artifact_name(backend, platform, run_id, attempt):
    return f"package-validation-{backend}-{platform}-{run_id}-{attempt}"


def manifest_name(run_id, attempt):
    return f"build-validate-manifest-{run_id}-{attempt}"


def json_artifact(api, artifact, filename):
    with api.download(artifact) as archive:
        require(archive.namelist() == [filename], f"Artifact {artifact['id']} must contain only {filename}")
        return checked_json(archive.read(filename))


def run_ref(run_id, attempt, revision):
    return {"run_id": run_id, "attempt": attempt, "source_revision": revision}


def collect_build(api, workflow, run_id, attempt, revision, directory):
    successful_run(api, workflow, run_id, attempt, revision)
    backend, platforms = BUILDS[workflow]
    jobs = jobs_for(api, run_id, attempt, revision, "build", platforms)
    packages = {}
    for platform in platforms:
        identity = package_identity(platform, backend, run_id, attempt, revision)
        name = build_artifact_name(backend, platform, run_id, attempt)
        artifact = api.artifact(run_ref(run_id, attempt, revision), name)
        with api.download(artifact) as archive:
            data, digest = package_files(archive.namelist(), archive.read, identity)
        package_dir = directory / str(artifact["id"])
        package_dir.mkdir()
        path = package_dir / identity["archive"]
        path.write_bytes(data)
        check_package_metadata(path, identity, backend)
        packages[f"{platform}-{backend}"] = {
            "build_workflow": workflow, "identity": identity, "artifact_id": artifact["id"],
            "sha256": digest, "validation_status": "pending",
        }
    return {"name": f"Build · {WORKFLOW_NAMES[workflow]}", **run_ref(run_id, attempt, revision),
            "conclusion": "success", "jobs": jobs}, packages


def collect_validation(api, build_workflow, run_id, attempt, revision, packages):
    workflow = build_workflow.replace("build-", "validate-", 1)
    successful_run(api, workflow, run_id, attempt, revision)
    backend, platforms = BUILDS[build_workflow]
    jobs = jobs_for(api, run_id, attempt, revision, "runtime", platforms, optional_gpu=backend == "cuda")
    validated = {}
    for platform in platforms:
        key = f"{platform}-{backend}"
        package = packages[key]
        name = validation_artifact_name(backend, platform, run_id, attempt)
        artifact = api.artifact(run_ref(run_id, attempt, revision), name)
        receipt = json_artifact(api, artifact, "validation.json")
        expected = validation_receipt(package["identity"], package["artifact_id"], package["sha256"],
                                      run_id, attempt, revision)
        require(same_json(receipt, expected),
                f"Validation run {run_id} receipt for {key} does not match the Build artifact and SHA-256")
        validated[key] = {**package, "validate_workflow": workflow, "validation_artifact_id": artifact["id"],
                          "validation_status": "success"}
    return {"name": f"Validate · {WORKFLOW_NAMES[build_workflow]}", **run_ref(run_id, attempt, revision),
            "conclusion": "success", "jobs": jobs}, validated


def new_manifest(repo, run_id, attempt, revision):
    return {"schema": 1, "repository": repo, "global": run_ref(run_id, attempt, revision),
            "status": "incomplete", "cuda_device_execution": "separate",
            "builds": {}, "validations": {}, "packages": {}}


def complete_manifest(api, run, directory):
    run_id, attempt, revision = (run.get(key) for key in ("id", "run_attempt", "head_sha"))
    successful_run(api, GLOBAL_WORKFLOW, run_id, attempt, revision, run=run)
    expected = new_manifest(api.repo, run_id, attempt, revision)
    artifact = api.artifact(expected["global"], manifest_name(run_id, attempt))
    manifest = json_artifact(api, artifact, "manifest.json")
    require(isinstance(manifest, dict) and manifest.get("global") == expected["global"]
            and manifest.get("repository") == api.repo and type(manifest.get("schema")) is int
            and manifest["schema"] == 1
            and manifest.get("status") == "success", f"Global manifest identity or status mismatch for {run_id}")

    for build_workflow in BUILDS:
        validate_workflow = build_workflow.replace("build-", "validate-", 1)
        try:
            build = manifest["builds"][build_workflow]
            validation = manifest["validations"][validate_workflow]
            build_id, build_attempt = build["run_id"], build["attempt"]
            validate_id, validate_attempt = validation["run_id"], validation["attempt"]
        except (KeyError, TypeError) as error:
            raise EvidenceError(f"Global manifest lacks child run evidence for {build_workflow}") from error
        record, packages = collect_build(api, build_workflow, build_id, build_attempt, revision, directory)
        expected["builds"][build_workflow] = record
        record, packages = collect_validation(api, build_workflow, validate_id, validate_attempt, revision, packages)
        expected["validations"][validate_workflow] = record
        expected["packages"].update(packages)
    expected["status"] = "success"
    require(same_json(manifest, expected),
            f"Global manifest for {run_id} differs from the verified runs and artifacts")
    return expected


def check_child_attempts(api, manifest):
    for stage in ("builds", "validations"):
        for workflow, child in manifest[stage].items():
            successful_run(api, workflow, child["run_id"], child["attempt"], child["source_revision"])
