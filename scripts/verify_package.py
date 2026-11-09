#!/usr/bin/env python3
"""Inspect a locally built CPack archive and run its extracted smoke example."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PORTABLE_VARIANT = "cpu-glibc2.34"
PORTABLE_MAX = {"GLIBC": (2, 34), "GLIBCXX": (3, 4, 29), "CXXABI": (1, 3, 13)}
PORTABLE_NEEDED = {"libc.so.6", "libm.so.6", "libstdc++.so.6", "libgcc_s.so.1",
                   "ld-linux-x86-64.so.2", "libpthread.so.0", "libdl.so.2", "librt.so.1"}
LICENSES = {
    "licenses/SSC-LICENSE.txt", "licenses/SolarPILOT-LICENSE.md",
    "licenses/SolTrace-LICENSE.md", "licenses/NLopt-LICENSE.htm",
    "licenses/lp_solve-LICENSE.htm", "licenses/RapidXML-license.txt",
}
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
    require(info["os"] == os_names.get(platform.system())
            and info["architecture"] == "x86_64"
            and platform.machine().lower() in {"amd64", "x86_64"}, "Use a matching native host")
    require(info["distribution"] == "local-validation-only"
            and info["redistribution"] == "blocked-pending-review", "Incorrect distribution status")
    revision = info["source_revision"]
    require(re.fullmatch(r"[0-9a-f]{40}", revision), "Invalid source revision")
    configured_revision = revision[:12] + ("-dirty" if info["source_dirty_at_configure"] else "")
    expected_prefix = f'hermite-optics-local-{configured_revision}-{info["os"]}-x86_64-{info["variant"]}'
    require(prefix == expected_prefix and info["build_type"] == "Release",
            "Archive name or build configuration differs from metadata")
    suffix = ".dll" if info["os"] == "windows" else ".so"
    library = f"lib/hermite_optics{suffix}"
    require(info["library"] == library, "Unexpected library path")
    require(set(files) == set(SOURCES) | {"BUILD.json", "python/copylot.py", library},
            "Archive differs from the package allowlist")
    private = re.compile(rb"/(?:home|tmp|Users|workspace|Volumes|_work)/"
                         rb"|[A-Za-z]:[\\/]+(?:Users|repositories|a|_work)[\\/]", re.I)
    for name, content in files.items():
        require(not private.search(content), f"Local path in archive member: {name}")
    if not runtime_only:
        verify_sources(files, info)
    return files, info


def verify_sources(files, info):
    checkout = str(ROOT).encode()
    checkout_windows = str(ROOT).replace("/", "\\").encode()
    for name, content in files.items():
        require(checkout not in content and checkout_windows not in content,
                f"Checkout path in archive member: {name}")
    for target, source in SOURCES.items():
        require(files[target] == (ROOT / source).read_bytes(), f"Altered package file: {target}")
    inventory = json.loads((ROOT / "docs/licensing-inventory.json").read_text(encoding="utf-8"))
    for component in inventory["components"]:
        license_copy = files[component["visible_license_copy"]]
        require(hashlib.sha256(license_copy).hexdigest() == component["sha256"],
                f'License checksum differs from inventory: {component["component"]}')
        require(license_copy == (ROOT / component["upstream_license_path"]).read_bytes(),
                f'License differs from pinned source: {component["component"]}')
    wrapper = (ROOT / "SolarPILOT/deploy/api/copylot.py").read_text(encoding="utf-8")
    wrapper = re.sub(r"\n[ \t]*# self\.pdll = CDLL\([^\n]*", "", wrapper)
    require(files["python/copylot.py"].decode().replace("\r\n", "\n") == wrapper,
            "Upstream wrapper differs beyond removed developer-path comments")
    lock = json.loads((ROOT / "repos.lock.json").read_text())
    require(info["dependencies"] == {name: pin["patched_sha"] for name, pin in lock.items()},
            "Dependency metadata differs from the pins")


def version_tuple(value):
    return tuple(map(int, value.split(".")))


def linux_dependencies(library, portable):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("LD_")}
    environment["LC_ALL"] = "C"

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
        require(set(needed) <= PORTABLE_NEEDED, f"Unexpected portable ELF dependencies: {needed}")
        require(all(re.fullmatch(r"[0-9.]+", value) and version_tuple(value) <= PORTABLE_MAX[family]
                    for family, value in imports), f"Portable ELF ABI ceiling exceeded: {imports}")
        require(set(symbols) == set(PORTABLE_MAX), "Incomplete portable ELF version requirements")
        require(all(level.strip() == "x86-64-baseline" for level in isa), f"Unexpected x86 ISA: {isa}")
        resolved = subprocess.check_output(["ldd", "-r", str(library)], text=True,
                                           stderr=subprocess.STDOUT, env=environment)
        require(not re.search(r"not found|undefined symbol", resolved), resolved)
        print(resolved, end="")
    return {"needed": needed, "symbols": symbols, "elf": "ELF64 x86-64 DYN", "isa_notes": isa}


def runtime_dependencies(library, os_name, portable):
    if os_name == "linux":
        return linux_dependencies(library, portable)
    if os_name == "windows":
        output = subprocess.check_output(["dumpbin", "/DEPENDENTS", str(library)],
                                         text=True, errors="replace")
        return {"needed": re.findall(r"^\s+(\S+\.dll)\s*$", output, flags=re.M | re.I)}
    output = subprocess.check_output(["otool", "-L", str(library)], text=True)
    needed = [line.split(" (", 1)[0].strip() for line in output.splitlines()[2:]]
    require(all(name.startswith(("/usr/lib/", "/System/Library/")) for name in needed),
            "Unexpected macOS dependency outside system libraries")
    return {"needed": needed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--cuda", action="store_true", help="Also run one CUDA/CPU check on an available GPU")
    parser.add_argument("--runtime-only", action="store_true",
                        help="Validate a trusted archive on a host without the pinned source checkout")
    args = parser.parse_args()
    files, info = inspect(args.archive, runtime_only=args.runtime_only)
    portable = info["variant"] == PORTABLE_VARIANT
    if portable:
        require(info["os"] == "linux" and info["diagnostics"] and not info["cuda_architecture"]
                and not info["cuda_toolkit"], "Portable profile requires Linux CPU and Original diagnostics")
        require([name for name, data in files.items() if data.startswith(b"\x7fELF")] == [info["library"]],
                "Expected exactly one bundled ELF")
    require(not args.cuda or info["cuda_architecture"], "--cuda needs a CUDA build")

    with TemporaryDirectory() as temp:
        root = Path(temp) / "extracted"
        for name, content in files.items():
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        dependencies = runtime_dependencies(root / info["library"], info["os"], portable)
        require(dependencies["needed"], "No dynamic runtime dependencies reported")
        links_cuda = any("cudart" in name.lower() for name in dependencies["needed"])
        require(links_cuda == bool(info["cuda_architecture"]),
                "CUDA runtime linkage differs from build metadata")
        environment = {k: v for k, v in os.environ.items()
                       if not k.startswith("SOLARPILOT_") and k not in {"PYTHONPATH", "PYTHONHOME"}}
        if portable:
            environment = {k: v for k, v in environment.items() if not k.startswith("LD_")}
        environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
        modes = ["refactored", "multicore"]
        if info["diagnostics"]:
            modes.append("original")
        if args.cuda:
            modes.append("cuda")
        for mode in modes:
            subprocess.run([sys.executable, str(root / "example.py"), "--mode", mode, "--compare"],
                           cwd=temp, env=environment, check=True, timeout=90)
    print(json.dumps({"sha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(),
                      "members": sorted(files), "runtime": dependencies, "smoke_modes": modes}, indent=2))


if __name__ == "__main__":
    main()
