import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from capcut_launcher.actions import launch_capcut, open_drafts


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="launcher test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_launch_uses_only_executable_no_project_or_shell_arguments(self):
        executable = self.root / "CapCut.exe"
        executable.touch()
        with patch("capcut_launcher.actions.sys.platform", "win32"), \
                patch("capcut_launcher.actions.subprocess.Popen") as popen:
            launch_capcut(executable)
        popen.assert_called_once_with([str(executable)], cwd=str(self.root))

    def test_relative_executable_resolves_before_changing_working_directory(self):
        executable = self.root / "CapCut.exe"
        executable.touch()
        relative = Path(os.path.relpath(executable))
        with patch("capcut_launcher.actions.sys.platform", "win32"), \
                patch("capcut_launcher.actions.subprocess.Popen") as popen:
            launch_capcut(relative)
        popen.assert_called_once_with([str(executable)], cwd=str(self.root))

    def test_missing_executable_is_not_launched(self):
        with patch("capcut_launcher.actions.sys.platform", "win32"), \
                patch("capcut_launcher.actions.subprocess.Popen") as popen:
            with self.assertRaises(OSError):
                launch_capcut(self.root / "CapCut.exe")
        popen.assert_not_called()

    def test_open_folder_uses_windows_shell_directory_action(self):
        with patch("capcut_launcher.actions.sys.platform", "win32"), \
                patch("capcut_launcher.actions.os.startfile", create=True) as startfile:
            open_drafts(self.root)
        startfile.assert_called_once_with(str(self.root))

    def test_missing_directory_is_not_opened(self):
        with patch("capcut_launcher.actions.sys.platform", "win32"), \
                patch("capcut_launcher.actions.os.startfile", create=True) as startfile:
            with self.assertRaises(OSError):
                open_drafts(self.root / "missing")
        startfile.assert_not_called()

    def test_non_windows_actions_explain_platform_requirement(self):
        with patch("capcut_launcher.actions.sys.platform", "linux"):
            for action, path in ((launch_capcut, self.root / "CapCut.exe"), (open_drafts, self.root)):
                with self.assertRaisesRegex(OSError, "requires Windows"):
                    action(path)
