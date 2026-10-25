"""Read-only, best-effort discovery. No Qt or Windows API dependency."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Project:
    name: str
    path: Path
    modified: float


@dataclass(frozen=True)
class ProjectScan:
    projects: tuple[Project, ...] = ()
    warnings: tuple[str, ...] = ()


def is_capcut_executable(path: Path) -> bool:
    """Check the selected filename, not the binary's identity or authenticity."""
    try:
        return path.name.lower() == "capcut.exe" and path.is_file()
    except (OSError, ValueError):
        return False


def is_directory(path: Path) -> bool:
    try:
        return path.is_dir()
    except (OSError, ValueError):
        return False


def detect_installation(environ: Mapping[str, str]) -> Path | None:
    """Probe common locations only, preferring a stable executable if present."""
    bases = [Path(environ[key]) / "CapCut" for key in
             ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)") if environ.get(key)]
    for base in bases:
        for executable in (base / "Apps" / "CapCut.exe", base / "CapCut.exe"):
            if is_capcut_executable(executable):
                return executable
        apps = base / "Apps"
        try:
            versions = [p for p in apps.iterdir() if p.is_dir()
                        and re.fullmatch(r"\d+(?:\.\d+)*", p.name)]
        except OSError:
            continue
        versions.sort(key=lambda p: tuple(int(n) for n in p.name.split(".")), reverse=True)
        for version in versions:
            executable = version / "CapCut.exe"
            if is_capcut_executable(executable):
                return executable
    return None


def detect_drafts(environ: Mapping[str, str]) -> Path | None:
    if not environ.get("LOCALAPPDATA"):
        return None
    path = Path(environ["LOCALAPPDATA"]) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    return path if is_directory(path) else None


def _modified_time(value: object, fallback: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return fallback
    try:
        stamp = float(value)
        # Observed metadata uses Unix microseconds; tolerate milliseconds/seconds.
        if stamp > 1e14:
            stamp /= 1_000_000
        elif stamp > 1e11:
            stamp /= 1_000
        if not math.isfinite(stamp) or stamp <= 0:
            return fallback
        datetime.fromtimestamp(stamp)
        return stamp
    except (ValueError, OverflowError, OSError):
        return fallback


def scan_projects(directory: Path) -> ProjectScan:
    """List immediate draft folders. Never write to or recursively scan drafts."""
    projects: list[Project] = []
    warnings: list[str] = []
    try:
        children = list(directory.iterdir())
    except OSError as exc:
        return ProjectScan(warnings=(f"Cannot read drafts directory: {exc}",))

    for child in children:
        try:
            if child.is_symlink() or not child.is_dir():
                continue
            metadata_path = child / "draft_meta_info.json"
            content_path = child / "draft_content.json"
            if not (metadata_path.is_file() or content_path.is_file()):
                continue
            name = child.name
            modified = max(p.stat().st_mtime for p in (child, metadata_path, content_path) if p.exists())
            if metadata_path.is_file():
                try:
                    # Bound reads; timeline content can be huge and is never parsed.
                    with metadata_path.open("rb") as stream:
                        raw = stream.read(1_048_577)
                    if len(raw) > 1_048_576:
                        raise ValueError("metadata exceeds 1 MiB")
                    metadata = json.loads(raw.decode("utf-8-sig"))
                    if not isinstance(metadata, dict):
                        raise ValueError("metadata is not an object")
                    candidate = metadata.get("draft_name")
                    if isinstance(candidate, str) and candidate.strip():
                        name = " ".join(candidate.split())[:200]
                    modified = _modified_time(metadata.get("tm_draft_modified"), modified)
                except (OSError, ValueError, UnicodeError, RecursionError):
                    warnings.append(f"{child.name}: metadata unavailable; using folder details.")
            projects.append(Project(name, child, modified))
        except OSError:
            warnings.append(f"{child.name}: could not read project details.")
    return ProjectScan(tuple(projects), tuple(warnings))
