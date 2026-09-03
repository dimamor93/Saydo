from __future__ import annotations

import os
import sys
from pathlib import Path


def configure_nvidia_runtime() -> None:
    """Make pip-installed NVIDIA CUDA DLLs available on Windows."""

    if sys.platform != "win32":
        return

    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    nvidia_dir = site_packages / "nvidia"

    if not nvidia_dir.exists():
        return

    dll_directories = [
        nvidia_dir / "cublas" / "bin",
        nvidia_dir / "cuda_nvrtc" / "bin",
        nvidia_dir / "cudnn" / "bin",
    ]

    for directory in dll_directories:
        if directory.exists():
            os.add_dll_directory(str(directory))

            current_path = os.environ.get("PATH", "")
            if str(directory) not in current_path.split(os.pathsep):
                os.environ["PATH"] = (
                    str(directory)
                    + os.pathsep
                    + current_path
                )