#!/usr/bin/env python3
"""Build or validate one native Windows/macOS CPU package artifact."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from verify_package import ROOT, check_runtime, inspect, require, verify_sources

PLATFORMS = ("windows-x86_64", "macos-x86_64", "macos-arm64")
BUILD = ROOT / "build/native-package"
BUNDLE = BUILD / "artifact"
MANIFEST = "artifact.json"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def verify_archive(archive, identity, *, upstream):
    checksum = archive.with_name(f"{archive.name}.sha256").read_text(encoding="ascii").split()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    require(checksum == [digest, archive.name], f"SHA-256 sidecar does not match {archive.name}")
    files, info = inspect(archive, runtime_only=True)
    os_name, architecture = identity["platform"].split("-", 1)
    require(info["source_revision"] == identity["source_revision"] and not info["source_dirty_at_configure"],
            "Archive source revision does not match the selected clean build")
    require((info["os"], info["architecture"], info["variant"]) == (os_name, architecture, "cpu")
            and info["diagnostics"] and not info["cuda_toolkit"] and not info["cuda_architecture"],
            "Expected the selected CPU package with Original diagnostics")
    verify_sources(files, info, upstream=upstream)
    return digest, files, info


def build(identity):
    require(not git("status", "--porcelain"), "Use a clean checkout for native packaging")
    require(not BUNDLE.exists(), f"Move the existing artifact directory before rebuilding: {BUNDLE}")
    subprocess.run([sys.executable, "scripts/bootstrap.py"], cwd=ROOT, check=True)
    os_name, architecture = identity["platform"].split("-", 1)
    if os_name == "windows":
        generator = ["-G", "Visual Studio 17 2022", "-A", "x64"]
    else:
        generator = ["-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                     f"-DCMAKE_OSX_ARCHITECTURES={architecture}", "-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0"]
    subprocess.run([
        "cmake", "-S", ".", "-B", str(BUILD), *generator,
        "-DBUILD_TESTING=OFF", "-DCOPILOT_LOCAL_PACKAGE=ON", "-DSOLARPILOT_ENABLE_CUDA=OFF",
        "-DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON",
    ], cwd=ROOT, check=True)
    subprocess.run(["cmake", "--build", str(BUILD), "--target", "solarpilot", "--config", "Release",
                    "--parallel", "4"], cwd=ROOT, check=True)
    environment = dict(os.environ, SOURCE_DATE_EPOCH=git("show", "-s", "--format=%ct", "HEAD"))
    subprocess.run(["cpack", "--config", str(BUILD / "CPackConfig.cmake"), "-C", "Release"],
                   cwd=ROOT, check=True, env=environment)
    archive = BUILD / "packages" / identity["archive"]
    digest, files, _ = verify_archive(archive, identity, upstream=True)

    BUNDLE.mkdir()
    for path in (archive, archive.with_name(f"{archive.name}.sha256")):
        shutil.copy2(path, BUNDLE)
    (BUNDLE / MANIFEST).write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**identity, "sha256": digest, "members": sorted(files)}, indent=2))


def validate(directory, identity):
    archive = directory / identity["archive"]
    require({p.name for p in directory.iterdir()} == {archive.name, f"{archive.name}.sha256", MANIFEST},
            "Unexpected files or archive name in the selected artifact")
    actual_identity = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    require(actual_identity == identity, "Artifact identity differs from the selected build run and attempt")
    digest, files, info = verify_archive(archive, identity, upstream=False)
    report = check_runtime(files, info)
    print(json.dumps({**identity, "sha256": digest, "members": sorted(files), **report}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "validate"))
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--directory", type=Path, help="Downloaded artifact directory for validation")
    args = parser.parse_args()
    require(re.fullmatch(r"[0-9a-f]{40}", args.revision) and git("rev-parse", "HEAD") == args.revision,
            "Checkout does not match the full selected source revision")
    require(args.run_id > 0 and args.run_attempt > 0, "Build run identifiers must be positive")
    suffix = ".zip" if args.platform.startswith("windows-") else ".tar.gz"
    identity = {
        "build_run_id": args.run_id,
        "build_run_attempt": args.run_attempt,
        "source_revision": args.revision,
        "platform": args.platform,
        "archive": f"hermite-optics-local-{args.revision[:12]}-{args.platform}-cpu{suffix}",
    }
    if args.operation == "build":
        build(identity)
    else:
        require(args.directory is not None, "Validation requires the downloaded --directory")
        validate(args.directory, identity)


if __name__ == "__main__":
    main()
