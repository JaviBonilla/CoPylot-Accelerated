import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from resolve_package import BUILDS, api, resolve


REPO = "owner/repository"
LINUX = "build-linux-cpu.yml"
MACOS = "build-macos-cpu.yml"
REVISION = "1234567890abcdef1234567890abcdef12345678"
PREFIX = f"repos/{REPO}/actions"


def run(run_id, workflow=LINUX, **overrides):
    return {"id": run_id, "run_attempt": 1, "head_sha": REVISION, "head_branch": "main",
            "head_repository": {"full_name": REPO}, "path": f".github/workflows/{workflow}",
            "event": "workflow_dispatch", "status": "completed", "conclusion": "success", **overrides}


def artifacts(build, workflow=LINUX):
    backend, platforms = BUILDS[workflow]
    run_id, attempt = build["id"], build["run_attempt"]
    return [{"name": f"hermite-optics-{backend}-{platform}-{run_id}-{attempt}", "id": run_id * 10 + index,
             "expired": False, "expires_at": "2099-01-01T00:00:00Z",
             "workflow_run": {"id": run_id, "head_sha": build["head_sha"], "head_branch": "main"}}
            for index, platform in enumerate(platforms, start=1)]


class ResolvePackage(unittest.TestCase):
    def setUp(self):
        self.responses = {}

    def request(self, path, collection=None):
        return self.responses[path, collection]

    def setup_runs(self, *runs, workflow=LINUX):
        self.responses[f"{PREFIX}/workflows/{workflow}/runs?"
                       "branch=main&event=workflow_dispatch&status=success&per_page=100", "workflow_runs"] = list(runs)
        for build in runs:
            self.responses[f"{PREFIX}/runs/{build['id']}", None] = build

    def add_artifacts(self, build, available):
        self.responses[f"{PREFIX}/runs/{build['id']}/artifacts?per_page=100", "artifacts"] = available

    def add_completed_jobs(self, build, *completed):
        path = f"{PREFIX}/runs/{build['id']}/attempts/{build['run_attempt']}/jobs?per_page=100"
        self.responses[path, "jobs"] = [
            {"status": "completed", "completed_at": value} for value in completed
        ]

    def test_uses_job_completion_time_and_extracts_provenance(self):
        newer_id = run(12, updated_at="2026-11-05T12:20:00Z")
        later_completion = run(11, run_attempt=3, updated_at="2026-11-05T12:15:00Z")
        self.setup_runs(newer_id, later_completion)
        self.add_artifacts(newer_id, artifacts(newer_id))
        self.add_artifacts(later_completion, artifacts(later_completion))
        self.add_completed_jobs(newer_id, "2026-11-05T12:10:00Z")
        self.add_completed_jobs(later_completion, "2026-11-05T12:15:00Z")
        result = resolve(REPO, LINUX, request=self.request)
        self.assertEqual(result, {"run_id": 11, "attempt": 3, "revision": REVISION,
                                  "artifacts": {"linux-x86_64": {
                                      "name": "hermite-optics-cpu-linux-x86_64-11-3", "id": "111"}}})

    def test_skips_failed_and_in_progress_runs(self):
        completed = run(11)
        self.setup_runs(run(13, status="in_progress", conclusion=None),
                        run(12, conclusion="failure"), completed)
        self.add_artifacts(completed, artifacts(completed))
        self.add_completed_jobs(completed, "2026-11-05T12:10:00Z")
        self.assertEqual(resolve(REPO, LINUX, request=self.request)["run_id"], 11)
        with self.assertRaisesRegex(ValueError, "No suitable successful Build for Build Run ID 13"):
            resolve(REPO, LINUX, "13", request=self.request)

    def test_skips_missing_expired_wrong_backend_and_wrong_platform_artifacts(self):
        completed, unsuitable = run(11), run(12, run_attempt=2)
        self.setup_runs(unsuitable, completed)
        self.add_artifacts(completed, artifacts(completed))
        self.add_completed_jobs(completed, "2026-11-05T12:10:00Z")
        valid, = artifacts(unsuitable)
        for available in (
            [], [{**valid, "expired": True}], [{**valid, "expires_at": "2000-01-01T00:00:00Z"}],
            [{**valid, "name": valid["name"].replace("-cpu-", "-cuda-")}],
            [{**valid, "name": valid["name"].replace("linux-x86_64", "windows-x86_64")}],
            [{**valid, "name": valid["name"].removesuffix("-2") + "-1"}],
            [{**valid, "workflow_run": {**valid["workflow_run"], "head_sha": "0" * 40}}],
        ):
            with self.subTest(available=available):
                self.add_artifacts(unsuitable, available)
                self.assertEqual(resolve(REPO, LINUX, request=self.request)["run_id"], 11)
                with self.assertRaisesRegex(ValueError, "needs one unexpired artifact"):
                    resolve(REPO, LINUX, "12", request=self.request)

    def test_macos_requires_both_artifacts_in_the_same_attempt(self):
        build = run(12, MACOS, run_attempt=2)
        self.setup_runs(build, workflow=MACOS)
        intel, arm = artifacts(build, MACOS)
        self.add_artifacts(build, [intel, {**arm, "name": arm["name"].removesuffix("-2") + "-1"}])
        with self.assertRaisesRegex(ValueError, "needs one unexpired artifact named .*macos-arm64-12-2"):
            resolve(REPO, MACOS, request=self.request)
        self.add_artifacts(build, [intel, arm])
        self.add_completed_jobs(build, "2026-11-05T12:10:00Z", "2026-11-05T12:20:00Z")
        result = resolve(REPO, MACOS, request=self.request)
        self.assertEqual(set(result["artifacts"]), {"macos-x86_64", "macos-arm64"})

    def test_manual_override_is_exact_and_checks_workflow_and_branch(self):
        older = run(11, run_attempt=4)
        self.setup_runs(older, run(12), run(13, MACOS), run(14, head_branch="feature"))
        self.add_artifacts(older, artifacts(older))
        self.add_completed_jobs(older, "2026-11-05T12:10:00Z")
        self.assertEqual(resolve(REPO, LINUX, "11", request=self.request)["attempt"], 4)
        for override in ("13", "14"):
            with self.assertRaisesRegex(ValueError, "not a successful main Build"):
                resolve(REPO, LINUX, override, request=self.request)
        with self.assertRaisesRegex(ValueError, "must be a positive integer"):
            resolve(REPO, LINUX, "invalid", request=self.request)

    def test_paginated_api_keeps_artifacts_from_every_page(self):
        pages = [{"artifacts": [{"id": 1}]}, {"artifacts": [{"id": 2}]}]
        with patch("resolve_package.subprocess.check_output", return_value=json.dumps(pages).encode()) as gh:
            self.assertEqual(api("endpoint", "artifacts"), [{"id": 1}, {"id": 2}])
        gh.assert_called_once_with(["gh", "api", "--paginate", "--slurp", "endpoint"])
