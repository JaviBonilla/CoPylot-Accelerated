"""Load the bundled library by absolute path and expose the pinned CoPylot API."""

from contextlib import ExitStack
import ctypes
import json
import os
from pathlib import Path

from copylot import CoPylot as UpstreamCoPylot

PACKAGE = Path(__file__).resolve().parents[1]


def build_info():
    return json.loads((PACKAGE / "BUILD.json").read_text(encoding="utf-8"))


class CoPylot(UpstreamCoPylot):
    """Use the bundle's distinct library name without changing working directory."""

    def __init__(self):
        info = build_info()
        library = PACKAGE / info["library"]
        with ExitStack() as dll_directories:
            if os.name == "nt":
                dll_directories.enter_context(os.add_dll_directory(str(library.parent)))
                if info["cuda_toolkit"] and os.environ.get("CUDA_PATH"):
                    cuda_bin = Path(os.environ["CUDA_PATH"]) / "bin"
                    dll_directories.enter_context(os.add_dll_directory(str(cuda_bin)))
            self.pdll = ctypes.CDLL(str(library))
