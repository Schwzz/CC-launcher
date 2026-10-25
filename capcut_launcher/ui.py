"""The dashboard and its compact settings dialog. No CapCut files are changed."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel, QEasingCurve, QModelIndex, QObject, QPropertyAnimation,
    QRunnable, QSize, Qt, QThreadPool, QTimer, Signal, Slot,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QComboBox, QDialog, QFileDialog, QFrame,
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QListView, QMainWindow,
    QMessageBox, QPushButton, QStackedWidget, QStyle, QStyledItemDelegate,
    QVBoxLayout, QWidget,
)

from .actions import launch_capcut, open_drafts
from .discovery import (
    Project, ProjectScan, detect_drafts, detect_installation,
    is_capcut_executable, is_directory, scan_projects,
)
from .preferences import Preferences, load_preferences, preferences_path, save_preferences


PALETTES = {
    "dark": dict(bg="#191B1D", panel="#202325", card="#25292B", hover="#2C3133",
                 line="#353A3C", text="#F0F2F1", muted="#A8B1AD", field="#232729"),
    "light": dict(bg="#F5F6F4", panel="#EBEEEA", card="#FFFFFF", hover="#F0F4F0",
                  line="#D4DBD4", text="#202824", muted="#56635C", field="#FFFFFF"),
}


def accent_ink(accent: str) -> str:
    color = QColor(accent)
    channels = [color.redF(), color.greenF(), color.blueF()]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
    luminance = sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))
    return "#151B18" if luminance > .179 else "#FFFFFF"


def label(text: str, kind: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if kind:
        widget.setObjectName(kind)
    return widget


def button(text: str, kind: str = "", tooltip: str = "") -> QPushButton:
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setMinimumHeight(38)
    if kind:
        widget.setObjectName(kind)
    if tooltip:
        widget.setToolTip(tooltip)
    return widget


class ComboBox(QComboBox):
    """Keep the dropdown indicator visible in both custom color schemes."""

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Text), 1.5))
        x, y = self.width() - 14, self.height() // 2
        painter.drawLine(x - 3, y - 1, x, y + 2)
        painter.drawLine(x, y + 2, x + 3, y - 1)


class ProjectModel(QAbstractListModel):
    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.projects: list[Project] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.projects)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.projects):
            return None
        project = self.projects[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return project.name
        if role == Qt.ItemDataRole.UserRole:
            return project
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{project.name}\n{project.path}\nOpen projects inside CapCut."
        return None

    def replace(self, projects: list[Project]):
        self.beginResetModel()
        self.projects = projects
        self.endResetModel()


class ProjectDelegate(QStyledItemDelegate):
    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.colors = PALETTES["dark"]
        self.accent = "#B6E3CF"

    def sizeHint(self, option, index):
        return QSize(400, 94)

    def paint(self, painter: QPainter, option, index):
        project = index.data(Qt.ItemDataRole.UserRole)
        if project is None:
            return
        colors = self.colors
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(0, 4, -2, -4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors["hover"] if option.state & QStyle.StateFlag.State_MouseOver else colors["card"]))
        painter.drawRoundedRect(rect, 12, 12)
        tile = rect.adjusted(16, 15, 0, 0)
        tile.setSize(QSize(56, 56))
        tint = QColor(self.accent)
        tint.setAlpha(28)
        painter.setBrush(tint)
        painter.drawRoundedRect(tile, 10, 10)
        painter.setPen(QPen(QColor(self.accent), 1.8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(tile.adjusted(15, 16, -15, -16), 3, 3)
        painter.drawLine(tile.left() + 15, tile.top() + 24, tile.right() - 15, tile.top() + 24)
        painter.drawLine(tile.left() + 24, tile.top() + 16, tile.left() + 19, tile.top() + 24)
        painter.drawLine(tile.left() + 33, tile.top() + 16, tile.left() + 28, tile.top() + 24)
        text_rect = rect.adjusted(89, 17, -24, -16)
        name_font = QFont(option.font)
        name_font.setPointSize(11)
        name_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(name_font)
        painter.setPen(QColor(colors["text"]))
        metrics = painter.fontMetrics()
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         metrics.elidedText(project.name, Qt.TextElideMode.ElideRight, text_rect.width()))
        painter.setFont(option.font)
        painter.setPen(QColor(colors["muted"]))
        try:
            date = datetime.fromtimestamp(project.modified).strftime("%b %d, %Y  ·  %H:%M")
        except (ValueError, OverflowError, OSError):
            date = "Date unavailable"
        painter.drawText(text_rect.adjusted(0, 29, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         f"Modified {date}")
        painter.restore()


class ScanSignals(QObject):
    finished = Signal(int, object)


class ScanTask(QRunnable):
    def __init__(self, generation: int, path: Path):
        super().__init__()
        self.generation, self.path = generation, path
        self.signals = ScanSignals()

    def run(self):
        result = scan_projects(self.path)
        self.signals.finished.emit(self.generation, result)


class SettingsDialog(QDialog):
    def __init__(self, prefs: Preferences, parent: QWidget):
        super().__init__(parent)
        self.setWindowTitle("Launcher settings")
        self.setMinimumWidth(480)
        self.setMaximumWidth(600)
        self.accent = prefs.accent
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(12)
        outer.addWidget(label("Make it yours", "sectionTitle"))
        outer.addWidget(label("Appearance", "eyebrow"))
        row = QHBoxLayout()
        self.theme = ComboBox()
        self.theme.addItems(["Dark", "Light"])
        self.theme.setCurrentIndex(0 if prefs.theme == "dark" else 1)
        self.theme.setAccessibleName("Color theme")
        row.addWidget(self.theme, 1)
        self.accent_button = button("Accent color")
        self.accent_button.clicked.connect(self.choose_accent)
        row.addWidget(self.accent_button, 1)
        outer.addLayout(row)
        self.update_accent()
        outer.addSpacing(8)
        outer.addWidget(label("Locations", "eyebrow"))
        outer.addWidget(label("Leave blank to use automatic detection.", "muted"))
        outer.addWidget(label("CapCut executable"))
        self.executable = QLineEdit(prefs.executable)
        self.executable.setPlaceholderText("Automatic · CapCut.exe")
        self.executable.setAccessibleName("CapCut executable override")
        self.add_path_row(outer, self.executable, self.browse_executable)
        outer.addWidget(label("Drafts directory"))
        self.drafts = QLineEdit(prefs.drafts)
        self.drafts.setPlaceholderText("Automatic · com.lveditor.draft")
        self.drafts.setAccessibleName("Drafts directory override")
        self.add_path_row(outer, self.drafts, self.browse_drafts)
        outer.addWidget(label("Choose the folder containing your individual project folders. "
                              "The launcher only reads their metadata.", "muted", True))
        self.error = label("", "error", True)
        self.error.hide()
        outer.addWidget(self.error)
        outer.addSpacing(8)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        save = button("Save preferences", "primary")
        save.setDefault(True)
        save.clicked.connect(self.validate)
        actions.addWidget(save)
        outer.addLayout(actions)

    def add_path_row(self, layout, field, callback):
        row = QHBoxLayout()
        row.addWidget(field, 1)
        browse = button("Browse…")
        browse.clicked.connect(callback)
        row.addWidget(browse)
        layout.addLayout(row)

    def update_accent(self):
        self.accent_button.setStyleSheet(
            f"background: {self.accent}; color: {accent_ink(self.accent)}; border: none;")
        self.accent_button.setToolTip(self.accent)

    def choose_accent(self):
        color = QColorDialog.getColor(QColor(self.accent), self, "Accent color")
        if color.isValid():
            self.accent = color.name()
            self.update_accent()

    def browse_executable(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select CapCut.exe", self.executable.text(), "CapCut (CapCut.exe)")
        if path:
            self.executable.setText(path)

    def browse_drafts(self):
        path = QFileDialog.getExistingDirectory(self, "Select drafts directory", self.drafts.text())
        if path:
            self.drafts.setText(path)

    def values(self) -> Preferences:
        return Preferences(self.theme.currentText().lower(), self.accent,
                           self.executable.text().strip(), self.drafts.text().strip())

    def validate(self):
        prefs = self.values()
        try:
            if prefs.executable and not is_capcut_executable(Path(prefs.executable)):
                raise ValueError("Choose an existing file named CapCut.exe, or clear the executable override.")
            if prefs.drafts and not is_directory(Path(prefs.drafts)):
                raise ValueError("Choose an existing drafts directory, or clear the drafts override.")
        except (OSError, ValueError) as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, config_path: Path | None = None):
        super().__init__()
        self.config_path = config_path if config_path is not None else preferences_path()
        self.prefs, preference_error = load_preferences(self.config_path)
        self.projects: tuple[Project, ...] = ()
        self.executable: Path | None = None
        self.drafts_directory: Path | None = None
        self.generation = 0
        self.scanning = False
        self.setWindowTitle("CC Launcher")
        self.resize(1040, 720)
        self.setMinimumSize(800, 580)
        self.build_ui()
        self.apply_appearance()
        self.refresh()
        if preference_error:
            QTimer.singleShot(0, lambda: self.show_error("Preferences", preference_error))

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 30, 22, 24)
        side.setSpacing(10)
        logo = label("cc /", "logo")
        side.addWidget(logo)
        side.addWidget(label("LAUNCHER", "eyebrow"))
        side.addSpacing(35)
        side.addWidget(label("  Projects", "navigation"))
        side.addStretch()
        side.addWidget(label("A little less noise.\nA little more creating.", "muted", True))
        side.addSpacing(16)
        settings = button("Settings", tooltip="Appearance and folder locations")
        settings.clicked.connect(self.open_settings)
        side.addWidget(settings)
        side.addWidget(label("Independent · v0.1", "muted"))
        layout.addWidget(sidebar)

        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(34, 30, 34, 22)
        main.setSpacing(16)
        header = QHBoxLayout()
        header.addWidget(label("YOUR WORKSPACE", "eyebrow"))
        header.addStretch()
        self.install_status = label("", "status")
        header.addWidget(self.install_status)
        main.addLayout(header)
        title = QVBoxLayout()
        title.setSpacing(7)
        title.addWidget(label("Room to create.", "title"))
        title.addWidget(label("Your CapCut projects, without the distractions.", "muted"))
        main.addLayout(title)
        actions = QHBoxLayout()
        self.launch_button = button("Launch CapCut", "primary", "Start CapCut normally; no project is passed to it")
        self.launch_button.clicked.connect(self.launch)
        actions.addWidget(self.launch_button)
        self.folder_button = button("Open drafts folder")
        self.folder_button.clicked.connect(self.open_folder)
        actions.addWidget(self.folder_button)
        actions.addStretch()
        main.addLayout(actions)
        self.notice = label("", "notice", True)
        main.addWidget(self.notice)
        heading = QHBoxLayout()
        heading.addWidget(label("Projects", "sectionTitle"))
        self.count_label = label("0", "muted")
        heading.addWidget(self.count_label)
        heading.addStretch()
        self.refresh_button = button("Refresh", tooltip="Recheck installation and read the project list")
        self.refresh_button.clicked.connect(self.refresh)
        heading.addWidget(self.refresh_button)
        main.addLayout(heading)
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search projects…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search projects")
        self.search.textChanged.connect(self.filter_projects)
        tools.addWidget(self.search, 1)
        self.sort = ComboBox()
        self.sort.addItems(["Recently modified", "Oldest first", "Name A–Z"])
        self.sort.setAccessibleName("Sort projects")
        self.sort.currentIndexChanged.connect(self.filter_projects)
        tools.addWidget(self.sort)
        main.addLayout(tools)
        self.stack = QStackedWidget()
        self.list_view = QListView()
        self.list_view.setAccessibleName("Local CapCut projects, read only")
        self.list_view.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.list_view.setMouseTracking(True)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.model = ProjectModel(self)
        self.delegate = ProjectDelegate(self)
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(self.delegate)
        self.stack.addWidget(self.list_view)
        empty = QFrame()
        empty.setObjectName("empty")
        empty_layout = QVBoxLayout(empty)
        empty_layout.setContentsMargins(28, 24, 28, 24)
        empty_layout.addStretch()
        empty_layout.addWidget(label("[  /  ]", "emptyIcon"), alignment=Qt.AlignmentFlag.AlignHCenter)
        self.empty_title = label("No projects yet", "sectionTitle")
        empty_layout.addWidget(self.empty_title, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.empty_text = label("", "muted", True)
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_text)
        empty_layout.addStretch()
        self.stack.addWidget(empty)
        main.addWidget(self.stack, 1)
        self.scan_note = label("", "muted", True)
        self.scan_note.hide()
        main.addWidget(self.scan_note)
        main.addWidget(label("Read-only dashboard  ·  Open individual projects inside CapCut.", "muted", True))
        layout.addWidget(content, 1)
        # A single short reveal after loading; no persistent animation or polling.
        self.fade_effect = QGraphicsOpacityEffect(self.stack)
        self.fade_effect.setOpacity(1.0)
        self.stack.setGraphicsEffect(self.fade_effect)
        self.fade = QPropertyAnimation(self.fade_effect, b"opacity", self)
        self.fade.setDuration(180)
        self.fade.setStartValue(.55)
        self.fade.setEndValue(1.0)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    def apply_appearance(self):
        c = PALETTES[self.prefs.theme]
        accent = self.prefs.accent
        self.delegate.colors = c
        self.delegate.accent = accent
        self.setStyleSheet(f"""
            QWidget {{ color: {c['text']}; font-family: 'Segoe UI', 'Inter', 'DejaVu Sans'; font-size: 13px; }}
            QMainWindow, QDialog {{ background: {c['bg']}; }}
            QFrame#sidebar {{ background: {c['panel']}; border-right: 1px solid {c['line']}; }}
            QLabel {{ background: transparent; }}
            QLabel#muted {{ color: {c['muted']}; font-size: 12px; }}
            QLabel#eyebrow {{ color: {c['muted']}; font-size: 10px; font-weight: 600; letter-spacing: 2px; }}
            QLabel#title {{ font-size: 32px; font-weight: 600; letter-spacing: -1px; }}
            QLabel#sectionTitle {{ font-size: 19px; font-weight: 600; }}
            QLabel#logo {{ color: {accent}; font-size: 38px; font-weight: 700; letter-spacing: -3px; }}
            QLabel#emptyIcon {{ color: {accent}; font-size: 32px; padding: 8px; }}
            QLabel#navigation {{ background: {c['card']}; border-radius: 8px; padding: 12px 5px; font-weight: 600; }}
            QLabel#status {{ color: {c['muted']}; background: {c['panel']}; border-radius: 10px; padding: 6px 10px; font-size: 11px; }}
            QLabel#notice {{ color: {c['muted']}; background: {c['panel']}; border-radius: 8px; padding: 10px 12px; font-size: 12px; }}
            QLabel#error {{ color: {'#FFB4A9' if self.prefs.theme == 'dark' else '#9C3026'}; }}
            QPushButton {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 8px; padding: 0 15px; font-weight: 500; }}
            QPushButton:hover {{ background: {c['hover']}; border-color: {c['muted']}; }}
            QPushButton:pressed {{ background: {c['panel']}; }}
            QPushButton#primary {{ background: {accent}; color: {accent_ink(accent)}; border-color: {accent}; font-weight: 600; }}
            QPushButton#primary:hover {{ background: {QColor(accent).lighter(108).name()}; }}
            QPushButton:disabled, QPushButton#primary:disabled {{ background: {c['panel']}; color: {c['muted']}; border-color: {c['line']}; }}
            QPushButton:focus {{ border: 1px solid {accent}; }}
            QLineEdit, QComboBox {{ background: {c['field']}; border: 1px solid {c['line']}; border-radius: 8px; padding: 10px 12px; selection-background-color: {accent}; selection-color: {accent_ink(accent)}; }}
            QLineEdit:focus, QComboBox:focus {{ border-color: {accent}; }}
            QComboBox {{ padding-right: 24px; }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QComboBox::down-arrow {{ image: none; }}
            QComboBox QAbstractItemView {{ background: {c['card']}; color: {c['text']}; selection-background-color: {c['hover']}; border: 1px solid {c['line']}; }}
            QListView {{ background: transparent; border: none; outline: none; }}
            QFrame#empty {{ background: {c['panel']}; border: 1px dashed {c['line']}; border-radius: 12px; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
            QScrollBar::handle:vertical {{ background: {c['line']}; border-radius: 4px; min-height: 24px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['line']}; padding: 6px; }}
        """)
        self.list_view.viewport().update()

    def refresh(self):
        self.generation += 1
        windows = sys.platform == "win32"
        self.executable = Path(self.prefs.executable) if self.prefs.executable else (detect_installation(os.environ) if windows else None)
        self.drafts_directory = Path(self.prefs.drafts) if self.prefs.drafts else (detect_drafts(os.environ) if windows else None)
        installed = self.executable is not None and is_capcut_executable(self.executable)
        has_drafts = self.drafts_directory is not None and is_directory(self.drafts_directory)
        self.install_status.setText("CapCut found" if installed else "CapCut not found")
        self.install_status.setToolTip(str(self.executable) if installed else "Set the executable location in Settings.")
        self.launch_button.setEnabled(windows and installed)
        self.folder_button.setEnabled(windows and has_drafts)
        self.folder_button.setToolTip(str(self.drafts_directory) if windows and has_drafts else "Requires Windows and an existing drafts directory")
        self.launch_button.setToolTip("Start CapCut normally; no project is passed to it" if windows and installed else "Requires Windows and an existing CapCut.exe; check Settings")
        if not windows:
            message = "Windows is required to launch CapCut and open File Explorer. Local draft inspection is available via Settings."
        elif not installed:
            message = "CapCut wasn’t found. Choose CapCut.exe in Settings, or install CapCut separately."
        elif not has_drafts:
            message = "No drafts directory found. Create a project in CapCut, or choose your drafts location in Settings."
        else:
            message = ""
        self.notice.setText(message)
        self.notice.setVisible(bool(message))
        self.scan_note.hide()
        self.projects = ()
        self.scanning = bool(has_drafts)
        self.filter_projects()
        if has_drafts:
            self.refresh_button.setEnabled(False)
            self.refresh_button.setText("Reading…")
            task = ScanTask(self.generation, self.drafts_directory)
            task.signals.finished.connect(self.finish_scan)
            QThreadPool.globalInstance().start(task)
        else:
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("Refresh")

    @Slot(int, object)
    def finish_scan(self, generation: int, result: ProjectScan):
        if generation != self.generation:
            return
        self.scanning = False
        self.projects = result.projects
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("Refresh")
        if result.warnings:
            self.scan_note.setText(f"{len(result.warnings)} reading notice(s). Hover here for details.")
            self.scan_note.setToolTip("\n".join(result.warnings[:20]))
            self.scan_note.show()
        self.filter_projects()
        self.fade.stop()
        self.fade.start()

    def filter_projects(self):
        query = self.search.text().strip().casefold()
        projects = [p for p in self.projects if query in p.name.casefold()]
        order = self.sort.currentIndex()
        if order == 2:
            projects.sort(key=lambda p: (p.name.casefold(), str(p.path)))
        else:
            projects.sort(key=lambda p: (p.modified, p.name.casefold()), reverse=order == 0)
        self.model.replace(projects)
        count = len(self.projects)
        self.count_label.setText(f"{len(projects)} of {count}" if query else str(count))
        self.stack.setCurrentIndex(0 if projects else 1)
        if self.scanning:
            title, text = "Reading your projects…", "Just the details. Your drafts stay untouched."
        elif query and count:
            title, text = "No matching projects", "Try a different name or clear your search."
        elif self.drafts_directory is None or not is_directory(self.drafts_directory):
            title, text = "Find your workspace", "Choose your CapCut drafts directory in Settings to see your projects here."
        else:
            title, text = "No projects to show", "Create a project in CapCut, then refresh. Check Settings if your drafts live elsewhere."
        self.empty_title.setText(title)
        self.empty_text.setText(text)

    def open_settings(self):
        dialog = SettingsDialog(self.prefs, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        prefs = dialog.values()
        try:
            save_preferences(self.config_path, prefs)
        except OSError as exc:
            self.show_error("Could not save preferences", str(exc))
            return
        self.prefs = prefs
        self.apply_appearance()
        self.refresh()

    def show_error(self, title: str, message: str):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(message)
        box.exec()

    def launch(self):
        try:
            if self.executable is None:
                raise OSError("Choose CapCut.exe in Settings first.")
            launch_capcut(self.executable)
        except OSError as exc:
            self.show_error("Could not launch CapCut", str(exc))
            self.refresh()

    def open_folder(self):
        try:
            if self.drafts_directory is None:
                raise OSError("Choose your drafts directory in Settings first.")
            open_drafts(self.drafts_directory)
        except OSError as exc:
            self.show_error("Could not open drafts", str(exc))
            self.refresh()


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("CC Launcher")
    app.setOrganizationName("CC Launcher")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    return app.exec()
