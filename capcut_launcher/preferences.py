"""Only launcher preferences are written, outside the CapCut directories."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_ACCENT = "#B6E3CF"


@dataclass
class Preferences:
    theme: str = "dark"
    accent: str = DEFAULT_ACCENT
    executable: str = ""
    drafts: str = ""


def preferences_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "CC-launcher" / "preferences.json"


def load_preferences(path: Path) -> tuple[Preferences, str | None]:
    try:
        with path.open("rb") as stream:
            raw = stream.read(65_537)
        if len(raw) > 65_536:
            raise ValueError("preferences file is too large")
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("preferences must be an object")
        prefs = Preferences()
        if data.get("theme") in ("dark", "light"):
            prefs.theme = data["theme"]
        if isinstance(data.get("accent"), str) and re.fullmatch(r"#[0-9a-fA-F]{6}", data["accent"]):
            prefs.accent = data["accent"]
        for key in ("executable", "drafts"):
            if isinstance(data.get(key), str) and "\x00" not in data[key]:
                setattr(prefs, key, data[key])
        return prefs, None
    except FileNotFoundError:
        return Preferences(), None
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        return Preferences(), f"Could not load preferences; using defaults. {exc}"


def save_preferences(path: Path, prefs: Preferences) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="preferences-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(asdict(prefs), stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
