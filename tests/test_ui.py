"""Headless Qt smoke tests; these do not establish real Windows integration."""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from capcut_launcher.preferences import Preferences, load_preferences, save_preferences
from capcut_launcher.ui import MainWindow, SettingsDialog


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "launcher" / "preferences.json"
        self.window = None

    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(5000)
        self.app.processEvents()
        if self.window:
            self.window.close()
            self.window.deleteLater()
            self.app.processEvents()
        self.temp.cleanup()

    def wait_for_scan(self):
        deadline = time.monotonic() + 5
        while self.window.scanning and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertFalse(self.window.scanning, "Background scan did not complete")
        self.app.processEvents()

    def make_projects(self):
        drafts = self.root / "drafts"
        for folder, name, timestamp in (("a", "Weekend edit", 1_700_000_000),
                                        ("b", "A winter film", 1_700_000_100)):
            project = drafts / folder
            project.mkdir(parents=True)
            (project / "draft_meta_info.json").write_text(json.dumps({
                "draft_name": name, "tm_draft_modified": timestamp}))
        save_preferences(self.config, Preferences(drafts=str(drafts)))

    def test_missing_installation_empty_state_and_platform_guards(self):
        with patch("capcut_launcher.ui.sys.platform", "linux"):
            self.window = MainWindow(self.config)
        self.window.show()
        self.app.processEvents()
        self.assertEqual(self.window.stack.currentIndex(), 1)
        self.assertEqual(self.window.empty_title.text(), "Find your workspace")
        self.assertFalse(self.window.launch_button.isEnabled())
        self.assertFalse(self.window.folder_button.isEnabled())
        self.assertFalse(self.config.exists())

    def test_scan_search_sort_and_render_both_themes(self):
        self.make_projects()
        self.window = MainWindow(self.config)
        self.window.show()
        self.wait_for_scan()
        self.assertEqual(self.window.model.rowCount(), 2)
        self.assertEqual(self.window.model.projects[0].name, "A winter film")
        self.window.sort.setCurrentIndex(1)
        self.assertEqual(self.window.model.projects[0].name, "Weekend edit")
        self.window.sort.setCurrentIndex(2)
        self.assertEqual(self.window.model.projects[0].name, "A winter film")
        QTest.keyClicks(self.window.search, "WEEKEND")
        self.assertEqual(self.window.model.rowCount(), 1)
        self.assertEqual(self.window.count_label.text(), "1 of 2")
        self.window.search.setText("no match")
        self.assertEqual(self.window.empty_title.text(), "No matching projects")
        self.window.search.clear()
        for theme in ("dark", "light"):
            self.window.prefs.theme = theme
            self.window.apply_appearance()
            self.app.processEvents()
            self.assertFalse(self.window.grab().isNull())

    def test_invalid_override_and_stale_scan_do_not_break_dashboard(self):
        save_preferences(self.config, Preferences(executable=str(self.root / "missing.exe"),
                                                drafts=str(self.root / "missing")))
        self.window = MainWindow(self.config)
        self.assertFalse(self.window.scanning)
        self.assertFalse(self.window.launch_button.isEnabled())
        from capcut_launcher.discovery import Project, ProjectScan
        stale = ProjectScan((Project("stale", self.root, 1_700_000_000),))
        self.window.finish_scan(self.window.generation - 1, stale)
        self.assertEqual(self.window.model.rowCount(), 0)

    def test_settings_validate_paths_and_persist_selected_appearance(self):
        self.window = MainWindow(self.config)
        dialog = SettingsDialog(self.window.prefs, self.window)
        dialog.executable.setText(str(self.root / "missing.exe"))
        dialog.validate()
        self.assertFalse(dialog.error.isHidden())
        self.assertEqual(dialog.result(), 0)
        dialog.executable.clear()
        dialog.drafts.setText(str(self.root / "missing"))
        dialog.validate()
        self.assertEqual(dialog.result(), 0)
        dialog.drafts.clear()
        dialog.theme.setCurrentIndex(1)
        dialog.accent = "#9381FF"
        dialog.validate()
        self.assertEqual(dialog.result(), 1)
        with patch("capcut_launcher.ui.SettingsDialog", return_value=dialog):
            with patch.object(dialog, "exec", return_value=1):
                self.window.open_settings()
        saved, error = load_preferences(self.config)
        self.assertIsNone(error)
        self.assertEqual(saved.theme, "light")
        self.assertEqual(saved.accent, "#9381FF")
        self.assertEqual(self.window.prefs, saved)
        dialog.deleteLater()
