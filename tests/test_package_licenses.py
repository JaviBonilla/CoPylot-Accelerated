import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from test_windows_package import LIBRARY, REVISION, pe_fixture
from native_package import verify_archive
from verify_package import ROOT, SOURCES, verify_licenses


SSC_LICENSE = "licenses/SSC-LICENSE.txt"
INVENTORY = "docs/licensing-inventory.json"


class PackageLicenses(unittest.TestCase):
    def setUp(self):
        self.license = (ROOT / SSC_LICENSE).read_bytes()

    def test_pinned_blob_matches_even_when_git_checks_out_crlf(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for name in (SSC_LICENSE, INVENTORY):
                copy = root / name
                copy.parent.mkdir(parents=True, exist_ok=True)
                copy.write_bytes((ROOT / name).read_bytes())
            repo = root / "ssc"
            repo.mkdir()
            (repo / ".gitattributes").write_bytes(b"* text=auto\n")
            license_path = repo / "LICENSE"
            license_path.write_bytes(self.license)

            def git(*args, eol="lf"):
                return subprocess.check_output(
                    ["git", "-C", str(repo), "-c", "core.autocrlf=false", "-c", f"core.eol={eol}", *args],
                    stderr=subprocess.PIPE,
                )

            git("init", "-q")
            git("add", "--", ".gitattributes", "LICENSE")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "-qm", "Pinned license fixture")
            pin = git("rev-parse", "HEAD").decode("ascii").strip()
            license_path.unlink()
            git("checkout-index", "--", "LICENSE", eol="crlf")
            self.assertEqual(license_path.read_bytes(), self.license.replace(b"\n", b"\r\n"))
            self.assertNotEqual(license_path.read_bytes(), self.license)

            files = {SSC_LICENSE: self.license}
            with patch("verify_package.ROOT", root):
                verify_licenses(files, lock={"ssc": {"patched_sha": pin}}, names={SSC_LICENSE})
                with self.assertRaisesRegex(ValueError, "missing or unavailable reference") as error:
                    verify_licenses(files, lock={"ssc": {"patched_sha": "0" * 40}}, names={SSC_LICENSE})
            self.assertIn("pinned source ssc/LICENSE: unavailable", str(error.exception))
            self.assertNotIn(str(root), str(error.exception))

    def test_diagnoses_and_rejects_crlf_and_changed_wording(self):
        for license_bytes, category, normalized in (
            (self.license.replace(b"\n", b"\r\n"), "CRLF/LF difference only", "yes"),
            (self.license + b"Changed fixture wording.\n", "license content differs", "no"),
        ):
            with self.subTest(category=category):
                with self.assertRaisesRegex(ValueError, category) as error:
                    verify_licenses({SSC_LICENSE: license_bytes}, names={SSC_LICENSE})
                message = str(error.exception)
                self.assertIn("for SSC", message)
                self.assertIn(f"CRLF/LF-normalized equality: {normalized}", message)
                for label, data in (("archive member", license_bytes), ("checkout", self.license)):
                    digest = hashlib.sha256(data).hexdigest()
                    self.assertIn(f"{label} {SSC_LICENSE}: {len(data)} bytes, SHA-256 {digest}", message)
                self.assertNotIn("Changed fixture wording.", message)

    def test_verifies_windows_zip_and_rejects_missing_or_wrong_license(self):
        lock = json.loads((ROOT / "repos.lock.json").read_text(encoding="utf-8"))
        info = {
            "os": "windows", "architecture": "x86_64", "source_revision": REVISION,
            "source_dirty_at_configure": False, "build_type": "Release", "variant": "cpu",
            "distribution": "local-validation-only", "redistribution": "blocked-pending-review",
            "library": LIBRARY, "diagnostics": True, "cuda_toolkit": "", "cuda_architecture": "",
            "dependencies": {name: dependency["patched_sha"] for name, dependency in lock.items()},
        }
        members = {
            target: (ROOT / source).read_bytes()
            for target, source in SOURCES.items() if target != "python/pysoltrace.py"
        }
        members.update({"BUILD.json": json.dumps(info).encode("utf-8"), LIBRARY: pe_fixture(),
                        "python/copylot.py": b"# fixture\n", "python/pysoltrace.py": b"# fixture\n"})
        identity = {"platform": "windows-x86_64", "source_revision": REVISION}
        prefix = f"hermite-optics-local-{REVISION[:12]}-windows-x86_64-cpu"
        with TemporaryDirectory() as temp:
            archive = Path(temp) / f"{prefix}.zip"

            def verify_zip(contents):
                with zipfile.ZipFile(archive, "w") as package:
                    for name, data in contents.items():
                        package.writestr(f"{prefix}/{name}", data)
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
                with patch("verify_package.platform.system", return_value="Windows"), \
                        patch("verify_package.platform.machine", return_value="AMD64"):
                    verify_archive(archive, identity, "cpu", upstream=False)

            verify_zip(members)
            with self.assertRaisesRegex(ValueError, "License verification failed for SSC .*missing archive member"):
                verify_zip({name: data for name, data in members.items() if name != SSC_LICENSE})
            with self.assertRaisesRegex(ValueError, "License verification failed for SSC .*license content differs"):
                verify_zip({**members, SSC_LICENSE: members["licenses/SolTrace-LICENSE.md"]})
