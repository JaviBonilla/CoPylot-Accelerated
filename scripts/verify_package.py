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


def linux_dependencies(library, portable, portable_cuda, cuda_runtime_dir):
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
        resolved = subprocess.check_output(["ldd", "-r", str(library)], text=True,
                                           stderr=subprocess.STDOUT, env=environment)
        require(not re.search(r"not found|undefined symbol", resolved), resolved)
        if cuda_runtime_dir:
            match = re.search(r"^\s*libcudart\.so\.13 => (.+?) \(0x", resolved, flags=re.M)
            require(match and Path(match[1]).resolve() == (cuda_runtime_dir / CUDART_SONAME).resolve(),
                    "CUDA runtime did not resolve to the requested external library")
        print(resolved, end="")
    return {"needed": needed, "symbols": symbols, "elf": "ELF64 x86-64 DYN", "isa_notes": isa}


def runtime_dependencies(library, os_name, portable, portable_cuda, cuda_runtime_dir):
    if os_name == "linux":
        return linux_dependencies(library, portable, portable_cuda, cuda_runtime_dir)
    if os_name == "windows":
        output = subprocess.check_output(["dumpbin", "/DEPENDENTS", str(library)],
                                         text=True, errors="replace")
        return {"needed": re.findall(r"^\s+(\S+\.dll)\s*$", output, flags=re.M | re.I)}
    output = subprocess.check_output(["otool", "-L", str(library)], text=True)
    needed = [line.split(" (", 1)[0].strip() for line in output.splitlines()[2:]]
    require(all(name.startswith(("/usr/lib/", "/System/Library/")) for name in needed),
            "Unexpected macOS dependency outside system libraries")
    return {"needed": needed}


def cuda_images(library, cuobjdump, architecture):
    images = {}
    for kind, flag, suffix in (("cubin", "--list-elf", "cubin"), ("ptx", "--list-ptx", "ptx")):
        output = subprocess.check_output([str(cuobjdump), flag, str(library)], text=True)
        targets = sorted(set(re.findall(rf"sm_(\d+)\.{suffix}\b", output)))
        require(targets == [architecture], f"Unexpected {kind} targets: {output}")
        images[kind] = targets
    return images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--cuda", action="store_true", help="Also run one CUDA/CPU check on an available GPU")
    parser.add_argument("--runtime-only", action="store_true",
                        help="Validate a trusted archive on a host without the pinned source checkout")
    parser.add_argument("--cuda-runtime-dir", type=Path,
                        help="Use this external libcudart directory for a portable CUDA archive")
    parser.add_argument("--cuobjdump", type=Path,
                        help="Verify CUDA cubin and PTX targets using this toolkit tool")
    args = parser.parse_args()
    files, info = inspect(args.archive, runtime_only=args.runtime_only)
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
    require(not args.cuda or info["cuda_architecture"], "--cuda needs a CUDA build")
    require(not args.cuobjdump or portable_cuda, "--cuobjdump needs a portable CUDA build")
    runtime_dir = args.cuda_runtime_dir
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
        dependencies = runtime_dependencies(library, info["os"], portable, portable_cuda, runtime_dir)
        if args.cuobjdump:
            dependencies["cuda_images"] = cuda_images(library, args.cuobjdump.resolve(), info["cuda_architecture"])
        require(dependencies["needed"], "No dynamic runtime dependencies reported")
        links_cuda = any("cudart" in name.lower() for name in dependencies["needed"])
        require(links_cuda == bool(info["cuda_architecture"]),
                "CUDA runtime linkage differs from build metadata")
        environment = {k: v for k, v in os.environ.items()
                       if not k.startswith("SOLARPILOT_") and k not in {"PYTHONPATH", "PYTHONHOME"}}
        if portable:
            environment = {k: v for k, v in environment.items() if not k.startswith("LD_")}
        if runtime_dir:
            environment["LD_LIBRARY_PATH"] = str(runtime_dir)
        if portable_cuda:
            if args.cuda and os.environ.get("LD_LIBRARY_PATH"):
                # GPU containers may expose the driver through their search path.
                paths = (environment.get("LD_LIBRARY_PATH"), os.environ["LD_LIBRARY_PATH"])
                environment["LD_LIBRARY_PATH"] = ":".join(path for path in paths if path)
            elif not args.cuda:
                environment["CUDA_VISIBLE_DEVICES"] = "-1"
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
