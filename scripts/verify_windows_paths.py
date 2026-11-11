"""Check Windows package PE strings and CodeView records without logging their contents."""

import ntpath
import re
import struct


PE_TEXT = (
    (re.compile(rb"[\x20-\x7e\x80-\xff]{5,}"), "UTF-8/ANSI", 1),
    (re.compile(rb"(?:[\x20-\x7e]\x00){3,}(?:[^\x00].|\x00[^\x00]){0,32767}\x00\x00",
                re.DOTALL), "UTF-16LE", 2),
)
PATHS = re.compile(
    r"""(?<![\w./\\@-])(?:"""
    r"""(?P<drive>(?:file:///|\\\\[?.]\\)?[a-z]:[\\/][^\s\\/:<>"|?*])"""
    r"""|(?P<unc>\\\\(?:\?\\UNC\\)?[^\s\\/:<>"|?*]+[\\/][^\s\\/:<>"|?*])"""
    r"""|(?P<posix>(?:file://)?/(?:home|tmp|Users|workspace|Volumes|_work)/[^\s/]))""",
    re.IGNORECASE | re.ASCII,
)
CREDENTIALS = re.compile(
    r"\b(?:gh[pousr]_[a-z0-9]{20,}|github_pat_[a-z0-9_]{20,})"
    r"|-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"
    r"|(?:https?|ssh)://[^/\s:@]+:[^/\s@]+@",
    re.IGNORECASE,
)
PATH_CATEGORIES = {"drive": "drive path", "unc": "UNC path", "posix": "POSIX local path"}


def codeview_records(data):
    """Yield file offsets and bytes of PDB paths in PE32+ debug directory entries."""
    pe_offset, = struct.unpack_from("<I", data, 60)
    section_count, = struct.unpack_from("<H", data, pe_offset + 6)
    optional_size, = struct.unpack_from("<H", data, pe_offset + 20)
    optional = pe_offset + 24
    sections = optional + optional_size
    if optional_size < 112 or sections + section_count * 40 > len(data):
        raise ValueError("Invalid PE optional header or section table")
    directories, = struct.unpack_from("<I", data, optional + 108)
    if directories <= 6:
        return
    if optional_size < 112 + 7 * 8:
        raise ValueError("Invalid PE debug data directory")
    debug_rva, debug_size = struct.unpack_from("<II", data, optional + 112 + 6 * 8)
    if not debug_rva and not debug_size:
        return

    def file_offset(rva, size):
        for section in range(sections, sections + section_count * 40, 40):
            address, raw_size, raw_offset = struct.unpack_from("<III", data, section + 12)
            delta = rva - address
            if 0 <= delta and delta + size <= raw_size and raw_offset + delta + size <= len(data):
                return raw_offset + delta
        raise ValueError("PE debug data is outside file-backed sections")

    if not debug_rva or not debug_size or debug_size % 28:
        raise ValueError("Invalid PE debug directory size or address")
    start = file_offset(debug_rva, debug_size)
    for entry in range(start, start + debug_size, 28):
        kind, size, rva, raw = struct.unpack_from("<IIII", data, entry + 12)
        if kind != 2:  # IMAGE_DEBUG_TYPE_CODEVIEW
            continue
        raw = raw or file_offset(rva, size)
        if size < 4 or raw + size > len(data):
            raise ValueError("Invalid PE CodeView record bounds")
        header_size = {b"RSDS": 24, b"NB10": 16}.get(data[raw:raw + 4])
        if header_size is not None:
            path_offset = raw + header_size
            path, nul, _ = data[path_offset:raw + size].partition(b"\0")
            if not nul or not path:
                raise ValueError("Invalid PE CodeView PDB path")
            yield path_offset, path


def verify_windows_paths(data, name):
    def reject(category, offset):
        raise ValueError(f"Unsafe content in archive member {name}: {category} at file offset 0x{offset:x}")

    for offset, raw_path in codeview_records(data):
        path = raw_path.decode("utf-8", errors="replace")
        if path.startswith(("\\", "/")) or ntpath.splitdrive(path)[0]:
            reject("PE CodeView local PDB path", offset)

    # A byte prefix in instructions or metadata alone is not a path. Look for
    # text with a terminator, a path boundary, and a component after the root.
    for strings, encoding, width in PE_TEXT:
        for match in strings.finditer(data):
            if width == 1:
                if data[match.end():match.end() + 1] not in (b"\0", b"\r", b"\n"):
                    continue
                raw = match[0]
            else:
                raw = match[0][:-width]
            codec = "utf-8" if width == 1 else "utf-16-le"
            try:
                text = raw.decode(codec)
            except UnicodeDecodeError:
                codec = "latin-1" if width == 1 else codec
                text = raw.decode(codec, errors="replace")
            for pattern in (PATHS, CREDENTIALS):
                for finding in pattern.finditer(text):
                    if pattern is PATHS and not text[finding.start():].isprintable():
                        continue
                    # Count UTF-16 code units so surrogate pairs do not skew offsets.
                    offset = match.start() + len(text[:finding.start()].encode(codec))
                    category = PATH_CATEGORIES[finding.lastgroup] if pattern is PATHS else "credential marker"
                    reject(f"PE {encoding} {category}", offset)
