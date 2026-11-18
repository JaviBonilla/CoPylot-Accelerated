import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_package import COMMERCIAL_ASSETS, EXAMPLE_MEMBERS, has_packaged_examples


class PackagedExampleLayoutTests(unittest.TestCase):
    def setUp(self):
        self.files = dict.fromkeys(EXAMPLE_MEMBERS, b"test fixture")
        manifest = {"assets": {
            name: {"path": path, "sha256": hashlib.sha256(self.files[f"commercial_demo/inputs/{path}"]).hexdigest()}
            for name, path in COMMERCIAL_ASSETS.items()
        }}
        self.files["commercial_demo/inputs/cases/commercial-reference/case_manifest.json"] = json.dumps(manifest).encode()

    def test_legacy_and_complete_example_layouts(self):
        self.assertFalse(has_packaged_examples({"example.py": b"old layout"}))
        self.assertTrue(has_packaged_examples(self.files))

    def test_missing_example_and_changed_input_are_rejected(self):
        broken = self.files.copy()
        del broken["quickstart_weather.csv"]
        with self.assertRaisesRegex(ValueError, "Missing packaged example files.*quickstart_weather"):
            has_packaged_examples(broken)
        path = f"commercial_demo/inputs/{COMMERCIAL_ASSETS['weather']}"
        with self.assertRaisesRegex(ValueError, "differs from its pinned hash"):
            has_packaged_examples({**self.files, path: self.files[path] + b"\r\n"})
