import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capcut_launcher.preferences import Preferences, load_preferences, save_preferences


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "settings" / "preferences.json"

    def test_missing_preferences_use_defaults_without_writing(self):
        self.assertEqual(load_preferences(self.path), (Preferences(), None))
        self.assertFalse(self.path.parent.exists())

    def test_round_trip(self):
        prefs = Preferences("light", "#AABBCC", r"C:\Apps\CapCut.exe", r"D:\Video drafts")
        save_preferences(self.path, prefs)
        self.assertEqual(load_preferences(self.path), (prefs, None))
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_invalid_values_and_unknown_fields_are_ignored(self):
        self.path.parent.mkdir()
        self.path.write_text(json.dumps({"theme": "neon", "accent": "red; invalid css",
                                        "executable": 123, "drafts": "\x00", "extra": "ignored"}))
        self.assertEqual(load_preferences(self.path), (Preferences(), None))

    def test_corrupt_preferences_report_defaults(self):
        self.path.parent.mkdir()
        self.path.write_text("broken json")
        prefs, error = load_preferences(self.path)
        self.assertEqual(prefs, Preferences())
        self.assertIn("Could not load", error)

    def test_failed_save_preserves_previous_preferences(self):
        save_preferences(self.path, Preferences())
        before = self.path.read_bytes()
        with patch("capcut_launcher.preferences.os.replace", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                save_preferences(self.path, Preferences(theme="light"))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
