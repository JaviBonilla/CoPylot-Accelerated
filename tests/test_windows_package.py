import json
from pathlib import Path
import re
import struct
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_package import SOURCES, inspect


LIBRARY = "lib/copylot_accelerated.dll"
REVISION = "a" * 40
STRING_OFFSET = 0x280
CODEVIEW_OFFSET = 0x340


def pe_fixture(payload=b"", pdb=b"copylot_accelerated.pdb", signature=b"RSDS", machine=0x8664):
    """A minimal PE32+ DLL header and file-backed section for archive inspection."""
    data = bytearray(0x600)
    pe = 0x80
    optional = pe + 24
    optional_size = 240
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, pe)
    data[pe:pe + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, pe + 4, machine, 1, 0, 0, 0, optional_size, 0x2022)
    struct.pack_into("<H", data, optional, 0x20B)
    struct.pack_into("<I", data, optional + 108, 16)
    section = optional + optional_size
    struct.pack_into("<8sIIII", data, section, b".rdata", 0x400, 0x1000, 0x400, 0x200)
    data[STRING_OFFSET:STRING_OFFSET + len(payload)] = payload
    if pdb is not None:
        record = signature + bytes(20 if signature == b"RSDS" else 12) + pdb + b"\0"
        struct.pack_into("<II", data, optional + 112 + 6 * 8, 0x1000, 28)
        struct.pack_into("<IIHHIIII", data, 0x200, 0, 0, 0, 0, 2, len(record),
                         0x1000 + CODEVIEW_OFFSET - 0x200, CODEVIEW_OFFSET)
        data[CODEVIEW_OFFSET:CODEVIEW_OFFSET + len(record)] = record
    return bytes(data)


class WindowsPackagePaths(unittest.TestCase):
    def inspect_dll(self, dll, *, extra=None, root="copylot-accelerated", outer_prefix=None, metadata_overrides=None):
        metadata = {
            "os": "windows", "architecture": "x86_64", "source_revision": REVISION,
            "source_dirty_at_configure": False, "build_type": "Release", "variant": "cpu",
            "schema_version": 1, "package_name": "copylot-accelerated", "library": LIBRARY,
            "compiler": "MSVC fixture", "cmake": "3.30.5", "diagnostics": True,
            "cuda_toolkit": "", "cuda_architecture": "", "dependencies": {},
        }
        metadata.update(metadata_overrides or {})
        prefix = f"copylot-accelerated-local-{REVISION[:12]}-windows-x86_64-cpu"
        with TemporaryDirectory() as temp:
            path = Path(temp) / f"{outer_prefix or prefix}.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(f"{root}/", "")
                for name in (*SOURCES, "python/copylot.py"):
                    archive.writestr(f"{root}/{name}", "placeholder")
                archive.writestr(f"{root}/BUILD.json", json.dumps(metadata))
                archive.writestr(f"{root}/{LIBRARY}", dll)
                if extra:
                    archive.writestr(extra, "" if extra.endswith("/") else "placeholder")
            with patch("verify_package.platform.system", return_value="Windows"), \
                    patch("verify_package.platform.machine", return_value="AMD64"):
                return inspect(path, runtime_only=True)

    def assert_rejected(self, dll, category, offset, hidden):
        with self.assertRaisesRegex(ValueError, rf"{re.escape(category)} at file offset 0x{offset:x}") as error:
            self.inspect_dll(dll)
        self.assertIn(LIBRARY, str(error.exception))
        self.assertNotIn(hidden, str(error.exception))

    def test_allows_relative_paths_and_unterminated_binary_prefix(self):
        dll = pe_fixture(b"\x90A:\\a\\\x91\0../Users/document.txt\0")
        self.assertIn(b"A:\\a\\", dll)
        files, _ = self.inspect_dll(dll)
        self.assertEqual(files[LIBRARY], dll)
        self.inspect_dll(pe_fixture(pdb=None))

    def test_rejects_drive_unc_and_posix_paths_in_text(self):
        for path, category in (
            (r"D:\a\fixture\private.cpp", "drive path"),
            (r"E:\fixture\private.cpp", "drive path"),
            (r"\\fixture\share\private.cpp", "UNC path"),
            ("/Users/fixture/private.cpp", "POSIX local path"),
        ):
            with self.subTest(category=category):
                dll = pe_fixture(b"Source: " + path.encode() + b"\0")
                self.assert_rejected(dll, f"PE UTF-8/ANSI {category}", STRING_OFFSET + 8, path)

    def test_rejects_utf16_path_with_byte_offset(self):
        prefix = "Origin 🚧: "
        path = r"C:\fixture\privé.cpp"
        dll = pe_fixture((prefix + path + "\0").encode("utf-16-le"))
        self.assert_rejected(dll, "PE UTF-16LE drive path",
                             STRING_OFFSET + len(prefix.encode("utf-16-le")), path)
        path = r"C:\測試\private.cpp"
        self.assert_rejected(pe_fixture((path + "\0").encode("utf-16-le")),
                             "PE UTF-16LE drive path", STRING_OFFSET, path)

    def test_rejects_structured_codeview_pdb_paths(self):
        for signature, header_size in ((b"RSDS", 24), (b"NB10", 16)):
            with self.subTest(signature=signature):
                path = r"X:\fixture\debug\copylot_accelerated.pdb"
                dll = pe_fixture(pdb=path.encode(), signature=signature)
                self.assert_rejected(dll, "PE CodeView local PDB path", CODEVIEW_OFFSET + header_size, path)

    def test_rejects_credential_and_preserves_package_gates(self):
        marker = "-----BEGIN PRIVATE KEY-----"
        self.assert_rejected(pe_fixture((marker + "\nfixture\n\0").encode()),
                             "PE UTF-8/ANSI credential marker", STRING_OFFSET, marker)
        with self.assertRaisesRegex(ValueError, "Expected an x64 PE32"):
            self.inspect_dll(pe_fixture(machine=0xAA64))
        with self.assertRaisesRegex(ValueError, "package allowlist"):
            self.inspect_dll(pe_fixture(), extra="copylot-accelerated/lib/copylot_accelerated.pdb")

    def test_archive_root_and_outer_name_are_checked_independently(self):
        self.inspect_dll(pe_fixture())
        with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
            self.inspect_dll(pe_fixture(), root=f"copylot-accelerated-local-{REVISION[:12]}-windows-x86_64-cpu")
        with self.assertRaisesRegex(ValueError, "Archive name or build configuration"):
            self.inspect_dll(pe_fixture(), outer_prefix="copylot-accelerated-v1.2.3-windows-x86_64-cpu")

    def test_inspection_rejects_wrong_build_metadata_identity(self):
        for overrides, error in (({"schema_version": True}, "Unsupported BUILD.json schema"),
                                 ({"package_name": "other"}, "BUILD.json package_name"),
                                 ({"version": "0.0.0"}, "fields differ from schema version 1")):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, error):
                self.inspect_dll(pe_fixture(), metadata_overrides=overrides)

    def test_rejects_unsafe_paths_and_unexpected_directories(self):
        for path in ("second-root/", "top-level.txt", "/copylot-accelerated/bad", "copylot-accelerated/../bad",
                     "copylot-accelerated/./bad", "copylot-accelerated/lib\\bad", "copylot-accelerated/lib:bad"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Unsafe archive path"):
                self.inspect_dll(pe_fixture(), extra=path)
        with self.assertRaisesRegex(ValueError, "unexpected directories"):
            self.inspect_dll(pe_fixture(), extra="copylot-accelerated/empty/")
