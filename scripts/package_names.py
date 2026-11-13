"""Names shared by package production, verification and release evidence."""

PACKAGE_PREFIX = "copylot-accelerated"
LOCAL_PREFIX = f"{PACKAGE_PREFIX}-local"
LIBRARY_BASENAME = "copylot_accelerated"
WRAPPER = f"python/{LIBRARY_BASENAME}.py"
PORTABLE_CPU = "cpu-glibc2.34"
PORTABLE_CUDA = "cuda13.0-sm89-glibc2.34"


def native_library(os_name):
    suffix = ".dll" if os_name == "windows" else ".so"
    return f"lib/{LIBRARY_BASENAME}{suffix}"


def package_variant(platform, backend):
    if platform == "linux-x86_64":
        return PORTABLE_CUDA if backend == "cuda" else PORTABLE_CPU
    return "cpu"


def archive_prefix(revision_short, platform, variant):
    return f"{LOCAL_PREFIX}-{revision_short}-{platform}-{variant}"


def package_identity(platform, backend, run_id, attempt, revision):
    suffix = ".zip" if platform.startswith("windows-") else ".tar.gz"
    archive = archive_prefix(revision[:12], platform, package_variant(platform, backend)) + suffix
    return {"build_run_id": run_id, "build_run_attempt": attempt, "source_revision": revision,
            "platform": platform, "archive": archive}


def build_artifact_name(backend, platform, run_id, attempt):
    return f"{PACKAGE_PREFIX}-{backend}-{platform}-{run_id}-{attempt}"
