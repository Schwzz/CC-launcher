# CC Launcher

A small, independent Windows desktop launcher for CapCut, built with Python and
PySide6. A quiet project list, a normal launch button, and a few appearance
settings. It is not affiliated with CapCut or ByteDance.

## Run on Windows

Use Python **3.10 or newer**, 64-bit, on Windows 10/11. Install CapCut separately.
From the repository directory in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m capcut_launcher
```

The only runtime dependency is `PySide6-Essentials` (the PySide6 distribution
containing QtCore, QtGui, and QtWidgets, plus its matching Shiboken dependency).
Qt Addons, web engines, databases, and network services are not needed. There is
no installer or standalone executable in this initial version.

## What it does

- Soft charcoal and light themes, rounded panels, a short list reveal animation,
  and a custom accent color picker.
- A read-only project dashboard with case-insensitive search and sorting by
  modification date or name. Hover a project to see its directory.
- Background folder scans, drawn project rows, and no thumbnail decoding,
  timeline loading, file watching, or continuous polling. Use **Refresh** after
  creating or editing a project in CapCut.
- **Launch CapCut** starts `CapCut.exe` with no arguments. **Open drafts folder**
  opens the selected directory with the Windows shell (normally File Explorer).
- **Settings** provides executable/drafts overrides and saves preferences locally.
  Clear an override to restore automatic detection. Cancel discards changes.
- Missing installations, stale/invalid paths, empty lists, unreadable folders,
  corrupt metadata, and preference read/write errors have explicit UI handling.

Project cards are informational. Open individual projects from inside CapCut;
double-clicking a card does not launch it. The launcher does not bypass CapCut's
home screen after launch, replace its editor, or alter its behavior.

## Detection and its limits

Installation detection checks these common locations, in this order for each
base directory:

```text
<base>\Apps\CapCut.exe
<base>\CapCut.exe
<base>\Apps\<numeric-version>\CapCut.exe   (highest version first)
```

Bases are `%LOCALAPPDATA%\CapCut`, `%PROGRAMFILES%\CapCut`, and
`%PROGRAMFILES(X86)%\CapCut`. This is a filename/existence check, not executable
signature verification. Only select a CapCut installation you trust. Store,
portable, custom, and future layouts may need a manual override.

The default drafts directory is:

```text
%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft
```

Select the parent containing individual draft folders, not a single project.
Only immediate subdirectories containing `draft_meta_info.json` or
`draft_content.json` appear. Symlinked project directories are skipped. The
launcher reads at most 1 MiB of each metadata file and never parses timeline
content. It uses `draft_name` and `tm_draft_modified` when available (Unix
seconds, milliseconds, or microseconds), otherwise folder names and filesystem
modification dates. Dates display in the machine's local timezone.

**CapCut metadata is a best-effort compatibility assumption, not a documented
CapCut API.** Encrypted, cloud-only, or differently structured drafts may be absent
or show folder names/dates. A card does not prove that a draft can be opened by
CapCut. Detection patterns and metadata interpretation have been tested with
fixtures, not a real CapCut installation.

## Local preferences and data safety

Preferences are saved atomically to:

- Windows: `%LOCALAPPDATA%\CC-launcher\preferences.json`
- Linux development: `$XDG_CONFIG_HOME/CC-launcher/preferences.json`, falling back
  to `~/.config/CC-launcher/preferences.json`.

The file contains only the theme, accent color, and optional path overrides.
Nothing is written until preferences are saved. Delete that file to reset the
launcher. No project list is cached, no telemetry is collected, and the launcher
makes no network requests.

The launcher does not write CapCut files or drafts, read/write registry keys,
touch licensing, or use undocumented launch flags, protocols, or direct project
opening. Starting CapCut hands control to the actual application, which retains
its own normal behavior and file writes.

## Tests and Linux development

Run from the repository root after installing the requirements:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

Linux/cloud equivalent:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -v
```

There are **32 tests**, using `unittest` and Qt's bundled test helpers. Tests use
temporary Windows-layout directories and mock the Windows launch/shell actions;
they never launch CapCut. Coverage includes version selection, missing and
inaccessible paths, project names/dates, corrupt and oversized metadata, read-only
scanning, preference persistence/failure handling, launch argument boundaries,
background scanning, search, sorting, empty states, and both theme renders.

The UI can run on a Linux desktop with `python -m capcut_launcher`. For headless
startup, set `QT_QPA_PLATFORM=offscreen`; no visible desktop window is expected.
Windows-only buttons remain disabled. A drafts override can point at local test
fixtures for UI development. Linux desktop sessions need Qt's normal platform
libraries; the offscreen tests do not require X11 or CapCut.

### Still requires real Windows testing

Automated Linux checks do **not** verify:

- Detection against actual installed CapCut versions and their current metadata.
- Normal CapCut process launch, including vendor launchers and permissions.
- File Explorer handoff and Windows native file/color dialogs.
- Windows fonts, DPI scaling, multi-monitor layout, and native window decoration.

Before relying on the launcher, run the suite on Windows, launch it with a real
CapCut installation, check detected paths (and manual overrides), search/sort
actual drafts, launch CapCut, open the drafts folder, and restart the launcher
to confirm saved appearance. Also try a missing executable, an empty drafts
folder, and a removed override directory. No direct-project-opening capability
is claimed or implemented.
