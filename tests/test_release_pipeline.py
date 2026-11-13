import copy
from contextlib import nullcontext, redirect_stdout
import hashlib
import importlib.util
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import sys
import tarfile
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import unquote
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from package_names import package_identity
import release_evidence as evidence
import release_github as github
import release_pipeline as pipeline


SHA = "a" * 40
GLOBAL_ID = 100
ASSET_SUFFIXES = {
    "linux-x86_64-cpu": "linux-x86_64-cpu.tar.gz",
    "linux-x86_64-cuda": "linux-x86_64-cuda.tar.gz",
    "windows-x86_64-cpu": "windows-x86_64-cpu.zip",
    "macos-x86_64-cpu": "macos-x86_64-cpu.tar.gz",
    "macos-arm64-cpu": "macos-arm64-cpu.tar.gz",
}


def zipped(files):
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()


def native_archive(identity, backend, *, library_name=None, omit=None):
    name = identity["archive"]
    root = name.removesuffix(".tar.gz").removesuffix(".zip")
    os_name, architecture = identity["platform"].split("-", 1)
    variant = root.split(identity["platform"] + "-", 1)[1]
    cuda = backend == "cuda"
    library = "lib/copylot_accelerated.dll" if os_name == "windows" else "lib/copylot_accelerated.so"
    metadata = json.dumps({"source_revision": identity["source_revision"], "source_dirty_at_configure": False,
                           "os": os_name, "architecture": architecture, "variant": variant,
                           "library": library if library_name is None else library_name,
                           "cuda_toolkit": "13.0.88" if cuda else "", "cuda_architecture": "89" if cuda else ""})
    files = {"BUILD.json": metadata.encode(), library: b"native fixture",
             "python/copylot_accelerated.py": b"wrapper fixture", "python/copylot.py": b"upstream fixture"}
    if omit:
        del files[omit]
    if name.endswith(".zip"):
        return zipped({f"{root}/{path}": data for path, data in files.items()})
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for path, data in files.items():
            info = tarfile.TarInfo(f"{root}/{path}")
            info.size = len(data)
            archive.addfile(info, BytesIO(data))
    return output.getvalue()


class FakeGitHub(github.GitHub):
    def __init__(self):
        self.repo = "example/optics"
        self.server = "https://github.com"
        self.runs = {}
        self.jobs = {}
        self.artifacts = {}
        self.contents = {}
        self.dispatched = []
        self.writes = []
        self.assets = []
        self.asset_bytes = {}
        self.releases = []
        self.tags = {}
        self.upload_failure = False

    def add_run(self, run_id, workflow):
        self.runs[run_id] = {"id": run_id, "run_attempt": 1, "head_sha": SHA, "head_branch": "main",
                             "head_repository": {"full_name": self.repo}, "event": "workflow_dispatch",
                             "path": f".github/workflows/{workflow}@main",
                             "status": "completed", "conclusion": "success"}
        self.jobs[run_id] = []
        self.artifacts[run_id] = []

    def add_job(self, run_id, name, conclusion="success"):
        self.jobs[run_id].append({"id": 10 * run_id + len(self.jobs[run_id]), "run_id": run_id,
                                  "head_sha": SHA, "name": name, "status": "completed", "conclusion": conclusion})

    def add_artifact(self, run_id, name, files):
        artifact_id = 10 * run_id + len(self.artifacts[run_id])
        data = zipped(files)
        self.contents[artifact_id] = data
        self.artifacts[run_id].append({"id": artifact_id, "name": name, "expired": False,
                                       "expires_at": "2099-01-01T00:00:00Z",
                                       "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                                       "workflow_run": {"id": run_id, "head_sha": SHA, "head_branch": "main"}})
        return artifact_id

    def dispatch(self, workflow, inputs=None):
        run_id = 1000 + len(self.dispatched)
        self.dispatched.append((workflow, inputs))
        self.add_run(run_id, workflow)
        validating = workflow.startswith("validate-")
        build = workflow.replace("validate-", "build-", 1)
        backend, platforms = evidence.BUILDS[build]
        role = "runtime" if validating else "build"
        if validating:
            self.add_job(run_id, "resolve")
        for platform in platforms:
            self.add_job(run_id, f"{role} ({platform})" if len(platforms) > 1 else role)
            build_id = int(inputs["build_run_id"]) if validating else run_id
            identity = package_identity(platform, backend, build_id, 1, SHA)
            name = identity["archive"]
            if validating:
                build_artifact, = [a for a in self.artifacts[build_id] if f"-{platform}-" in a["name"]]
                with self.download(build_artifact) as archive:
                    digest, _ = archive.read(name + ".sha256").decode().split()
                receipt = evidence.validation_receipt(identity, build_artifact["id"], digest, run_id, 1, SHA)
                self.add_artifact(run_id, evidence.validation_artifact_name(backend, platform, run_id, 1),
                                  {"validation.json": json.dumps(receipt)})
            else:
                data = native_archive(identity, backend)
                digest = hashlib.sha256(data).hexdigest()
                self.add_artifact(run_id, f"copylot-accelerated-{backend}-{platform}-{run_id}-1",
                                  {name: data, name + ".sha256": f"{digest}  {name}\n",
                                   "artifact.json": json.dumps(identity)})
        if workflow == "validate-linux-cuda.yml":
            self.add_job(run_id, "gpu", "skipped")
        return run_id

    def request(self, path, *, payload=None, binary=False):
        if path == "git/ref/heads/main":
            return {"object": {"sha": SHA}}
        if path.startswith("actions/runs/"):
            return copy.deepcopy(self.runs[int(path.split("/")[2])])
        if path.startswith("actions/artifacts/"):
            self.assert_binary(binary)
            return self.contents[int(path.split("/")[2])]
        if path == "releases" and payload:
            self.writes.append((path, payload))
            release = {**payload, "id": 99, "html_url": self.server + "/example/optics/releases/draft"}
            self.releases.append(release)
            return release
        if path == "releases/99":
            return self.releases[-1]
        if path.startswith("git/ref/tags/"):
            name = unquote(path.split("/")[-1])
            if name not in self.tags:
                raise github.ApiError("Tag not found", 404)
            return {"object": {"type": "commit", "sha": self.tags[name]}}
        if path == "git/refs" and payload:
            self.writes.append((path, payload))
            self.tags[payload["ref"].removeprefix("refs/tags/")] = payload["sha"]
            return {}
        raise AssertionError(path)

    @staticmethod
    def assert_binary(value):
        if value is not True:
            raise AssertionError("Expected binary download")

    def items(self, path, key=None):
        if key == "workflow_runs":
            globals_ = (run for run in self.runs.values() if evidence.GLOBAL_WORKFLOW in run["path"])
            return iter(sorted(globals_, key=lambda run: run["id"], reverse=True))
        if key == "artifacts":
            return iter(self.artifacts[int(path.split("/")[2])])
        if key == "jobs":
            return iter(self.jobs[int(path.split("/")[2])])
        if path == "releases":
            return iter(self.releases)
        if path == "releases/99/assets":
            return iter(self.assets)
        raise AssertionError(path)

    def upload(self, release, file):
        self.writes.append(("upload", file.name))
        if self.upload_failure:
            raise github.ApiError("Upload HTTP 502", 502)
        data = file.read_bytes()
        self.asset_bytes[file.name] = data
        asset = {"name": file.name, "size": len(data), "state": "uploaded",
                 "digest": "sha256:" + hashlib.sha256(data).hexdigest()}
        self.assets.append(asset)
        return asset


class ReleasePipeline(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.api = FakeGitHub()
        self.api.add_run(GLOBAL_ID, evidence.GLOBAL_WORKFLOW)
        self.manifest_path = self.directory / "manifest.json"
        self.env = {"GITHUB_SHA": SHA, "GITHUB_RUN_ID": str(GLOBAL_ID), "GITHUB_RUN_ATTEMPT": "1",
                    "GITHUB_REF": "refs/heads/main", "GITHUB_STEP_SUMMARY": str(self.directory / "summary.md")}

    def orchestrate(self):
        with (patch.dict(os.environ, self.env), patch.object(pipeline, "MANIFEST", self.manifest_path),
              redirect_stdout(StringIO())):
            pipeline.orchestrate(self.api)
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def upload_manifest(self, manifest, run_id=GLOBAL_ID, attempt=1):
        return self.api.add_artifact(run_id, evidence.manifest_name(run_id, attempt),
                                     {"manifest.json": json.dumps(manifest)})

    def complete_global(self):
        manifest = self.orchestrate()
        self.upload_manifest(manifest)
        return manifest

    def test_global_passes_all_platforms_and_dispatches_exact_run_ids(self):
        manifest = self.complete_global()
        self.assertEqual(manifest["status"], "success")
        self.assertEqual(manifest["cuda_device_execution"], "separate")
        self.assertEqual(len(manifest["packages"]), 5)
        for index, workflow in enumerate(evidence.BUILDS):
            self.assertEqual(self.api.dispatched[index], (workflow, None))
            validate, inputs = self.api.dispatched[index + 4]
            self.assertEqual(validate, workflow.replace("build-", "validate-", 1))
            self.assertEqual(inputs["build_run_id"], str(1000 + index))
            self.assertEqual(inputs.get("run_gpu"), "false" if index == 1 else None)
        self.assertEqual(set(manifest["validations"]["validate-macos-cpu.yml"]["jobs"]),
                         {"resolve", "macos-x86_64", "macos-arm64"})
        expected = self.directory / "download"
        expected.mkdir()
        self.assertEqual(pipeline.select_global(self.api, str(GLOBAL_ID), expected), manifest)
        summary = (self.directory / "summary.md").read_text(encoding="utf-8")
        self.assertTrue(all(f"/actions/runs/{run_id}/attempts/1" in summary for run_id in range(1000, 1008)))

    def test_wrong_revision_stops_before_validation_and_preserves_partial_manifest(self):
        original_dispatch = self.api.dispatch

        def dispatch(*args):
            run_id = original_dispatch(*args)
            self.api.runs[run_id]["head_sha"] = "b" * 40
            return run_id

        with patch.object(self.api, "dispatch", side_effect=dispatch):
            with self.assertRaisesRegex(github.EvidenceError, "does not match"):
                self.orchestrate()
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "failure")
        self.assertEqual(len(manifest["builds"]), 4)
        self.assertEqual(manifest["validations"], {})

    def test_cancelled_child_is_a_failed_wave(self):
        self.api.add_run(200, "build-linux-cpu.yml")
        self.api.runs[200]["conclusion"] = "cancelled"
        records = {"build-linux-cpu.yml": {"run_id": 200, "attempt": 1, "conclusion": None}}
        with self.assertRaisesRegex(github.EvidenceError, "cancelled"):
            pipeline.wait_for_wave(self.api, records, SHA, minutes=1, checkpoint=lambda: None)
        self.assertEqual(records["build-linux-cpu.yml"]["conclusion"], "cancelled")

    def test_timed_out_wave_reports_pending_run(self):
        self.api.add_run(200, "build-linux-cpu.yml")
        self.api.runs[200].update(status="queued", conclusion=None)
        records = {"build-linux-cpu.yml": {"run_id": 200, "attempt": 1, "conclusion": None}}
        with patch.object(pipeline.time, "monotonic", side_effect=[0, 61]):
            with self.assertRaisesRegex(github.EvidenceError, r"Timed out.*200"):
                pipeline.wait_for_wave(self.api, records, SHA, minutes=1, checkpoint=lambda: None)

    def test_missing_macos_architecture_and_reruns_are_rejected(self):
        manifest = self.complete_global()
        directory = self.directory / "download"
        directory.mkdir()
        validate = manifest["validations"]["validate-macos-cpu.yml"]["run_id"]
        self.api.jobs[validate].pop()
        with self.assertRaisesRegex(github.EvidenceError, "macos-arm64"):
            pipeline.select_global(self.api, str(GLOBAL_ID), directory)
        run_id = manifest["builds"]["build-linux-cpu.yml"]["run_id"]
        self.api.runs[run_id]["run_attempt"] = 2
        with TemporaryDirectory() as clean:
            with self.assertRaisesRegex(github.EvidenceError, "attempt 1"):
                pipeline.select_global(self.api, str(GLOBAL_ID), Path(clean))

    def test_rejects_validation_receipt_for_a_different_artifact(self):
        manifest = self.complete_global()
        package = manifest["packages"]["linux-x86_64-cpu"]
        artifact_id = package["validation_artifact_id"]
        with zipfile.ZipFile(BytesIO(self.api.contents[artifact_id])) as archive:
            receipt = json.loads(archive.read("validation.json"))
        receipt["build_artifact_id"] += 1
        data = zipped({"validation.json": json.dumps(receipt)})
        self.api.contents[artifact_id] = data
        validate = manifest["validations"]["validate-linux-cpu.yml"]["run_id"]
        self.api.artifacts[validate][0]["digest"] = "sha256:" + hashlib.sha256(data).hexdigest()
        with TemporaryDirectory() as clean:
            with self.assertRaisesRegex(github.EvidenceError, "does not match the Build artifact"):
                pipeline.select_global(self.api, str(GLOBAL_ID), Path(clean))

    def test_integrity_manifest_zip_and_native_sha_checks(self):
        manifest = self.complete_global()
        global_artifact = self.api.artifacts[GLOBAL_ID][0]
        directory = self.directory / "download"
        directory.mkdir()
        with patch.dict(global_artifact, {"digest": "sha256:" + "0" * 64}):
            with self.assertRaisesRegex(github.EvidenceError, "incorrect GitHub SHA-256"):
                pipeline.select_global(self.api, str(GLOBAL_ID), directory)
        manifest["packages"]["macos-arm64-cpu"]["sha256"] = "0" * 64
        self.api.artifacts[GLOBAL_ID].clear()
        self.upload_manifest(manifest)
        with self.assertRaisesRegex(github.EvidenceError, "differs from the verified runs and artifacts"):
            pipeline.select_global(self.api, str(GLOBAL_ID), directory)
        identity = manifest["packages"]["macos-arm64-cpu"]["identity"]
        name = identity["archive"]
        files = {"artifact.json": json.dumps(identity).encode(), name: b"corrupt", name + ".sha256": b"bad"}
        with self.assertRaisesRegex(github.EvidenceError, "Archive SHA-256 mismatch"):
            evidence.package_files(files.keys(), files.__getitem__, identity)
        with self.assertRaisesRegex(github.EvidenceError, "Duplicate JSON"):
            evidence.checked_json('{"schema": 1, "schema": 2}')

    def test_package_names_and_library_metadata_on_all_targets(self):
        variants = {"linux-x86_64-cpu": "cpu-glibc2.34",
                    "linux-x86_64-cuda": "cuda13.0-sm89-glibc2.34"}
        for key, suffix in ASSET_SUFFIXES.items():
            platform, backend = key.rsplit("-", 1)
            identity = package_identity(platform, backend, 20, 1, SHA)
            ext = "zip" if suffix.endswith(".zip") else "tar.gz"
            variant = variants.get(key, "cpu")
            with self.subTest(target=key):
                self.assertEqual(identity["archive"],
                                 f"copylot-accelerated-local-{SHA[:12]}-{platform}-{variant}.{ext}")
                path = self.directory / identity["archive"]
                path.write_bytes(native_archive(identity, backend))
                evidence.check_package_metadata(path, identity, backend)
                path.write_bytes(native_archive(identity, backend, library_name="lib/wrong.so"))
                with self.assertRaisesRegex(github.EvidenceError, "expected platform, library"):
                    evidence.check_package_metadata(path, identity, backend)
                path.write_bytes(native_archive(identity, backend, omit="python/copylot_accelerated.py"))
                with self.assertRaisesRegex(github.EvidenceError, "Missing or duplicate"):
                    evidence.check_package_metadata(path, identity, backend)

    def test_packaged_wrapper_loads_the_renamed_library_by_absolute_path(self):
        wrapper_path = Path(__file__).resolve().parents[1] / "packaging/copylot_accelerated.py"
        spec = importlib.util.spec_from_file_location("copylot_accelerated", wrapper_path)
        wrapper = importlib.util.module_from_spec(spec)
        upstream = type("UpstreamCoPylot", (), {})
        with patch.dict(sys.modules, {"copylot": SimpleNamespace(CoPylot=upstream)}):
            spec.loader.exec_module(wrapper)
        for platform, library in (("linux", "lib/copylot_accelerated.so"),
                                  ("macos", "lib/copylot_accelerated.so"),
                                  ("windows", "lib/copylot_accelerated.dll")):
            metadata = {"library": library, "cuda_toolkit": ""}
            (self.directory / "BUILD.json").write_text(json.dumps(metadata), encoding="utf-8")
            fake_os = SimpleNamespace(name="nt" if platform == "windows" else "posix", environ={},
                                      add_dll_directory=Mock(return_value=nullcontext()))
            with (self.subTest(platform=platform), patch.object(wrapper, "PACKAGE", self.directory),
                  patch.object(wrapper, "os", fake_os), patch.object(wrapper.ctypes, "CDLL") as load):
                instance = wrapper.CoPylot()
                self.assertIsInstance(instance, upstream)
                self.assertIs(instance.pdll, load.return_value)
                load.assert_called_once_with(str(self.directory / library))
                if platform == "windows":
                    fake_os.add_dll_directory.assert_called_once_with(str(self.directory / "lib"))

    def test_latest_falls_back_as_a_whole_but_explicit_selection_does_not(self):
        manifest = self.complete_global()
        second_id = GLOBAL_ID + 1
        self.api.add_run(second_id, evidence.GLOBAL_WORKFLOW)
        incomplete = {**manifest, "global": evidence.run_ref(second_id, 1, SHA), "status": "incomplete"}
        self.upload_manifest(incomplete, second_id)
        directory = self.directory / "download"
        directory.mkdir()
        with redirect_stdout(StringIO()) as log:
            selected = pipeline.select_global(self.api, "", directory)
        self.assertIn(f"Skipping global run {second_id}", log.getvalue())
        self.assertEqual(selected["global"]["run_id"], GLOBAL_ID)
        with self.assertRaisesRegex(github.EvidenceError, "identity or status"):
            pipeline.select_global(self.api, str(second_id), directory)
        self.api.artifacts[second_id][0]["expired"] = True
        with self.assertRaisesRegex(github.EvidenceError, "expired"):
            pipeline.select_global(self.api, str(second_id), directory)

    def test_draft_has_exact_assets_and_tag_at_source_and_rejects_duplicates(self):
        manifest = self.complete_global()
        with (patch.dict(os.environ, {**self.env, "RELEASE_VERSION": "v1.2.3-rc1+build.7"}),
              redirect_stdout(StringIO())):
            pipeline.create_draft(self.api)
            with self.assertRaisesRegex(github.EvidenceError, "already exists"):
                pipeline.create_draft(self.api)
        create, *uploads, tag = self.api.writes
        self.assertEqual(create[0], "releases")
        payload = create[1]
        self.assertIs(payload["draft"], True)
        self.assertIs(payload["prerelease"], True)
        self.assertEqual(payload["name"], "CoPylot-Accelerated v1.2.3-rc1+build.7")
        self.assertEqual(payload["tag_name"], "v1.2.3-rc1+build.7")
        self.assertEqual(payload["target_commitish"], manifest["global"]["source_revision"])
        self.assertEqual(len(uploads), 6)
        names = {key: f"copylot-accelerated-v1.2.3-rc1_build.7-{suffix}" for key, suffix in ASSET_SUFFIXES.items()}
        download_base = f"{self.api.server}/{self.api.repo}/releases/download/v1.2.3-rc1%2Bbuild.7"
        for name in (*names.values(), "SHA256SUMS.txt"):
            self.assertIn(f"]({download_base}/{name})", payload["body"])
        self.assertEqual({name for _, name in uploads}, {*names.values(), "SHA256SUMS.txt"})
        sums = self.api.asset_bytes["SHA256SUMS.txt"].decode().splitlines()
        self.assertEqual(len(sums), 5)
        self.assertEqual(set(sums), {f"{manifest['packages'][key]['sha256']}  {name}" for key, name in names.items()})
        for key, name in names.items():
            package = manifest["packages"][key]
            original_artifact = self.api.contents[package["artifact_id"]]
            with zipfile.ZipFile(BytesIO(original_artifact)) as archive:
                self.assertEqual(self.api.asset_bytes[name], archive.read(package["identity"]["archive"]))
            self.assertEqual(hashlib.sha256(self.api.asset_bytes[name]).hexdigest(), package["sha256"])
        self.assertEqual(tag, ("git/refs", {"ref": "refs/tags/v1.2.3-rc1+build.7", "sha": SHA}))

    def test_release_notes_list_stable_assets_and_link_exact_provenance(self):
        self.complete_global()
        manifest = pipeline.select_global(self.api, str(GLOBAL_ID), self.directory)
        _, names = pipeline.stage_assets(manifest, "v1.2.3", self.directory)
        expected = {key: f"copylot-accelerated-v1.2.3-{suffix}" for key, suffix in ASSET_SUFFIXES.items()}
        self.assertEqual(names, expected)
        notes = pipeline.release_notes(self.api, manifest, "v1.2.3", names)
        self.assertEqual([line for line in notes.splitlines() if line.startswith("## ")],
                         ["## Overview", "## Downloads", "## Quick start", "## Requirements", "## Source and validation"])
        self.assertNotRegex(notes, r"(?i)\bdraft\b|ready for review|distribution review|untagged-|/releases/latest")
        self.assertIn("CoPylot is its Python API", notes)
        self.assertIn("paths in a patched build as a numerical reference", notes)
        self.assertIn("All four modes use the same Hermite optical formulation", notes)
        for mode in ("Original SolarPILOT/CoPylot", "Refactored CPU", "Multicore CPU", "CUDA GPU"):
            self.assertIn(f"| {mode} |", notes)
        self.assertIn("https://github.com/NatLabRockies/SolarPILOT", notes)
        self.assertIn("| Platform | Backend | Download |", notes)
        self.assertIn("python3.12 -m venv .venv\n.venv/bin/python -m pip install -r requirements.txt\n"
                      ".venv/bin/python example.py --mode refactored", notes)
        self.assertIn("py -3.12 -m venv .venv\n"
                      r".\.venv\Scripts\python.exe -m pip install -r requirements.txt" "\n"
                      r".\.venv\Scripts\python.exe example.py --mode refactored", notes)
        self.assertIn("The hosted CUDA job checks library loading and CPU modes", notes)
        self.assertIn("earlier portable archive", notes)
        self.assertIn("`rtol=1e-15` and `atol=1e-15 kW/m²` per cell", notes)
        self.assertIn(f"https://github.com/{self.api.repo}/tree/{SHA}", notes)
        self.assertIn(self.api.run_url(GLOBAL_ID, 1), notes)
        download_base = f"{self.api.server}/{self.api.repo}/releases/download/v1.2.3"
        self.assertIn(f"[Download SHA256SUMS.txt]({download_base}/SHA256SUMS.txt)", notes)
        downloads = notes.split("## Downloads\n", 1)[1].split("## Quick start\n", 1)[0]
        self.assertNotIn("/actions/", downloads)
        details = notes.split("<details>", 1)[1].split("</details>", 1)[0]
        for key, package in manifest["packages"].items():
            self.assertIn(f"[{expected[key]}]({download_base}/{expected[key]})", downloads)
            build = manifest["builds"][package["build_workflow"]]
            validation = manifest["validations"][package["validate_workflow"]]
            self.assertIn(self.api.run_url(build["run_id"], build["attempt"]), details)
            self.assertIn(self.api.run_url(validation["run_id"], validation["attempt"]), details)
            self.assertIn(f"{self.api.run_url(build['run_id'])}/artifacts/{package['artifact_id']}", details)
            self.assertIn(f"{self.api.run_url(validation['run_id'])}/artifacts/{package['validation_artifact_id']}", details)

    def test_validation_receipt_uses_downloaded_bytes_and_actual_tooling_revision(self):
        build_id = self.api.dispatch("build-linux-cpu.yml")
        artifact, = self.api.artifacts[build_id]
        directory = self.directory / "build/selected-artifact"
        directory.mkdir(parents=True)
        with self.api.download(artifact) as archive:
            for name in archive.namelist():
                (directory / name).write_bytes(archive.read(name))
        receipt = self.directory / "validation.json"
        revision = "b" * 40
        env = {**self.env, "GITHUB_WORKFLOW_SHA": revision, "PACKAGE_PLATFORM": "linux-x86_64",
               "PACKAGE_BACKEND": "cpu", "BUILD_RUN_ID": str(build_id), "BUILD_ATTEMPT": "1",
               "BUILD_ARTIFACT_ID": str(artifact["id"]), "BUILD_REVISION": SHA}
        with (patch.dict(os.environ, env), patch.object(pipeline, "RECEIPT", receipt),
              patch.object(pipeline, "Path", return_value=directory)):
            pipeline.emit_receipt()
        identity = package_identity("linux-x86_64", "cpu", build_id, 1, SHA)
        digest = hashlib.sha256((directory / identity["archive"]).read_bytes()).hexdigest()
        self.assertEqual(json.loads(receipt.read_text(encoding="utf-8")),
                         evidence.validation_receipt(identity, artifact["id"], digest, GLOBAL_ID, 1, revision))

    def test_upload_failure_leaves_only_a_draft_and_refuses_overwrite(self):
        self.complete_global()
        self.api.upload_failure = True
        with (patch.dict(os.environ, {**self.env, "RELEASE_VERSION": "v1.2.3"}),
              redirect_stdout(StringIO())):
            with self.assertRaisesRegex(github.EvidenceError, "Inspect draft"):
                pipeline.create_draft(self.api)
            with self.assertRaisesRegex(github.EvidenceError, "Release or draft .* already exists"):
                pipeline.create_draft(self.api)
        self.assertEqual(self.api.tags, {})
        self.assertEqual(len(self.api.releases), 1)
        self.assertTrue(self.api.releases[0]["draft"])

    def test_preflight_never_creates_draft_for_invalid_explicit_run(self):
        self.api.artifacts[GLOBAL_ID].clear()
        with patch.dict(os.environ, {**self.env, "RELEASE_VERSION": "v1.2.3", "GLOBAL_RUN_ID": str(GLOBAL_ID)}):
            with self.assertRaisesRegex(github.EvidenceError, "must contain exactly one"):
                pipeline.create_draft(self.api)
        self.assertEqual(self.api.writes, [])

    def test_semver(self):
        for value, parsed in [("v0.1.0", ("v0.1.0", False)),
                              ("0.1.0-rc.1+build.001", ("v0.1.0-rc.1+build.001", True))]:
            self.assertEqual(pipeline.parse_version(value), parsed)
        for value in ("", " v0.1.0", "v1.2", "v01.2.3", "v1.2.3-01", "v1.2.3+", "v1.2.3\n", "v1.2.３"):
            with self.subTest(value=value), self.assertRaises(github.EvidenceError):
                pipeline.parse_version(value)


class GitHubAPI(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "example/optics", "GITHUB_SERVER_URL": "https://github.com",
                                     "GITHUB_API_URL": "https://api.github.com", "GITHUB_TOKEN": "test"}):
            self.api = github.GitHub()

    def test_dispatch_requests_direct_run_id(self):
        with patch.object(self.api, "request", return_value={"workflow_run_id": 42}) as request:
            self.assertEqual(self.api.dispatch("validate-linux-cuda.yml", {"build_run_id": "21"}), 42)
        request.assert_called_once_with("actions/workflows/validate-linux-cuda.yml/dispatches",
                                        payload={"ref": "main", "return_run_details": True,
                                                 "inputs": {"build_run_id": "21"}},
                                        version="2022-11-28")
        with patch.object(self.api, "request", return_value=None):
            with self.assertRaisesRegex(github.ApiError, "no run ID"):
                self.api.dispatch("build-linux-cpu.yml")

    def test_get_retries_rate_limit_but_ambiguous_post_is_not_repeated(self):
        error = HTTPError("https://api.github.com", 429, "rate limited", {"Retry-After": "1"}, None)
        with (patch.object(github, "urlopen", side_effect=[error, BytesIO(b'{"ok": true}')]) as open_url,
              patch.object(github.time, "sleep") as sleep):
            self.assertEqual(self.api.request("releases"), {"ok": True})
            self.assertEqual(open_url.call_count, 2)
            sleep.assert_called_once_with(1)
        error = HTTPError("https://api.github.com", 502, "bad gateway", {}, None)
        with patch.object(github, "urlopen", side_effect=error) as open_url:
            with self.assertRaisesRegex(github.ApiError, "HTTP 502"):
                self.api.request("releases", payload={"draft": True})
            self.assertEqual(open_url.call_count, 1)
