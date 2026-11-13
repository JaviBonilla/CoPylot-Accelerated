"""Orchestrate native package workflows and prepare draft releases from their evidence."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
from tempfile import TemporaryDirectory
import time
from urllib.parse import quote
import zipfile

from package_names import PACKAGE_PREFIX, package_identity
from release_evidence import (
    BUILDS, GLOBAL_WORKFLOW, WORKFLOW_NAMES, check_child_attempts, collect_build, collect_validation,
    complete_manifest, new_manifest, package_files, require, run_identity,
    run_ref, successful_run, validation_receipt,
)
from release_github import ApiError, EvidenceError, GitHub


MANIFEST = Path("build/release-evidence/manifest.json")
RECEIPT = Path("build/package-validation/validation.json")
RELEASE_PLATFORMS = {
    "linux-x86_64": "Linux x86-64",
    "windows-x86_64": "Windows x86-64",
    "macos-x86_64": "macOS Intel (x86-64)",
    "macos-arm64": "macOS Apple Silicon (arm64)",
}
NUMERIC = r"(?:0|[1-9][0-9]*)"
IDENTIFIER = rf"(?:{NUMERIC}|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
SEMVER = re.compile(rf"v?{NUMERIC}\.{NUMERIC}\.{NUMERIC}"
                    rf"(?:-(?P<prerelease>{IDENTIFIER}(?:\.{IDENTIFIER})*))?"
                    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")


def parse_version(text):
    match = SEMVER.fullmatch(text)
    require(match is not None, "version must be SemVer, for example v0.1.0 or v0.1.0-rc1")
    return "v" + text.removeprefix("v"), match["prerelease"] is not None


def summary(text):
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a", encoding="utf-8") as stream:
            print(text, file=stream)


def write_json(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def emit_receipt():
    # The composite runs this only after the native validator succeeded.
    run_id, attempt, artifact_id = (int(os.environ[key])
                                   for key in ("BUILD_RUN_ID", "BUILD_ATTEMPT", "BUILD_ARTIFACT_ID"))
    identity = package_identity(os.environ["PACKAGE_PLATFORM"], os.environ["PACKAGE_BACKEND"],
                                run_id, attempt, os.environ["BUILD_REVISION"])
    directory = Path("build/selected-artifact")
    _, digest = package_files([path.name for path in directory.iterdir()],
                              lambda name: (directory / name).read_bytes(), identity)
    receipt = validation_receipt(identity, artifact_id, digest, int(os.environ["GITHUB_RUN_ID"]),
                                 int(os.environ["GITHUB_RUN_ATTEMPT"]), os.environ["GITHUB_WORKFLOW_SHA"])
    write_json(RECEIPT, receipt)


def check_main_revision(api, revision):
    current = api.request("git/ref/heads/main")["object"]["sha"]
    require(current == revision, f"main moved to {current}; dispatch a fresh global run at the desired revision")


def wait_for_wave(api, records, revision, *, minutes, checkpoint):
    started = time.monotonic()
    pending = set(records)
    while pending:
        for workflow in sorted(pending):
            record = records[workflow]
            run_id = record["run_id"]
            try:
                run = api.request(f"actions/runs/{run_id}")
            except ApiError as error:
                if error.status == 404 and time.monotonic() - started < 90:
                    continue  # A newly dispatched run can take time to appear.
                raise
            run_identity(run, api.repo, workflow, run_id, record["attempt"], revision)
            if run["status"] == "completed":
                record["conclusion"] = run["conclusion"]
                pending.remove(workflow)
                checkpoint()
                if record["conclusion"] != "success":
                    jobs = api.items(f"actions/runs/{run_id}/attempts/{record['attempt']}/jobs", "jobs")
                    record["job_conclusions"] = {job["name"]: job["conclusion"] for job in jobs}
                    checkpoint()
        if pending:
            elapsed = time.monotonic() - started
            require(elapsed < 60 * minutes,
                    "Timed out waiting for " + ", ".join(f"{workflow} ({records[workflow]['run_id']})"
                                                        for workflow in sorted(pending)))
            time.sleep(15)
    failed = [f"{workflow} ({child['run_id']}): {child['conclusion']}"
              for workflow, child in records.items() if child["conclusion"] != "success"]
    require(not failed, "Unsuccessful child runs: " + ", ".join(failed))


def orchestration_summary(api, manifest):
    global_run = manifest["global"]
    lines = ["## Build & Validate · All", f"Source revision `{global_run['source_revision']}`",
             "", "| Workflow | Run | Conclusion |", "| --- | --- | --- |"]
    for stage in ("builds", "validations"):
        for workflow, child in manifest[stage].items():
            url = api.run_url(child["run_id"], child["attempt"])
            name = child.get("name", workflow)
            lines.append(f"| {name} | [{child['run_id']}]({url}) | {child['conclusion'] or 'pending'} |")
    for stage in ("builds", "validations"):
        for child in manifest[stage].values():
            if jobs := child.get("job_conclusions"):
                details = ", ".join(f"{name}: {conclusion}" for name, conclusion in jobs.items())
                lines += ["", f"Jobs in run {child['run_id']}: {details}."]
    if manifest["packages"]:
        lines += ["", "| Package | Build artifact ID | Validation |", "| --- | --- | --- |"]
        lines += [f"| {key} | {package['artifact_id']} | {package['validation_status']} |"
                  for key, package in manifest["packages"].items()]
    if error := manifest.get("error"):
        lines += ["", f"Failed: {error}"]
    lines += ["", "Linux CUDA used hosted cross-distribution CPU/load checks. GPU execution is a separate check."]
    summary("\n".join(lines))


def orchestrate(api):
    revision = os.environ["GITHUB_SHA"]
    manifest = new_manifest(api.repo, int(os.environ["GITHUB_RUN_ID"]),
                            int(os.environ["GITHUB_RUN_ATTEMPT"]), revision)

    def checkpoint():
        write_json(MANIFEST, manifest)

    def dispatch(workflow, stage, inputs=None):
        run_id = api.dispatch(workflow, inputs)
        build = workflow if stage == "builds" else workflow.replace("validate-", "build-", 1)
        name = f"{'Build' if stage == 'builds' else 'Validate'} · {WORKFLOW_NAMES[build]}"
        manifest[stage][workflow] = {"name": name, **run_ref(run_id, 1, revision), "conclusion": None}
        checkpoint()
        print(f"{workflow}: {api.run_url(run_id)}", flush=True)

    checkpoint()
    try:
        require(os.environ["GITHUB_REF"] == "refs/heads/main", "Run this workflow from main")
        check_main_revision(api, revision)
        # Submit the entire wave before waiting so GitHub can schedule child jobs concurrently.
        for workflow in BUILDS:
            dispatch(workflow, "builds")
        wait_for_wave(api, manifest["builds"], revision, minutes=75, checkpoint=checkpoint)
        with TemporaryDirectory() as temp:
            for workflow, child in manifest["builds"].items():
                record, packages = collect_build(api, workflow, child["run_id"], child["attempt"], revision,
                                                 Path(temp))
                manifest["builds"][workflow] = record
                manifest["packages"].update(packages)
                checkpoint()

        check_main_revision(api, revision)
        for workflow, child in manifest["builds"].items():
            inputs = {"build_run_id": str(child["run_id"])}
            if BUILDS[workflow][0] == "cuda":
                inputs["run_gpu"] = "false"
            dispatch(workflow.replace("build-", "validate-", 1), "validations", inputs)
        wait_for_wave(api, manifest["validations"], revision, minutes=45, checkpoint=checkpoint)
        for workflow, child in manifest["validations"].items():
            record, packages = collect_validation(api, workflow.replace("validate-", "build-", 1),
                                                  child["run_id"], child["attempt"], revision, manifest["packages"])
            manifest["validations"][workflow] = record
            manifest["packages"].update(packages)
            checkpoint()
        check_child_attempts(api, manifest)
        manifest["status"] = "success"
    except KeyboardInterrupt:
        manifest.update(status="cancelled", error="Parent cancelled; dispatched child runs may still be active")
        raise
    except (ValueError, ApiError, OSError, zipfile.BadZipFile, KeyError, TypeError) as error:
        manifest.update(status="failure", error=str(error))
        raise
    finally:
        for package in manifest["packages"].values():
            if package["validation_status"] == "pending":
                package["validation_status"] = "unverified"
        checkpoint()
        orchestration_summary(api, manifest)


def select_global(api, override, directory):
    if override:
        require(re.fullmatch(r"[1-9][0-9]*", override), "build_validate_run_id must be a positive integer")
        run = api.request(f"actions/runs/{override}")
        require(run.get("id") == int(override), "GitHub returned a different global run ID")
        return complete_manifest(api, run, directory)

    candidates = api.items(f"actions/workflows/{GLOBAL_WORKFLOW}/runs?"
                           "branch=main&event=workflow_dispatch&status=success", "workflow_runs")
    for candidate in candidates:
        run_id = candidate["id"]
        try:
            # Re-read the run in case it was rerun after it appeared in the listing.
            run = api.request(f"actions/runs/{run_id}")
            return complete_manifest(api, run, directory)
        except (EvidenceError, zipfile.BadZipFile, EOFError) as error:
            print(f"Skipping global run {run_id}: {error}", flush=True)
        except ApiError as error:
            if error.status not in {404, 410}:
                raise
            print(f"Skipping global run {run_id}: required evidence is unavailable ({error})", flush=True)
        for path in directory.iterdir():
            shutil.rmtree(path)
    raise EvidenceError("No successful global run has a complete available manifest and five validated packages")


def find_tag(api, version):
    try:
        return api.request(f"git/ref/tags/{quote(version, safe='')}")
    except ApiError as error:
        if error.status == 404:
            return None
        raise


def check_version_available(api, version):
    require(find_tag(api, version) is None, f"Tag {version} already exists")
    require(not any(release.get("tag_name") == version for release in api.items("releases")),
            f"Release or draft {version} already exists")


def stage_assets(manifest, version, directory):
    assets = directory / "assets"
    assets.mkdir()
    filenames = {}
    # GitHub may normalize punctuation in asset filenames. Keep + in the tag only.
    asset_version = version.replace("+", "_")
    for key, package in manifest["packages"].items():
        identity = package["identity"]
        source = directory / str(package["artifact_id"]) / identity["archive"]
        extension = ".zip" if source.suffix == ".zip" else ".tar.gz"
        target = assets / f"{PACKAGE_PREFIX}-{asset_version}-{key}{extension}"
        shutil.copyfile(source, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        require(digest == package["sha256"], f"Staged asset SHA-256 mismatch for {key}")
        filenames[key] = target.name
    checksums = assets / "SHA256SUMS.txt"
    checksums.write_text("".join(f"{manifest['packages'][key]['sha256']}  {name}\n"
                                for key, name in sorted(filenames.items())), encoding="ascii", newline="\n")
    return assets, filenames


def release_notes(api, manifest, version, filenames):
    global_run = manifest["global"]
    revision = global_run["source_revision"]
    repository = f"{api.server}/{api.repo}"
    download_base = f"{repository}/releases/download/{quote(version, safe='')}"
    source_docs = f"{repository}/blob/{revision}"
    run_url = api.run_url(global_run["run_id"], global_run["attempt"])
    downloads = []
    provenance = []
    for key, filename in filenames.items():
        platform, backend = key.rsplit("-", 1)
        target = RELEASE_PLATFORMS[platform]
        package = manifest["packages"][key]
        build = manifest["builds"][package["build_workflow"]]
        validation = manifest["validations"][package["validate_workflow"]]
        build_id, validate_id = build["run_id"], validation["run_id"]
        build_url = api.run_url(build_id, build["attempt"])
        validate_url = api.run_url(validate_id, validation["attempt"])
        artifact = package["artifact_id"]
        record = package["validation_artifact_id"]
        downloads.append(f"| {target} | {backend.upper()} | "
                         f"[{filename}]({download_base}/{quote(filename, safe='')}) |")
        provenance.append(f"| {target} · {backend.upper()} | [{build_id}]({build_url}) · "
                          f"[artifact {artifact}]({api.run_url(build_id)}/artifacts/{artifact}) | "
                          f"[{validate_id}]({validate_url}) · "
                          f"[record {record}]({api.run_url(validate_id)}/artifacts/{record}) |")
    lines = [
        "## Overview",
        "",
        "SolarPILOT(TM) is the original scientific software for optical simulation of concentrating solar "
        "power towers, and CoPylot is its Python API. CoPylot-Accelerated evaluates heliostat-field optics "
        "and receiver flux. It retains the original CPU calculation paths in a patched build as a numerical "
        "reference and adds three accelerated implementations. "
        "All four modes use the same Hermite optical formulation. The project builds on the original software "
        "from Alliance for Sustainable Energy, LLC, and uses SSC and SolTrace. "
        "[Original SolarPILOT(TM) project](https://github.com/NatLabRockies/SolarPILOT)",
        "",
        "| Mode | Description |",
        "| --- | --- |",
        "| Original SolarPILOT/CoPylot | Retained original image-plane and receiver-flux paths on one CPU thread |",
        "| Refactored CPU | Optimized single-threaded CPU implementation |",
        "| Multicore CPU | Parallel CPU implementation |",
        "| CUDA GPU | Accelerated image-plane evaluation and receiver flux accumulation on supported NVIDIA hardware |",
        "",
        "## Downloads",
        "",
        "| Platform | Backend | Download |",
        "| --- | --- | --- |",
        *downloads,
        "",
        f"[Download SHA256SUMS.txt]({download_base}/SHA256SUMS.txt) to verify the archives.",
        "",
        "## Quick start",
        "",
        "Download the archive for your platform and extract it. From the directory containing `requirements.txt` "
        "and `example.py`, create a virtual environment with the recommended Python 3.12, install the pinned "
        "requirements, and run the synthetic example.",
        "",
        "**Linux and macOS**",
        "",
        "```sh",
        "python3.12 -m venv .venv",
        ".venv/bin/python -m pip install -r requirements.txt",
        ".venv/bin/python example.py --mode refactored",
        "```",
        "",
        "**Windows PowerShell**",
        "",
        "```powershell",
        "py -3.12 -m venv .venv",
        r".\.venv\Scripts\python.exe -m pip install -r requirements.txt",
        r".\.venv\Scripts\python.exe example.py --mode refactored",
        "```",
        "",
        "Use the same interpreter with `--mode multicore --compare` or `--mode original --compare`. "
        "Original requires `diagnostics: true` in `BUILD.json`. Use `--mode cuda --compare` with the CUDA "
        "package and a compatible GPU.",
        "",
        "## Requirements",
        "",
        "The virtual environment manages Python packages. Native runtimes such as glibc, Visual C++ and CUDA "
        "are provided by the host.",
        "",
        "- **Linux x86-64.** glibc 2.34 or later and a C++ runtime providing `GLIBCXX_3.4.29` and "
        "`CXXABI_1.3.13`. Host validation covered Ubuntu 22.04 and 24.04, Debian 12 and AlmaLinux 9.",
        "- **Linux CUDA.** Install NVIDIA CUDA Runtime 13.0.88 (`libcudart.so.13`) separately, including "
        "for CPU modes. Device execution requires an SM 89 NVIDIA GPU and Linux driver 580.82.07 or newer.",
        "- **Windows x86-64.** Install the x64 Visual C++ runtime.",
        "- **macOS.** Use macOS 15 or later and a Python interpreter matching the Intel or Apple Silicon archive. "
        "Signing and notarization are outside the validation scope.",
        "",
        "## Source and validation",
        "",
        f"[Source commit `{revision}`]({repository}/tree/{revision}) · "
        f"[Build & Validate run {global_run['run_id']}]({run_url})",
        "",
        "The hosted CUDA job checks library loading and CPU modes. GPU execution was verified separately on "
        f"an RTX 6000 Ada with an [earlier portable archive]({source_docs}/docs/packaging.md"
        "#gpu-execution-of-the-reference-archive).",
        "",
        "On Apple Silicon, Original's receiver map is compared with each optimized mode using "
        "`rtol=1e-15` and `atol=1e-15 kW/m²` per cell. Refactored and Multicore maps, all receiver "
        "summaries and all per-heliostat outputs agree bitwise in the synthetic check.",
        "",
        "<details>",
        "<summary>Build and validation provenance by platform</summary>",
        "",
        "| Target | Build | Validation |",
        "| --- | --- | --- |",
        *provenance,
        "",
        "</details>",
        "",
        "Each archive includes its license texts and upstream notices. See the "
        f"[third-party notices]({source_docs}/THIRD_PARTY_NOTICES) and "
        f"[licensing inventory]({source_docs}/docs/licensing-inventory.json) for attribution and terms.",
    ]
    return "\n".join(lines) + "\n"


def publish_draft(api, version, prerelease, manifest, assets, notes):
    revision = manifest["global"]["source_revision"]
    release = api.request("releases", payload={"tag_name": version, "target_commitish": revision,
                                               "name": f"CoPylot-Accelerated {version}", "body": notes,
                                               "draft": True, "prerelease": prerelease})
    release_id = release["id"]
    link = release.get("html_url") or f"{api.server}/{api.repo}/releases"
    try:
        require(release.get("draft") is True and release.get("tag_name") == version
                and release.get("target_commitish") == revision,
                f"GitHub returned unexpected draft metadata for {version}")
        expected = {}
        for path in sorted(assets.iterdir(), key=lambda item: (item.name == "SHA256SUMS.txt", item.name)):
            expected[path.name] = (path.stat().st_size, f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}")
            try:
                uploaded = api.upload(release, path)
            except ApiError as error:
                raise EvidenceError(f"Could not upload {path.name}: {error}") from error
            require(uploaded.get("name") == path.name and uploaded.get("state") == "uploaded"
                    and (uploaded.get("size"), uploaded.get("digest")) == expected[path.name],
                    f"GitHub did not confirm the name, size and SHA-256 of uploaded asset {path.name}")
        actual = list(api.items(f"releases/{release_id}/assets"))
        require(len(actual) == len(expected)
                and {asset["name"]: (asset["size"], asset["digest"]) for asset in actual
                     if asset.get("state") == "uploaded"} == expected,
                "The draft does not contain exactly the six prepared assets")
        require(api.request(f"releases/{release_id}").get("draft") is True,
                f"Release {version} changed state during asset upload")

        tag = find_tag(api, version)
        if tag is None:
            # Draft creation can defer the Git ref. Create it only after all assets have been checked.
            api.request("git/refs", payload={"ref": f"refs/tags/{version}", "sha": revision})
            tag = find_tag(api, version)
        require(tag and tag["object"]["type"] == "commit" and tag["object"]["sha"] == revision,
                f"Tag {version} does not point to the validated commit {revision}")
    except (EvidenceError, ApiError, OSError, KeyError, TypeError) as error:
        summary(f"Draft preparation failed. [Inspect the draft]({link}) and resolve it before trying {version} again.")
        raise EvidenceError(f"{error}. Inspect draft {link}; no assets or tags will be overwritten automatically") from error
    summary(f"[Draft {version}]({link}) has five verified archives and SHA256SUMS.txt. Tag targets `{revision}`.")
    print(f"Draft {version}: {link}", flush=True)


def create_draft(api):
    require(os.environ["GITHUB_REF"] == "refs/heads/main", "Run this workflow from main")
    version, prerelease = parse_version(os.environ["RELEASE_VERSION"])
    check_version_available(api, version)
    with TemporaryDirectory() as temp:
        directory = Path(temp)
        manifest = select_global(api, os.environ.get("GLOBAL_RUN_ID", ""), directory)
        assets, filenames = stage_assets(manifest, version, directory)
        notes = release_notes(api, manifest, version, filenames)
        run = manifest["global"]
        successful_run(api, GLOBAL_WORKFLOW, run["run_id"], run["attempt"], run["source_revision"])
        check_child_attempts(api, manifest)
        check_version_available(api, version)
        try:
            publish_draft(api, version, prerelease, manifest, assets, notes)
        except ApiError as error:
            raise EvidenceError(f"{error}. Check Releases for an existing draft of {version} before retrying") from error


def main():
    def on_interrupt(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, on_interrupt)
    try:
        operation, = sys.argv[1:]
        if operation == "receipt":
            emit_receipt()
        else:
            {"orchestrate": orchestrate, "draft": create_draft}[operation](GitHub())
    except KeyboardInterrupt:
        raise SystemExit("Cancelled") from None
    except (ValueError, ApiError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
