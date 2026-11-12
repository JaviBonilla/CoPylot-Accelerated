#!/usr/bin/env python3
"""Build or validate one CPack package artifact."""

import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from verify_package import PORTABLE_CPU, PORTABLE_CUDA, ROOT, check_runtime, inspect, require, verify_sources

PLATFORMS = ("linux-x86_64", "windows-x86_64", "macos-x86_64", "macos-arm64")
BUILD = ROOT / "build/native-package"
BUNDLE = BUILD / "artifact"
MANIFEST = "artifact.json"
SENSITIVE_LOG_LINE = re.compile(
    r"authorization\s*:|(?:password|passwd|token|secret|credentials?)\s*[:=]|"
    r"(?:https?|ssh)://[^/\s]+@|[?&](?:signature|sig|access_token)=|"
    r"\b(?:gh[pousr]_|github_pat_)[a-z0-9_]+|-----BEGIN .*PRIVATE KEY-----",
    re.IGNORECASE,
)
NLOPT_DIAGNOSTIC = re.compile(
    r"\b(?:fatal error|error|warning):|^ld:|Undefined symbols|symbol\(s\) not found",
    re.IGNORECASE,
)


def git(*args, directory=None):
    return subprocess.check_output(["git", *args], cwd=directory or ROOT, text=True).strip()


def verify_archive(archive, identity, variant, *, upstream, source_root=None):
    checksum = archive.with_name(f"{archive.name}.sha256").read_text(encoding="ascii").split()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    require(checksum == [digest, archive.name], f"SHA-256 sidecar does not match {archive.name}")
    try:
        files, info = inspect(archive, runtime_only=True, source_root=source_root)
        os_name, architecture = identity["platform"].split("-", 1)
        require(info["source_revision"] == identity["source_revision"] and not info["source_dirty_at_configure"],
                "Archive source revision does not match the selected clean build")
        cuda_metadata = ("13.0.88", "89") if variant == PORTABLE_CUDA else ("", "")
        require((info["os"], info["architecture"], info["variant"]) == (os_name, architecture, variant)
                and info["diagnostics"] and (info["cuda_toolkit"], info["cuda_architecture"]) == cuda_metadata,
                "Archive platform, backend or diagnostics do not match the selected package")
        verify_sources(files, info, upstream=upstream, source_root=source_root)
    except KeyError as error:
        raise ValueError(f"Unsupported package layout for this validator (missing {error})") from None
    except FileNotFoundError as error:
        raise ValueError("Build source checkout lacks files required by this package validator") from error
    return digest, files, info


def diagnostic_line(line):
    if SENSITIVE_LOG_LINE.search(line):
        return "[credential-like diagnostic omitted]\n"
    for path in (ROOT, Path(os.environ.get("RUNNER_TEMP") or BUILD), Path.home()):
        for spelling in (path.as_posix(), str(path)):
            line = re.sub(re.escape(spelling), "<runner-path>", line, flags=re.IGNORECASE)
    return line


def report_nlopt_failure(diagnostics):
    directory = BUILD / "nlopt-config"
    with (diagnostics / "nlopt.log").open("w", encoding="utf-8") as log:
        for name in ("configure.log", "configure-error.log", "config.log"):
            path = directory / name
            if not path.is_file():
                continue
            # config.log also contains raw probe commands and a cache/environment dump.
            # Keep compiler diagnostics from the last probe and the configure failure.
            lines = deque(maxlen=40)
            with path.open(encoding="utf-8", errors="replace") as source:
                for line in source:
                    if name == "config.log":
                        if line.startswith("## Cache variables."):
                            break
                        if re.match(r"configure:\d+: checking ", line):
                            lines.clear()
                        elif line.startswith("configure:"):
                            if not re.match(r"configure:\d+: (?:result:|error:|\$\? = )", line):
                                continue
                        elif not NLOPT_DIAGNOSTIC.search(line):
                            continue
                    lines.append(diagnostic_line(line))
            if lines:
                summary = f"NLopt {name} (tail)\n" + "".join(lines)
                print(summary, end="\n", flush=True)
                log.write(summary + "\n")


def run_native_phase(phase, command, *, env=None):
    diagnostics = BUILD / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    log_path = diagnostics / f"{phase}.log"
    with log_path.open("w", encoding="utf-8") as log:
        with subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, encoding="utf-8", errors="replace") as process:
            for line in process.stdout:
                line = diagnostic_line(line)
                print(line, end="", flush=True)
                log.write(line)
            status = process.wait()
        log.write(f"Exit status: {status}\n")
    if status:
        if phase == "configure" and "NLopt configure failed" in log_path.read_text(encoding="utf-8"):
            report_nlopt_failure(diagnostics)
        raise subprocess.CalledProcessError(status, command)


def build_native(identity):
    subprocess.run([sys.executable, "scripts/bootstrap.py"], cwd=ROOT, check=True)
    os_name, architecture = identity["platform"].split("-", 1)
    if os_name == "windows":
        generator = ["-G", "Visual Studio 17 2022", "-A", "x64"]
    else:
        generator = ["-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                     f"-DCMAKE_OSX_ARCHITECTURES={architecture}", "-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0"]
    run_native_phase("configure", [
        "cmake", "-S", ".", "-B", str(BUILD), *generator,
        "-DBUILD_TESTING=OFF", "-DCOPILOT_LOCAL_PACKAGE=ON", "-DSOLARPILOT_ENABLE_CUDA=OFF",
        "-DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON",
    ])
    run_native_phase("build", ["cmake", "--build", str(BUILD), "--target", "copilot_package_library",
                               "--config", "Release", "--parallel", "4"])
    environment = dict(os.environ, SOURCE_DATE_EPOCH=git("show", "-s", "--format=%ct", "HEAD"))
    run_native_phase("cpack", ["cpack", "--config", str(BUILD / "CPackConfig.cmake"), "-C", "Release"],
                     env=environment)
    return BUILD / "packages" / identity["archive"]


def build(identity, variant):
    require(not git("status", "--porcelain"), "Use a clean checkout for packaging")
    require(not BUNDLE.exists(), f"Move the existing artifact directory before rebuilding: {BUNDLE}")
    if identity["platform"] == "linux-x86_64":
        suffix = "_cuda_portable" if variant == PORTABLE_CUDA else "_portable"
        subprocess.run(["bash", f"scripts/package_linux{suffix}.sh", "--inspect-only"], cwd=ROOT, check=True)
        archive = ROOT / f"build/package-linux{suffix.replace('_', '-')}/packages" / identity["archive"]
    else:
        archive = build_native(identity)
    digest, files, _ = verify_archive(archive, identity, variant, upstream=True)

    BUNDLE.mkdir(parents=True)
    for path in (archive, archive.with_name(f"{archive.name}.sha256")):
        shutil.copy2(path, BUNDLE)
    (BUNDLE / MANIFEST).write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**identity, "sha256": digest, "members": sorted(files)}, indent=2))


def validate(directory, identity, variant, *, source_root, cuda=False, runtime_dir=None):
    tooling_revision = git("rev-parse", "HEAD")
    print(f"Validation tooling revision: {tooling_revision}", flush=True)
    archive = directory / identity["archive"]
    require({p.name for p in directory.iterdir()} == {archive.name, f"{archive.name}.sha256", MANIFEST},
            "Unsupported package layout for this validator (unexpected files or archive name in the selected artifact)")
    actual_identity = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    require(isinstance(actual_identity, dict) and actual_identity.keys() == identity.keys(),
            "Unsupported artifact manifest layout for this validator")
    require(actual_identity == identity, "Artifact identity differs from the selected build run and attempt")
    digest, files, info = verify_archive(archive, identity, variant, upstream=False, source_root=source_root)
    report = check_runtime(files, info, cuda=cuda, runtime_dir=runtime_dir)
    print(json.dumps({**identity, "validation_revision": tooling_revision, "sha256": digest,
                      "members": sorted(files), **report}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "validate"))
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--cuda", action="store_true", help="Execute the packaged CUDA smoke case")
    parser.add_argument("--cuda-runtime-dir", type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--directory", type=Path, help="Downloaded artifact directory for validation")
    parser.add_argument("--source-directory", type=Path,
                        help="Build source checkout for validation (defaults to the tooling checkout)")
    args = parser.parse_args()
    require(args.source_directory is None or args.operation == "validate",
            "--source-directory is only for package validation")
    source_root = (args.source_directory or ROOT).resolve()
    require(re.fullmatch(r"[0-9a-f]{40}", args.revision)
            and git("rev-parse", "HEAD", directory=source_root) == args.revision,
            "Build source checkout does not match the full selected Build revision")
    require(args.run_id > 0 and args.run_attempt > 0, "Build run identifiers must be positive")
    require(args.backend != "cuda" or args.platform == "linux-x86_64", "CUDA packages require Linux x86-64")
    if args.platform == "linux-x86_64":
        variant = PORTABLE_CUDA if args.backend == "cuda" else PORTABLE_CPU
    else:
        variant = "cpu"
    require(not (args.cuda or args.cuda_runtime_dir) or (args.operation == "validate" and variant == PORTABLE_CUDA),
            "CUDA runtime options require validation of a portable CUDA artifact")
    suffix = ".zip" if args.platform.startswith("windows-") else ".tar.gz"
    identity = {
        "build_run_id": args.run_id,
        "build_run_attempt": args.run_attempt,
        "source_revision": args.revision,
        "platform": args.platform,
        "archive": f"hermite-optics-local-{args.revision[:12]}-{args.platform}-{variant}{suffix}",
    }
    if args.operation == "build":
        build(identity, variant)
    else:
        require(args.directory is not None, "Validation requires the downloaded --directory")
        validate(args.directory, identity, variant, source_root=source_root,
                 cuda=args.cuda, runtime_dir=args.cuda_runtime_dir)


if __name__ == "__main__":
    main()
