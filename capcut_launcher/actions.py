"""Supported actions: start the executable normally or open a directory."""

import os
import subprocess
import sys
from pathlib import Path

from .discovery import is_capcut_executable, is_directory


def launch_capcut(executable: Path) -> None:
    if sys.platform != "win32":
        raise OSError("Launching CapCut requires Windows.")
    if not is_capcut_executable(executable):
        raise OSError("CapCut.exe is missing. Choose its location in Settings.")
    executable = executable.resolve()
    subprocess.Popen([str(executable)], cwd=str(executable.parent))


def open_drafts(directory: Path) -> None:
    if sys.platform != "win32":
        raise OSError("Opening drafts in File Explorer requires Windows.")
    if not is_directory(directory):
        raise OSError("The drafts directory is missing. Choose its location in Settings.")
    os.startfile(str(directory.resolve()))
