#!/usr/bin/env python3
"""Inspect a locally built CPack archive and run its extracted smoke example."""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import zipfile

from verify_windows_paths import verify_windows_paths

ROOT = Path(__file__).resolve().parents[1]
PORTABLE_CPU = "cpu-glibc2.34"
PORTABLE_CUDA = "cuda13.0-sm89-glibc2.34"
CUDART_SONAME = "libcudart.so.13"
PORTABLE_MAX = {"GLIBC": (2, 34), "GLIBCXX": (3, 4, 29), "CXXABI": (1, 3, 13)}
PORTABLE_NEEDED = {"libc.so.6", "libm.so.6", "libstdc++.so.6", "libgcc_s.so.1",
                   "ld-linux-x86-64.so.2", "libpthread.so.0", "libdl.so.2", "librt.so.1"}
LICENSES = {
    "licenses/SSC-LICENSE.txt", "licenses/SolarPILOT-LICENSE.md",
    "licenses/SolTrace-LICENSE.md", "licenses/NLopt-LICENSE.htm",
    "licenses/lp_solve-LICENSE.htm", "licenses/RapidXML-license.txt",
}
PROJECT_LICENSES = {
    "LICENSE": "Project code",
    "licenses/Project-documentation-CC-BY-4.0.txt": "Project documentation",
}
PACKAGE_LICENSES = LICENSES | set(PROJECT_LICENSES)
SOURCES = {
    "README.md": "packaging/README.md",
    "licenses/Project-documentation-CC-BY-4.0.txt": "docs/LICENSE",
    "example.py": "packaging/example.py",
    "python/hermite_optics.py": "packaging/hermite_optics.py",
    "python/pysoltrace.py": "SolarPILOT/deploy/api/pysoltrace.py",
    **{name: name for name in LICENSES | {"requirements.txt", "LICENSE", "THIRD_PARTY_NOTICES"}},
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def archive_files(path):
    if path.name.endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                require(not stat.S_ISLNK(item.external_attr >> 16), "ZIP links are forbidden")
                if not item.is_dir():
                    yield item.filename, archive.read(item)
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            for item in archive:
                if not item.isdir():
                    require(item.isfile(), "TAR members must be regular files")
                    with archive.extractfile(item) as stream:
                        yield item.name, stream.read()
    else:
        raise ValueError("Expected a CPack .zip or .tar.gz archive")


def inspect(path, runtime_only=False):
    prefix = path.name.removesuffix(".tar.gz").removesuffix(".zip")
    files = {}
    for name, content in archive_files(path):
        parts = PurePosixPath(name).parts
        require(len(parts) > 1 and parts[0] == prefix and ".." not in parts
                and "\\" not in name and ":" not in name, f"Unsafe archive path: {name}")
        relative = "/".join(parts[1:])
        require(relative not in files, f"Duplicate archive member: {relative}")
        files[relative] = content

    info = json.loads(files["BUILD.json"])
    os_names = {"Linux": "linux", "Windows": "windows", "Darwin": "macos"}
    host_arch = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64"}
    architecture = info["architecture"]
    require(info["os"] == os_names.get(platform.system())
            and architecture == host_arch.get(platform.machine().lower())
            and (architecture == "x86_64" or (architecture == "arm64" and info["os"] == "macos")),
            "Use a matching native host")
    require(info["distribution"] == "local-validation-only"
            and info["redistribution"] == "blocked-pending-review", "Incorrect distribution status")
    revision = info["source_revision"]
    require(re.fullmatch(r"[0-9a-f]{40}", revision), "Invalid source revision")
    configured_revision = revision[:12] + ("-dirty" if info["source_dirty_at_configure"] else "")
    expected_prefix = f'hermite-optics-local-{configured_revision}-{info["os"]}-{architecture}-{info["variant"]}'
    require(prefix == expected_prefix and info["build_type"] == "Release",
            "Archive name or build configuration differs from metadata")
    suffix = ".dll" if info["os"] == "windows" else ".so"
    library = f"lib/hermite_optics{suffix}"
    require(info["library"] == library, "Unexpected library path")
    missing_licenses = PACKAGE_LICENSES - files.keys()
    if missing_licenses:
        verify_licenses(files, names=missing_licenses)
    require(set(files) == set(SOURCES) | {"BUILD.json", "python/copylot.py", library},
            "Archive differs from the package allowlist")
    if info["os"] != "linux":
        verify_binary_header(files[library], info["os"], architecture)
    private = re.compile(rb"/(?:home|tmp|Users|workspace|Volumes|_work)/"
                         rb"|[A-Za-z]:[\\/]+(?:Users|repositories|a|_work)[\\/]", re.I)
    for name, content in files.items():
        if info["os"] == "windows" and name == library:
            verify_windows_paths(content, name)
        else:
            require(not private.search(content), f"Local path in archive member: {name}")
    if not runtime_only:
        verify_sources(files, info)
    return files, info


def verify_binary_header(data, os_name, architecture):
    if os_name == "windows":
        require(data.startswith(b"MZ") and len(data) >= 64, "Expected a Windows PE binary")
        offset = struct.unpack_from("<I", data, 60)[0]
        require(offset >= 64 and len(data) >= offset + 26 and data[offset:offset + 4] == b"PE\0\0",
                "Invalid PE header")
        machine, = struct.unpack_from("<H", data, offset + 4)
        characteristics, magic = struct.unpack_from("<HH", data, offset + 22)
        require(architecture == "x86_64" and machine == 0x8664 and magic == 0x20B
                and characteristics & 0x2000, "Expected an x64 PE32+ DLL")
    else:
        require(len(data) >= 32 and data.startswith(b"\xcf\xfa\xed\xfe"),
                "Expected a single-architecture 64-bit Mach-O")
        machine, _, file_type = struct.unpack_from("<III", data, 4)
        require(machine == {"x86_64": 0x01000007, "arm64": 0x0100000C}[architecture] and file_type == 6,
                f"Expected a Mach-O dylib for {architecture}")


def verify_license(component, name, packaged, reference_label, reference, expected_sha):
    packaged_sha = hashlib.sha256(packaged).hexdigest() if packaged is not None else None
    if packaged is not None and packaged == reference and (expected_sha is None or packaged_sha == expected_sha):
        return

    normalized_equal = None
    if packaged is not None and reference is not None:
        normalized_equal = packaged.replace(b"\r\n", b"\n") == reference.replace(b"\r\n", b"\n")
    if packaged is None:
        category = "missing archive member"
    elif reference is None:
        category = "missing or unavailable reference"
    elif packaged == reference:
        category = "inventory checksum mismatch"
    elif normalized_equal:
        category = "CRLF/LF difference only"
    else:
        category = "license content differs"

    packaged_info = f"{len(packaged)} bytes, SHA-256 {packaged_sha}" if packaged is not None else "missing"
    reference_info = (f"{len(reference)} bytes, SHA-256 {hashlib.sha256(reference).hexdigest()}"
                      if reference is not None else "unavailable")
    normalized = "unavailable" if normalized_equal is None else ("yes" if normalized_equal else "no")
    inventory = f"\n  inventory SHA-256 {expected_sha}" if expected_sha is not None else ""
    raise ValueError(
        f"License verification failed for {component} ({category})\n"
        f"  archive member {name}: {packaged_info}\n"
        f"  {reference_label}: {reference_info}\n"
        f"  CRLF/LF-normalized equality: {normalized}{inventory}"
    )


def verify_licenses(files, *, lock=None, names=PACKAGE_LICENSES):
    inventory = json.loads((ROOT / "docs/licensing-inventory.json").read_text(encoding="utf-8"))
    components = {item["visible_license_copy"]: item for item in inventory["components"]}
    require(components.keys() == LICENSES, "Third-party license inventory differs from the package allowlist")
    for name in sorted(names):
        packaged = files.get(name)
        if name in PROJECT_LICENSES:
            component, expected_sha = PROJECT_LICENSES[name], None
        else:
            item = components[name]
            component, expected_sha = item["component"], item["sha256"]
            if lock is not None:
                dependency = item["pin_in_repos_lock"]
                source = item["upstream_license_path"]
                relative = PurePosixPath(source).relative_to(dependency).as_posix()
                pin = lock[dependency]["patched_sha"]
                # Read the committed bytes without Git's working-tree filters.
                try:
                    result = subprocess.run(
                        ["git", "cat-file", "blob", f"{pin}:{relative}"],
                        cwd=ROOT / dependency, capture_output=True, check=False,
                    )
                    pinned = result.stdout if result.returncode == 0 else None
                except FileNotFoundError:
                    pinned = None
                verify_license(component, name, packaged, f"pinned source {source}", pinned, expected_sha)
        source = SOURCES[name]
        try:
            checkout_copy = (ROOT / source).read_bytes()
        except FileNotFoundError:
            checkout_copy = None
        verify_license(component, name, packaged, f"checkout {source}", checkout_copy, expected_sha)


def verify_sources(files, info, *, upstream=True):
    checkout = str(ROOT).encode()
    checkout_windows = str(ROOT).replace("/", "\\").encode()
    for name, content in files.items():
        require(checkout not in content and checkout_windows not in content,
                f"Checkout path in archive member: {name}")
    lock = json.loads((ROOT / "repos.lock.json").read_text())
    verify_licenses(files, lock=lock if upstream else None)
    for target, source in SOURCES.items():
        if target in PACKAGE_LICENSES:
            continue
        if not upstream and source == "SolarPILOT/deploy/api/pysoltrace.py":
            continue
        require(files[target] == (ROOT / source).read_bytes(), f"Altered package file: {target}")
    if upstream:
        wrapper = (ROOT / "SolarPILOT/deploy/api/copylot.py").read_text(encoding="utf-8")
        wrapper = re.sub(r"\n[ \t]*# self\.pdll = CDLL\([^\n]*", "", wrapper)
        require(files["python/copylot.py"].decode().replace("\r\n", "\n") == wrapper,
                "Upstream wrapper differs beyond removed developer-path comments")
    require(info["dependencies"] == {name: pin["patched_sha"] for name, pin in lock.items()},
            "Dependency metadata differs from the pins")


def version_tuple(value):
    return tuple(map(int, value.split(".")))


def linux_dependencies(library, portable, portable_cuda, cuda_runtime_dir, *, resolve=True):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("LD_")}
    environment["LC_ALL"] = "C"
    if cuda_runtime_dir:
        environment["LD_LIBRARY_PATH"] = str(cuda_runtime_dir)

    def readelf(flag):
        return subprocess.check_output(["readelf", flag, str(library)], text=True, env=environment)

    dynamic = readelf("-d")
    require("(RPATH)" not in dynamic and "(RUNPATH)" not in dynamic, "Unexpected ELF search path")
    needed = re.findall(r"\(NEEDED\).*?\[([^]]+)\]", dynamic)
    versions = readelf("--version-info").partition("Version needs section")[2]
    imports = re.findall(r"Name: (GLIBCXX|GLIBC|CXXABI)_(\S+)", versions)
    symbols = {}
    for family in PORTABLE_MAX:
        values = {value for name, value in imports if name == family and re.fullmatch(r"[0-9.]+", value)}
        if values:
            symbols[family] = max(values, key=version_tuple)
    header = readelf("-h")
    require(re.search(r"Class:\s+ELF64", header)
            and re.search(r"Machine:\s+Advanced Micro Devices X86-64", header)
            and re.search(r"Type:\s+DYN", header), "Expected an x86-64 ELF shared object")
    isa = re.findall(r"x86 ISA needed:\s*([^\n]+)", readelf("-n"))
    if portable:
        allowed = PORTABLE_NEEDED | ({CUDART_SONAME} if portable_cuda else set())
        require(set(needed) <= allowed, f"Unexpected portable ELF dependencies: {needed}")
        require((CUDART_SONAME in needed) == portable_cuda, "Unexpected portable CUDA runtime SONAME")
        require(all(re.fullmatch(r"[0-9.]+", value) and version_tuple(value) <= PORTABLE_MAX[family]
                    for family, value in imports), f"Portable ELF ABI ceiling exceeded: {imports}")
        require(set(symbols) == set(PORTABLE_MAX), "Incomplete portable ELF version requirements")
        require(all(level.strip() == "x86-64-baseline" for level in isa), f"Unexpected x86 ISA: {isa}")
    if portable and resolve:
        resolved = subprocess.check_output(["ldd", "-r", str(library)], text=True,
                                           stderr=subprocess.STDOUT, env=environment)
        require(not re.search(r"not found|undefined symbol", resolved), resolved)
        if cuda_runtime_dir:
            match = re.search(r"^\s*libcudart\.so\.13 => (.+?) \(0x", resolved, flags=re.M)
            require(match and Path(match[1]).resolve() == (cuda_runtime_dir / CUDART_SONAME).resolve(),
                    "CUDA runtime did not resolve to the requested external library")
        print(resolved, end="")
    return {"needed": needed, "symbols": symbols, "elf": "ELF64 x86-64 DYN", "isa_notes": isa}


def find_dumpbin():
    if executable := shutil.which("dumpbin"):
        return executable
    installer = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
    location = subprocess.check_output([
        str(installer), "-latest", "-version", "[17.0,18.0)", "-products", "*",
        "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath",
    ], text=True).strip()
    require(location, "Visual Studio 2022 C++ tools are required for dumpbin")
    vc = Path(location) / "VC"
    toolset = (vc / "Auxiliary/Build/Microsoft.VCToolsVersion.default.txt").read_text().strip()
    return str(vc / "Tools/MSVC" / toolset / "bin/Hostx64/x64/dumpbin.exe")


def runtime_dependencies(library, os_name, portable, portable_cuda, cuda_runtime_dir, *, resolve=True):
    if os_name == "linux":
        return linux_dependencies(library, portable, portable_cuda, cuda_runtime_dir, resolve=resolve)
    if os_name == "windows":
        output = subprocess.check_output([find_dumpbin(), "/DEPENDENTS", str(library)],
                                         text=True, errors="replace")
        return {"needed": re.findall(r"^\s+(\S+\.dll)\s*$", output, flags=re.M | re.I)}
    output = subprocess.check_output(["otool", "-L", str(library)], text=True)
    install_name, *dependencies = [line.split(" (", 1)[0].strip() for line in output.splitlines()[1:]]
    require(install_name == f"@rpath/{library.name}", f"Unexpected Mach-O install name: {install_name}")
    require(all(name.startswith(("/usr/lib/", "/System/Library/")) for name in dependencies),
            f"Unexpected macOS dependency outside system libraries: {dependencies}")
    commands = subprocess.check_output(["otool", "-l", str(library)], text=True)
    require(not re.search(r"^\s*cmd LC_RPATH$", commands, re.M), "Unexpected Mach-O runtime search path")
    return {"needed": dependencies, "install_name": install_name}


def cuda_images(library, cuobjdump, architecture):
    images = {}
    for kind, flag, suffix in (("cubin", "--list-elf", "cubin"), ("ptx", "--list-ptx", "ptx")):
        output = subprocess.check_output([str(cuobjdump), flag, str(library)], text=True)
        targets = sorted(set(re.findall(rf"sm_(\d+)\.{suffix}\b", output)))
        require(targets == [architecture], f"Unexpected {kind} targets: {output}")
        images[kind] = targets
    return images


def check_runtime(files, info, *, cuda=False, runtime_dir=None, cuobjdump=None, inspect_only=False):
    portable_cuda = info["variant"] == PORTABLE_CUDA
    portable = portable_cuda or info["variant"] == PORTABLE_CPU
    if portable:
        require(info["os"] == "linux" and info["diagnostics"],
                "Portable profiles require Linux and Original diagnostics")
        expected = ("89", "13.0.88") if portable_cuda else ("", "")
        require((info["cuda_architecture"], info["cuda_toolkit"]) == expected,
                "Portable profile and CUDA metadata differ")
        require([name for name, data in files.items() if data.startswith(b"\x7fELF")] == [info["library"]],
                "Expected exactly one bundled ELF")
    require(not cuda or (info["cuda_architecture"] and not inspect_only),
            "--cuda needs a CUDA build and runtime validation")
    require(not cuobjdump or portable_cuda, "--cuobjdump needs a portable CUDA build")
    if runtime_dir:
        runtime_dir = runtime_dir.resolve()
        require(portable_cuda and (runtime_dir / CUDART_SONAME).is_file(),
                f"--cuda-runtime-dir needs a portable CUDA build and {CUDART_SONAME}")

    with TemporaryDirectory() as temp:
        root = Path(temp) / "extracted"
        for name, content in files.items():
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        library = root / info["library"]
        dependencies = runtime_dependencies(library, info["os"], portable, portable_cuda, runtime_dir,
                                            resolve=not inspect_only)
        if cuobjdump:
            dependencies["cuda_images"] = cuda_images(library, cuobjdump.resolve(), info["cuda_architecture"])
        require(dependencies["needed"], "No dynamic runtime dependencies reported")
        links_cuda = any(re.search(r"(?:cudart|nvcuda|libcuda\.)", name, re.I)
                         for name in dependencies["needed"])
        require(links_cuda == bool(info["cuda_architecture"]),
                "CUDA runtime linkage differs from build metadata")
        if inspect_only:
            return {"runtime": dependencies, "smoke_modes": []}
        if info["os"] in {"windows", "macos"}:
            print(f'Native imports: {", ".join(dependencies["needed"])}', flush=True)
        if info["os"] == "windows" and info["variant"] == "cpu":
            # CPU archives have no bundled dependencies. Probe the native
            # runtime search location and name any missing import DLLs.
            for name in dependencies["needed"]:
                try:
                    ctypes.WinDLL(name, winmode=0x00000800)  # LOAD_LIBRARY_SEARCH_SYSTEM32
                except OSError as error:
                    raise RuntimeError(f"Cannot load Windows dependency {name}: {error}") from error
        environment = {k: v for k, v in os.environ.items()
                       if not k.startswith("SOLARPILOT_") and k not in {"PYTHONPATH", "PYTHONHOME"}}
        if portable:
            environment = {k: v for k, v in environment.items() if not k.startswith("LD_")}
        if runtime_dir:
            environment["LD_LIBRARY_PATH"] = str(runtime_dir)
        if portable_cuda:
            if cuda and os.environ.get("LD_LIBRARY_PATH"):
                # GPU containers may expose the driver through their search path.
                paths = (environment.get("LD_LIBRARY_PATH"), os.environ["LD_LIBRARY_PATH"])
                environment["LD_LIBRARY_PATH"] = ":".join(path for path in paths if path)
            elif not cuda:
                environment["CUDA_VISIBLE_DEVICES"] = "-1"
        if info["os"] == "macos":
            environment = {k: v for k, v in environment.items() if not k.startswith("DYLD_")}
        environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
        modes = ["refactored", "multicore"]
        if info["diagnostics"]:
            modes.append("original")
        if cuda:
            modes.append("cuda")
        for mode in modes:
            subprocess.run([sys.executable, str(root / "example.py"), "--mode", mode, "--compare"],
                           cwd=temp, env=environment, check=True, timeout=90)
    return {"runtime": dependencies, "smoke_modes": modes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--inspect-only", action="store_true", help="Check structure and ABI without running the example")
    parser.add_argument("--cuda", action="store_true", help="Also run one CUDA/CPU check on an available GPU")
    parser.add_argument("--runtime-only", action="store_true",
                        help="Validate a trusted archive on a host without the pinned source checkout")
    parser.add_argument("--cuda-runtime-dir", type=Path,
                        help="Use this external libcudart directory for a portable CUDA archive")
    parser.add_argument("--cuobjdump", type=Path,
                        help="Verify CUDA cubin and PTX targets using this toolkit tool")
    args = parser.parse_args()
    files, info = inspect(args.archive, runtime_only=args.runtime_only)
    report = check_runtime(files, info, cuda=args.cuda, runtime_dir=args.cuda_runtime_dir,
                           cuobjdump=args.cuobjdump, inspect_only=args.inspect_only)
    print(json.dumps({"sha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(),
                      "members": sorted(files), **report}, indent=2))


if __name__ == "__main__":
    main()
