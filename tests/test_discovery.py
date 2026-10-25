import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capcut_launcher.discovery import (
    detect_drafts, detect_installation, is_capcut_executable, scan_projects,
)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Real temporary directories stand in for Windows environment roots.
        self.environment = {"LOCALAPPDATA": str(self.root / "Local AppData"),
                            "PROGRAMFILES": str(self.root / "Program Files")}

    def file(self, relative, contents=""):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        return path

    def test_missing_installation_and_environment(self):
        self.assertIsNone(detect_installation({}))
        self.assertIsNone(detect_installation(self.environment))

    def test_stable_executable_is_preferred(self):
        expected = self.file("Local AppData/CapCut/Apps/CapCut.exe")
        self.file("Local AppData/CapCut/Apps/99.0.0/CapCut.exe")
        self.assertEqual(detect_installation(self.environment), expected)

    def test_latest_numeric_version_not_lexical_order(self):
        self.file("Local AppData/CapCut/Apps/9.0.0/CapCut.exe")
        expected = self.file("Local AppData/CapCut/Apps/10.2.0/CapCut.exe")
        self.file("Local AppData/CapCut/Apps/11.0.0/unrelated.exe")
        self.file("Local AppData/CapCut/Apps/cache/CapCut.exe")
        self.assertEqual(detect_installation(self.environment), expected)

    def test_program_files_fallback(self):
        expected = self.file("Program Files/CapCut/CapCut.exe")
        self.assertEqual(detect_installation(self.environment), expected)

    def test_program_files_x86_fallback(self):
        expected = self.file("Program Files x86/CapCut/Apps/1.0/CapCut.exe")
        self.assertEqual(detect_installation({"PROGRAMFILES(X86)": str(self.root / "Program Files x86")}), expected)

    def test_executable_validation(self):
        self.assertFalse(is_capcut_executable(self.root / "CapCut.exe"))
        self.assertFalse(is_capcut_executable(self.file("other.exe")))
        self.assertTrue(is_capcut_executable(self.file("CAPCUT.EXE")))
        folder = self.root / "folder" / "CapCut.exe"
        folder.mkdir(parents=True)
        self.assertFalse(is_capcut_executable(folder))

    def test_inaccessible_executable_is_not_detected(self):
        with patch.object(Path, "is_file", side_effect=PermissionError("access denied")):
            self.assertIsNone(detect_installation(self.environment))

    def test_drafts_only_detected_if_directory_exists(self):
        self.assertIsNone(detect_drafts({}))
        self.assertIsNone(detect_drafts(self.environment))
        expected = self.root / "Local AppData/CapCut/User Data/Projects/com.lveditor.draft"
        expected.mkdir(parents=True)
        self.assertEqual(detect_drafts(self.environment), expected)

    def test_project_name_and_microsecond_timestamp(self):
        self.file("drafts/id-one/draft_meta_info.json", json.dumps({
            "draft_name": "  Summer\n Film  ", "tm_draft_modified": 1_700_000_000_000_000}))
        result = scan_projects(self.root / "drafts")
        self.assertEqual(len(result.projects), 1)
        self.assertEqual(result.projects[0].name, "Summer Film")
        self.assertEqual(result.projects[0].modified, 1_700_000_000)
        self.assertFalse(result.warnings)

    def test_second_and_millisecond_timestamps(self):
        for i, value in enumerate((1_700_000_000, 1_700_000_000_000)):
            self.file(f"drafts/{i}/draft_meta_info.json", json.dumps({"tm_draft_modified": value}))
        self.assertEqual([p.modified for p in scan_projects(self.root / "drafts").projects],
                         [1_700_000_000, 1_700_000_000])

    def test_content_only_project_uses_folder_details_without_parsing_timeline(self):
        content = self.file("drafts/folder-name/draft_content.json", "not parsed")
        os.utime(content.parent, (1_700_000_000, 1_700_000_000))
        os.utime(content, (1_700_000_100, 1_700_000_100))
        result = scan_projects(self.root / "drafts")
        self.assertEqual(result.projects[0].name, "folder-name")
        self.assertEqual(result.projects[0].modified, 1_700_000_100)
        self.assertFalse(result.warnings)

    def test_malformed_and_oversized_metadata_fall_back(self):
        for i, data in enumerate(("bad json", "[]", "\ufeff{}", "x" * 1_048_577)):
            self.file(f"drafts/{i}/draft_meta_info.json", data)
        result = scan_projects(self.root / "drafts")
        self.assertEqual(len(result.projects), 4)
        self.assertEqual(len(result.warnings), 3)  # UTF-8 BOM is supported.

    def test_invalid_metadata_fields_fall_back(self):
        for i, timestamp in enumerate((None, "today", -1, float("inf"), True, 10**100)):
            self.file(f"drafts/{i}/draft_meta_info.json", json.dumps({
                "draft_name": ["wrong type"], "tm_draft_modified": timestamp}))
        for project in scan_projects(self.root / "drafts").projects:
            self.assertEqual(project.name, project.path.name)
            self.assertGreater(project.modified, 1_600_000_000)

    def test_unrelated_and_nested_folders_ignored(self):
        self.file("drafts/not-a-project/nested/draft_content.json")
        self.file("drafts/random.json")
        self.assertEqual(scan_projects(self.root / "drafts").projects, ())

    def test_missing_and_empty_drafts_are_distinct(self):
        missing = scan_projects(self.root / "missing")
        self.assertFalse(missing.projects)
        self.assertEqual(len(missing.warnings), 1)
        self.root.joinpath("empty").mkdir()
        self.assertEqual(scan_projects(self.root / "empty").warnings, ())

    def test_unreadable_drafts_are_reported(self):
        with patch.object(Path, "iterdir", side_effect=PermissionError("access denied")):
            result = scan_projects(self.root)
        self.assertIn("access denied", result.warnings[0])

    def test_scan_does_not_write_or_recurse_through_links(self):
        metadata = self.file("drafts/project/draft_meta_info.json", '{"draft_name":"Original"}')
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        try:
            (self.root / "drafts" / "linked").symlink_to(metadata.parent, target_is_directory=True)
        except OSError:
            pass  # Windows may require Developer Mode for symlinks.
        result = scan_projects(self.root / "drafts")
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(len(result.projects), 1)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
