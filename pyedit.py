#!/usr/bin/env python3
#
# A Python-focused text editor application built with the PyQt6 library.
# This version focuses on a minimal, clean, and functional core.
#
# Key Features:
# 1. Recent Files: A menu to quickly access recently opened files.
# 2. Font Size Controls: Actions to increase and decrease the editor's font size.
# 3. Theme Toggle: The ability to switch between a light and dark theme.
# 4. Session Persistence: The editor saves and restores open files, including
#    their unsaved status.
# 5. Duplicate Tab: A new menu item and shortcut to clone the current tab's content.
# 6. Tab Reordering: Users can now drag and drop tabs to rearrange them.
# 7. Go to Line: A menu item and dialog for quick navigation.
# 8. Keyboard Shortcuts: Standard shortcuts for New, Open, Save, and Run.
# 9. Integrated Debugger: A menu item to run the script with a command-line debugger (`pdb`).
# 10. Stop Script: A menu item to terminate a running script.
# 11. Find/Replace: Advanced dialog for searching and replacing text.
# 12. Polished UI: Dynamic tab titles, improved syntax highlighting, and a dynamic status bar.
# 13. Line Numbers: A new feature to display line numbers next to the text area.
# 14. Close All Tabs: A new action to close all open tabs.
# 15. Interactive Console: A dedicated, interactive panel for running scripts and
#     interacting with the debugger.
# 16. Enhanced Status Bar: Displays cursor line/column, file type, and modification status.
#
from __future__ import annotations # This must be the very first import

import sys
import os
import json
import subprocess
from typing import Optional, List, Dict, Any


# Import necessary modules from PyQt6 for UI components and functionality.
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QTabWidget, QStatusBar, QMenuBar, QMenu,
    QFileDialog, QMessageBox, QInputDialog, QLineEdit,
    QPlainTextEdit, QDialog, QLabel, QDialogButtonBox,
    QCheckBox, QHBoxLayout, QTextEdit, QFrame
)
from PyQt6.QtGui import (
    QAction, QKeySequence, QFont, QTextCursor, QSyntaxHighlighter, QTextCharFormat, QColor,
    QTextDocument, QPainter
)
from PyQt6.QtCore import (
    QSettings, QSize, Qt, QProcess, QObject, pyqtSignal, QFileInfo, QByteArray, QRect
)


# =========================================================================
# Custom Widgets and Dialogs
# =========================================================================

class LineNumberArea(QWidget):
    """
    A custom widget to display line numbers for a QPlainTextEdit.
    The logic has been improved to ensure perfect alignment.
    """
    def __init__(self, editor: QPlainTextEdit):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        """Determines the widget's preferred size."""
        return QSize(self.editor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        """Paints the line numbers in the widget."""
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor("#2d2d30"))

        block = self.editor.firstVisibleBlock()
        block_number = block.blockNumber()
        
        # This is the key change: use a robust method to get the block's position
        top = int(self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top())
        bottom = top + int(self.editor.blockBoundingRect(block).height())
        
        # A simple check for the first line being outside the viewport
        offset = self.editor.contentOffset().y()
        if block.isVisible():
            # Adjust the top position to account for the first line being partially visible.
            top = int(self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top())

        # Iterate over all visible blocks
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible():
                number = str(block_number + 1)
                painter.setPen(QColor("#808080"))
                painter.drawText(0, top, self.width(), self.editor.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, number)
            
            block = block.next()
            top = top + int(self.editor.blockBoundingRect(block).height())
            block_number += 1


class PyEdit(QPlainTextEdit):
    """
    A custom QPlainTextEdit widget that manages its own file path and a syntax highlighter.
    The redundant 'is_dirty' attribute has been removed.
    """
    # Signal to notify the controller that the document's modification state has changed
    modification_state_changed = pyqtSignal(bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        
        # Dynamically calculate tab stop distance based on font size.
        # This fixes the hardcoded tab stop issue.
        tab_width_space = self.fontMetrics().horizontalAdvance(' ') * 4
        self.setTabStopDistance(tab_width_space)
        
        # Connect the document's modification state to our custom signal
        self.document().modificationChanged.connect(self.modification_state_changed)
        
        self.file_path: Optional[str] = None
        
        # **FIX:** Ensure the highlighter is a class attribute so it's not garbage collected.
        self.highlighter = PythonHighlighter(self.document())

        # Line number area setup
        self.lineNumberArea = LineNumberArea(self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        
        self.updateLineNumberAreaWidth(0)

        # Highlight current line
        self.highlight_format = QTextCharFormat()
        self.highlight_format.setBackground(QColor("#404040"))
        self.current_highlighting = False

    def resizeEvent(self, event):
        """Overrides the resize event to correctly position the line number area."""
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    def lineNumberAreaWidth(self) -> int:
        """Calculates the required width for the line number area."""
        digits = 1
        max_val = max(1, self.blockCount())
        while max_val >= 10:
            max_val /= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def updateLineNumberAreaWidth(self, newBlockCount: int):
        """Updates the line number area's width based on the number of lines."""
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        """Handles the scrolling and updates the line number area."""
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())
        
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def highlightCurrentLine(self):
        """Highlights the line where the cursor is located."""
        if not self.isReadOnly():
            selection = []
            cursor = self.textCursor()
            # Only highlight if there is no selection
            if not cursor.hasSelection():
                line_selection = QTextEdit.ExtraSelection()
                line_selection.format = self.highlight_format
                line_selection.cursor = cursor
                line_selection.cursor.clearSelection()
                selection.append(line_selection)
            self.setExtraSelections(selection)


class InteractiveConsole(QPlainTextEdit):
    """
    A custom QPlainTextEdit that acts as an interactive console.
    It captures user input and sends it to the controller.
    """
    command_entered = pyqtSignal(str)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setReadOnly(True)
        self.prompt = ">>> "
        self.setPrompt(self.prompt)
        
        self.history = []
        self.history_index = -1

    def setPrompt(self, new_prompt: str):
        self.prompt = new_prompt
        self.current_line_start_pos = self.textCursor().position() + len(self.prompt)
        self.appendPlainText(self.prompt)
        # FIX: Changed `QTextCursor.End` to `QTextCursor.MoveOperation.End`
        self.moveCursor(QTextCursor.MoveOperation.End)

    def keyPressEvent(self, event):
        """Captures user input and handles special keys."""
        cursor = self.textCursor()
        
        # Restrict cursor movement to the current input line
        if cursor.position() < self.current_line_start_pos:
            # FIX: Changed `QTextCursor.End` to `QTextCursor.MoveOperation.End`
            cursor.setPosition(self.document().characterCount() - 1)
            self.setTextCursor(cursor)

        if event.key() in [Qt.Key.Key_Up, Qt.Key.Key_Down]:
            self._handle_history_navigation(event)
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self._handle_command_entry()
        else:
            super().keyPressEvent(event)
            
    def _handle_history_navigation(self, event):
        """Navigates through command history."""
        if not self.history:
            return

        if event.key() == Qt.Key.Key_Up:
            if self.history_index < len(self.history) - 1:
                self.history_index += 1
        elif event.key() == Qt.Key.Key_Down:
            if self.history_index > 0:
                self.history_index -= 1
            else:
                self.history_index = -1 # Clear the line if at the beginning of history

        # Erase current input and replace with history command
        self.textCursor().beginEditBlock()
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(self.prompt)
        
        if self.history_index != -1:
            self.insertPlainText(self.history[self.history_index])

        self.textCursor().endEditBlock()
        
    def _handle_command_entry(self):
        """Processes the command entered by the user."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
        
        # Get the command, trim the prompt, and remove leading/trailing whitespace
        command = cursor.selectedText().strip()[len(self.prompt):].strip()
        
        # Add the command to history if it's not empty
        if command:
            if not self.history or self.history[0] != command:
                self.history.insert(0, command)
        
        # Reset history index
        self.history_index = -1
        
        # Append a newline and emit the signal
        self.appendPlainText("\n")
        self.command_entered.emit(command)
        self.setPrompt(self.prompt)

    def appendPlainText(self, text: str):
        """Adds text to the console without a prompt."""
        cursor = self.textCursor()
        # FIX: Changed `QTextCursor.End` to `QTextCursor.MoveOperation.End`
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

class FindReplaceDialog(QDialog):
    """
    A Find and Replace dialog with robust options.
    This class now provides a clean interface for the controller to use.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Find and Replace")
        self.setMinimumSize(QSize(350, 200))

        self.layout = QVBoxLayout(self)

        # Find input
        find_layout = QHBoxLayout()
        find_layout.addWidget(QLabel("Find:"))
        self.find_input = QLineEdit()
        find_layout.addWidget(self.find_input)
        self.layout.addLayout(find_layout)

        # Replace input
        replace_layout = QHBoxLayout()
        replace_layout.addWidget(QLabel("Replace with:"))
        self.replace_input = QLineEdit()
        replace_layout.addWidget(self.replace_input)
        self.layout.addLayout(replace_layout)

        # Options checkboxes
        options_layout = QHBoxLayout()
        self.case_sensitive_checkbox = QCheckBox("Case sensitive")
        self.whole_word_checkbox = QCheckBox("Whole word")
        options_layout.addWidget(self.case_sensitive_checkbox)
        options_layout.addWidget(self.whole_word_checkbox)
        self.layout.addLayout(options_layout)

        # Button box for actions
        button_box = QDialogButtonBox()
        self.find_next_button = button_box.addButton("Find Next", QDialogButtonBox.ButtonRole.ActionRole)
        self.replace_button = button_box.addButton("Replace", QDialogButtonBox.ButtonRole.ActionRole)
        self.replace_all_button = button_box.addButton("Replace All", QDialogButtonBox.ButtonRole.ActionRole)
        self.cancel_button = button_box.addButton(QDialogButtonBox.StandardButton.Cancel)

        self.layout.addWidget(button_box)

        # Connect button signals
        self.find_next_button.clicked.connect(lambda: self.accept_role("find"))
        self.replace_button.clicked.connect(lambda: self.accept_role("replace"))
        self.replace_all_button.clicked.connect(lambda: self.accept_role("replace_all"))
        self.cancel_button.clicked.connect(self.reject)

        self.current_action: Optional[str] = None

    def accept_role(self, action_name: str):
        """Sets the current action and accepts the dialog."""
        self.current_action = action_name
        self.accept()
        
    def get_search_params(self) -> Dict[str, Any]:
        """Returns the search and replace strings and options."""
        return {
            "find_text": self.find_input.text(),
            "replace_text": self.replace_input.text(),
            "case_sensitive": self.case_sensitive_checkbox.isChecked(),
            "whole_word": self.whole_word_checkbox.isChecked(),
            "action": self.current_action
        }


class PythonHighlighter(QSyntaxHighlighter):
    """
    A more comprehensive syntax highlighter for Python code.
    Includes highlighting for keywords, built-ins, strings, comments, numbers,
    classes, methods, and self.
    """
    def __init__(self, parent: QTextDocument):
        super().__init__(parent)

        self.highlighting_rules = []
        
        # Define formats
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569cd6"))
        
        function_format = QTextCharFormat()
        function_format.setForeground(QColor("#ffc66d"))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#6a9955"))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#757575"))

        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#b5cea8"))

        class_format = QTextCharFormat()
        class_format.setForeground(QColor("#4ec9b0"))

        method_format = QTextCharFormat()
        method_format.setForeground(QColor("#dcdcaa"))
        
        self_format = QTextCharFormat()
        self_format.setForeground(QColor("#569cd6"))
        self_format.setFontItalic(True)

        # Highlighting rules
        keywords = ["and", "as", "assert", "async", "await", "break", "class", "continue",
                    "def", "del", "elif", "else", "except", "False", "finally", "for",
                    "from", "global", "if", "import", "in", "is", "lambda", "None",
                    "nonlocal", "not", "or", "pass", "raise", "return", "True",
                    "try", "while", "with", "yield"]
        for word in keywords:
            self.highlighting_rules.append((r'\b' + word + r'\b', keyword_format))

        functions = ["abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes", "callable",
                     "chr", "classmethod", "compile", "complex", "delattr", "dict", "dir", "divmod",
                     "enumerate", "eval", "exec", "filter", "float", "format", "frozenset", "getattr",
                     "globals", "hasattr", "hash", "help", "hex", "id", "input", "int", "isinstance",
                     "issubclass", "iter", "len", "list", "locals", "map", "max", "memoryview",
                     "min", "next", "object", "oct", "open", "ord", "pow", "print", "property",
                     "range", "repr", "reversed", "round", "set", "setattr", "slice", "sorted",
                     "staticmethod", "str", "sum", "super", "tuple", "type", "vars", "zip"]
        for word in functions:
            self.highlighting_rules.append((r'\b' + word + r'\b', function_format))

        self.highlighting_rules.append((r'".*?"', string_format))
        self.highlighting_rules.append((r"'.*?'", string_format))
        self.highlighting_rules.append((r'#.*', comment_format))
        self.highlighting_rules.append((r'\b[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\b', number_format))
        self.highlighting_rules.append((r'\bclass\s+([A-Za-z0-9_]+)\b', class_format))
        self.highlighting_rules.append((r'\bdef\s+([A-Za-z0-9_]+)\b', method_format))
        self.highlighting_rules.append((r'\bself\b', self_format))

    def highlightBlock(self, text: str):
        """Applies highlighting rules to the given text block."""
        import re
        for pattern, format in self.highlighting_rules:
            for match in re.finditer(pattern, text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, format)


# =========================================================================
# Refactored Classes for Modularity and Decoupling
# =========================================================================

class SettingsManager(QObject):
    """
    Handles the loading and saving of application settings.
    Uses QSettings for platform-independent persistence.
    """
    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self.settings = QSettings("PyEdit", "PythonFocusedEditor")

    def load_settings(self) -> Dict[str, Any]:
        """Loads settings from disk and returns them as a dictionary."""
        settings_data = {
            "font_size": int(self.settings.value("font_size", 12)),
            "recent_files": self._load_json_list("recent_files"),
            "dark_mode": self.settings.value("dark_mode", False, type=bool),
            "tabs": self._load_json_list("tabs")
        }
        return settings_data

    def save_settings(self, font_size: int, recent_files: list, dark_mode: bool, tabs: list):
        """Saves settings to disk."""
        self.settings.setValue("font_size", font_size)
        self.settings.setValue("recent_files", json.dumps(recent_files))
        self.settings.setValue("dark_mode", dark_mode)
        self.settings.setValue("tabs", json.dumps(tabs))
        self.settings.sync()

    def _load_json_list(self, key: str) -> List[Any]:
        """Helper to load and parse a JSON-encoded list from QSettings."""
        data = self.settings.value(key, b"[]")
        if isinstance(data, QByteArray):
            try:
                return json.loads(bytes(data).decode())
            except json.JSONDecodeError:
                return []
        return []


class FileManager(QObject):
    """
    Manages file-related operations (open, save, new).
    Uses signals to notify other components of file changes.
    """
    # Signals for communicating with the controller/UI
    file_opened_signal = pyqtSignal(str, str, str)  # filePath, content, title
    file_saved_signal = pyqtSignal(str)              # filePath
    file_saved_as_signal = pyqtSignal(str, str)      # filePath, title
    status_message_signal = pyqtSignal(str)

    def __init__(self, parent: QObject = None):
        super().__init__(parent)

    def open_file(self, file_path: Optional[str] = None):
        """Opens a file and emits a signal with its content."""
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                None, "Open File", "", "All Files (*);;Python Files (*.py)")
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                    title = os.path.basename(file_path)
                    self.file_opened_signal.emit(file_path, content, title)
                    self.status_message_signal.emit(f"Opened: {file_path}")
            except Exception as e:
                QMessageBox.critical(None, "Error", f"Could not open file: {e}")

    def save_file(self, editor: PyEdit) -> bool:
        """Saves content to an existing file path and returns True on success."""
        if not editor.file_path:
            return self.save_file_as(editor)
        
        try:
            with open(editor.file_path, 'w') as f:
                f.write(editor.toPlainText())
            editor.document().setModified(False)
            self.file_saved_signal.emit(editor.file_path)
            self.status_message_signal.emit(f"Saved: {editor.file_path}")
            return True
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Could not save file: {e}")
            return False

    def save_file_as(self, editor: PyEdit) -> bool:
        """Prompts for a new file path and saves the content, returning True on success."""
        file_path, _ = QFileDialog.getSaveFileName(
            None, "Save File As", "", "All Files (*);;Python Files (*.py)")
        
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    f.write(editor.toPlainText())
                editor.document().setModified(False)
                title = os.path.basename(file_path)
                self.file_saved_as_signal.emit(file_path, title)
                self.status_message_signal.emit(f"Saved: {file_path}")
                return True
            except Exception as e:
                QMessageBox.critical(None, "Error", f"Could not save file: {e}")
                return False
        return False


class ScriptRunner(QObject):
    """
    Handles running and stopping external processes (e.g., Python scripts).
    Uses QProcess to manage the script's lifecycle.
    """
    # Signals for communicating with the controller/UI
    output_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int)

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.finished.connect(self.finished_signal.emit)

    def _read_stdout(self):
        """Reads standard output and emits a signal."""
        data = self.process.readAllStandardOutput().data().decode()
        self.output_signal.emit(data)

    def _read_stderr(self):
        """Reads standard error and emits a signal."""
        data = self.process.readAllStandardError().data().decode()
        self.error_signal.emit(data)

    def write_to_stdin(self, command: str):
        """Writes a command to the process's standard input."""
        if self.process.state() == QProcess.ProcessState.Running:
            self.process.write(f"{command}\n".encode())

    def run_script(self, file_path: str, args: List[str] = None, debugger: bool = False):
        """Runs a Python script with optional debugger and command-line arguments."""
        if not QFileInfo(file_path).exists():
            self.error_signal.emit(f"Error: File not found at '{file_path}'")
            return

        command = [sys.executable]
        if debugger:
            command.extend(["-m", "pdb"])
        command.append(file_path)
        if args:
            command.extend(args)
        
        self.output_signal.emit(f"\n[Running script: {' '.join(command)}]\n")
        self.process.start(command[0], command[1:])
        
    def stop_script(self):
        """Terminates the running process."""
        if self.process.state() == QProcess.ProcessState.Running:
            self.process.kill()
            self.output_signal.emit("\n[Script terminated]\n")


# =========================================================================
# Main UI and Controller
# =========================================================================

class PythonFocusedEditorUI(QMainWindow):
    """
    Defines the main window UI components.
    This class is now solely responsible for building and managing the UI.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setWindowTitle("Python Focused Editor")
        self.resize(800, 600)
        self.setMinimumSize(QSize(400, 300))
        
        self._create_widgets()
        self._create_menu_bar()
        self._create_status_bar()

    def _create_widgets(self):
        """Creates the main widgets for the application."""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        
        # New frame for the console
        self.console_frame = QFrame()
        self.console_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.console_frame_layout = QVBoxLayout(self.console_frame)
        self.console_frame_layout.setContentsMargins(0, 0, 0, 0)
        
        self.console = InteractiveConsole()
        self.console.setMaximumHeight(150)
        self.console.setStyleSheet("background-color: #212121; color: #ffffff;")
        
        self.console_frame_layout.addWidget(self.console)
        
        self.main_layout.addWidget(self.tabs)
        self.main_layout.addWidget(self.console_frame)
        
        # Initially hide the console frame
        self.console_frame.setVisible(False)

    def _create_menu_bar(self):
        """Creates the application's menu bar and its actions."""
        menu_bar = self.menuBar()

        # File menu actions
        self.new_action = QAction("&New", self)
        self.new_action.setShortcut("Ctrl+N")
        self.open_action = QAction("&Open...", self)
        self.open_action.setShortcut("Ctrl+O")
        self.save_action = QAction("&Save", self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_as_action = QAction("Save &As...", self)
        self.save_as_action.setShortcut("Ctrl+Shift+S")
        self.close_all_action = QAction("Close All", self)
        self.close_all_action.setShortcut(QKeySequence("Ctrl+Shift+W"))
        self.duplicate_tab_action = QAction("&Duplicate Tab", self)
        self.duplicate_tab_action.setShortcut("Ctrl+Shift+D")
        self.quit_action = QAction("&Quit", self)
        self.quit_action.setShortcut("Ctrl+Q")

        # Edit menu actions
        self.increase_font_action = QAction("Increase Font", self)
        self.increase_font_action.setShortcut("Ctrl++")
        self.decrease_font_action = QAction("Decrease Font", self)
        self.decrease_font_action.setShortcut("Ctrl+-")
        self.toggle_theme_action = QAction("Toggle Theme", self)
        self.toggle_theme_action.setShortcut("Ctrl+T")
        self.go_to_line_action = QAction("Go to Line...", self)
        self.go_to_line_action.setShortcut("Ctrl+G")
        self.find_replace_action = QAction("Find and Replace...", self)
        self.find_replace_action.setShortcut("Ctrl+F")

        # Run menu actions
        self.run_script_action = QAction("&Run Script", self)
        self.run_script_action.setShortcut(QKeySequence("Ctrl+R"))
        self.run_with_debugger_action = QAction("Run with &Debugger", self)
        self.run_with_debugger_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self.stop_script_action = QAction("&Stop Script", self)
        self.stop_script_action.setShortcut(QKeySequence("Ctrl+C"))
        self.stop_script_action.setEnabled(False) # initially disabled

        # Menus
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        self.recent_files_menu = QMenu("Recent Files", self)
        file_menu.addMenu(self.recent_files_menu)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.duplicate_tab_action)
        file_menu.addAction(self.close_all_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        edit_menu = menu_bar.addMenu("&Edit")
        edit_menu.addAction(self.increase_font_action)
        edit_menu.addAction(self.decrease_font_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.toggle_theme_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.go_to_line_action)
        edit_menu.addAction(self.find_replace_action)

        run_menu = menu_bar.addMenu("&Run")
        run_menu.addAction(self.run_script_action)
        run_menu.addAction(self.run_with_debugger_action)
        run_menu.addAction(self.stop_script_action)
        
    def _create_status_bar(self):
        """
        Creates the status bar and its permanent widgets.
        These widgets will display real-time information.
        """
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # Permanent widgets that stay on the right side of the status bar
        self.status_cursor_label = QLabel("Ln 1, Col 1")
        self.status_filetype_label = QLabel("Plain Text")
        
        self.statusBar.addPermanentWidget(self.status_cursor_label)
        self.statusBar.addPermanentWidget(self.status_filetype_label)

    def get_current_editor(self) -> Optional[PyEdit]:
        """Returns the current editor widget or None if no tab is open."""
        return self.tabs.currentWidget()

    def new_tab(self, title: str = "Untitled") -> PyEdit:
        """Adds a new tab to the QTabWidget."""
        editor = PyEdit()
        self.tabs.addTab(editor, title)
        self.tabs.setCurrentWidget(editor)
        return editor

    def close_tab_dialog(self) -> int:
        """Shows a message box to confirm closing a modified tab."""
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Unsaved Changes")
        box.setText("Do you want to save your changes?")
        box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        return box.exec()

    def update_tab_title(self, index: int, title: str):
        """Updates the title of a tab."""
        self.tabs.setTabText(index, title)

    def set_font_size(self, size: int):
        """Sets the font size for all PyEdit widgets."""
        font = QFont("Consolas")
        font.setPointSize(size)
        self.console.setFont(font)
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if isinstance(editor, PyEdit):
                editor.setFont(font)

    def update_recent_files_menu(self, recent_files: List[str]):
        """Populates the recent files menu."""
        self.recent_files_menu.clear()
        for file_path in recent_files:
            action = QAction(os.path.basename(file_path), self)
            action.triggered.connect(lambda checked, path=file_path: self._open_file_from_recent(path))
            self.recent_files_menu.addAction(action)

    def _open_file_from_recent(self, file_path: str):
        """
        A helper method for the recent files menu actions.
        This is a workaround to pass data with QAction.triggered signal.
        The actual logic is handled by the controller's file_manager.
        """
        self.file_manager_instance.open_file(file_path)

    def set_window_title(self, title: str):
        """Sets the main window title."""
        self.setWindowTitle(f"Python Focused Editor - {title}")
        
    def show_console(self):
        """Shows the console frame."""
        self.console_frame.setVisible(True)

    def hide_console(self):
        """Hides the console frame."""
        self.console_frame.setVisible(False)


class PythonFocusedEditorController(QObject):
    """
    Main controller class that orchestrates the application logic.
    It connects UI signals to back-end logic (file, process, settings managers).
    """
    def __init__(self, ui: PythonFocusedEditorUI):
        super().__init__()
        self.ui = ui
        self.font_size = 12
        self.recent_files: List[str] = []
        self.dark_mode = False
        self.untitled_counter = 1
        
        # New, refactored components
        self.settings_manager = SettingsManager()
        self.file_manager = FileManager()
        self.script_runner = ScriptRunner()
        
        # Pass the file manager instance to the UI for recent file actions
        self.ui.file_manager_instance = self.file_manager

        self._connect_signals()
        self._load_initial_settings()

    def _connect_signals(self):
        """Connects all UI actions and custom signals to their handlers."""
        # UI Action Signals to Controller Methods
        self.ui.tabs.tabCloseRequested.connect(self._handle_tab_close_request)
        self.ui.tabs.currentChanged.connect(self._handle_tab_changed)
        
        # Connect the console's command entered signal
        self.ui.console.command_entered.connect(self._send_command_to_process)

        # File Menu Actions
        self.ui.new_action.triggered.connect(self._handle_file_new)
        self.ui.open_action.triggered.connect(lambda: self.file_manager.open_file())
        self.ui.save_action.triggered.connect(self._handle_file_save)
        self.ui.save_as_action.triggered.connect(self._handle_file_save_as)
        self.ui.close_all_action.triggered.connect(self._handle_close_all_tabs)
        self.ui.duplicate_tab_action.triggered.connect(self._handle_duplicate_tab)
        self.ui.quit_action.triggered.connect(QApplication.instance().quit)

        # Edit Menu Actions
        self.ui.increase_font_action.triggered.connect(self._increase_font)
        self.ui.decrease_font_action.triggered.connect(self._decrease_font)
        self.ui.toggle_theme_action.triggered.connect(self._toggle_theme)
        self.ui.go_to_line_action.triggered.connect(self._handle_go_to_line)
        self.ui.find_replace_action.triggered.connect(self._handle_find_replace)

        # Run Menu Actions
        self.ui.run_script_action.triggered.connect(self._run_current_script)
        self.ui.run_with_debugger_action.triggered.connect(self._run_with_debugger)
        self.ui.stop_script_action.triggered.connect(self.script_runner.stop_script)

        # File Manager Signals to Controller Methods
        self.file_manager.file_opened_signal.connect(self._on_file_opened)
        self.file_manager.file_saved_signal.connect(self._on_file_saved)
        self.file_manager.file_saved_as_signal.connect(self._on_file_saved_as)
        self.file_manager.status_message_signal.connect(self.ui.statusBar.showMessage)

        # Script Runner Signals to Controller Methods
        self.script_runner.output_signal.connect(self.ui.console.appendPlainText)
        self.script_runner.error_signal.connect(self.ui.console.appendPlainText)
        self.script_runner.finished_signal.connect(self._on_script_finished)

    def _load_initial_settings(self):
        """Loads settings on startup and applies them to the UI."""
        settings_data = self.settings_manager.load_settings()
        self.font_size = settings_data["font_size"]
        self.recent_files = settings_data["recent_files"]
        self.dark_mode = settings_data["dark_mode"]

        self.ui.set_font_size(self.font_size)
        self.recent_files = [f for f in self.recent_files if QFileInfo(f).exists()]
        self.ui.update_recent_files_menu(self.recent_files)
        
        # Apply theme
        if self.dark_mode:
            self._apply_dark_theme()
        
        # Load saved tabs and handle non-existent files gracefully
        saved_tabs = settings_data["tabs"]
        if saved_tabs:
            # Clear the initial untitled tab if there are saved tabs
            if self.ui.tabs.count() > 0:
                self.ui.tabs.removeTab(0)
            for tab_data in saved_tabs:
                file_path = tab_data.get("path")
                content = tab_data.get("content", "")
                is_dirty = tab_data.get("is_dirty", False)

                editor = self.ui.new_tab("Untitled")
                editor.setPlainText(content)
                editor.document().setModified(is_dirty)

                if file_path and QFileInfo(file_path).exists():
                    editor.file_path = file_path
                    self.ui.update_tab_title(self.ui.tabs.count() - 1, os.path.basename(file_path))
                else:
                    editor.file_path = None
                    if file_path:
                        QMessageBox.warning(self.ui, "File Not Found", f"Could not open file: {file_path}. It may have been moved or deleted.")
                
                # Connect the modification signal for each editor
                editor.modification_state_changed.connect(
                    lambda: self._update_status_bar()
                )
                editor.cursorPositionChanged.connect(
                    lambda: self._update_status_bar()
                )

        if self.ui.tabs.count() == 0:
            self._handle_file_new()
            
        # Set initial window title and status bar message
        self._update_status_bar()

    def _update_status_bar(self):
        """
        Updates the status bar with current line, column, file type, and modification status.
        This method is now the central point for status bar updates.
        """
        editor = self.ui.get_current_editor()
        if not editor:
            self.ui.statusBar.showMessage("No file open")
            self.ui.status_cursor_label.setText("")
            self.ui.status_filetype_label.setText("")
            return

        # 1. Update line and column number
        cursor = editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.ui.status_cursor_label.setText(f"Ln {line}, Col {col}")

        # 2. Update file type and path
        file_path = editor.file_path
        if file_path:
            file_info = QFileInfo(file_path)
            file_extension = file_info.suffix().lower()
            if file_extension == 'py':
                self.ui.status_filetype_label.setText("Python")
            else:
                self.ui.status_filetype_label.setText(f".{file_extension}")
        else:
            self.ui.status_filetype_label.setText("Plain Text")

        # 3. Update modification status in the main message area
        status_message = ""
        if editor.document().isModified():
            status_message = "Unsaved changes"
            # We also update the tab title with an asterisk
            current_title = self.ui.tabs.tabText(self.ui.tabs.currentIndex())
            if not current_title.endswith('*'):
                self.ui.tabs.setTabText(self.ui.tabs.currentIndex(), current_title + '*')
        else:
            status_message = "Ready"
            # Remove the asterisk from the tab title
            current_title = self.ui.tabs.tabText(self.ui.tabs.currentIndex())
            if current_title.endswith('*'):
                self.ui.tabs.setTabText(self.ui.tabs.currentIndex(), current_title.removesuffix('*'))
            
        # Display the file path or "New file" as the main status message
        if file_path:
            self.ui.statusBar.showMessage(f"{file_path} - {status_message}")
        else:
            self.ui.statusBar.showMessage(f"New file - {status_message}")

    def _handle_tab_close_request(self, index: int):
        """Handles closing a tab with a save confirmation dialog."""
        editor = self.ui.tabs.widget(index)
        if editor and editor.document().isModified():
            choice = self.ui.close_tab_dialog()
            if choice == QMessageBox.StandardButton.Save:
                self._handle_file_save(editor)
            elif choice == QMessageBox.StandardButton.Discard:
                self.ui.tabs.removeTab(index)
            # If user selected Cancel, do nothing
        else:
            self.ui.tabs.removeTab(index)
        
        if self.ui.tabs.count() == 0:
            self._handle_file_new()
            
    def _handle_close_all_tabs(self):
        """
        Closes all open tabs, prompting to save any unsaved changes.
        This is a robust loop that handles tabs as they are closed.
        """
        while self.ui.tabs.count() > 0:
            editor = self.ui.tabs.widget(0)
            if editor.document().isModified():
                choice = self.ui.close_tab_dialog()
                if choice == QMessageBox.StandardButton.Save:
                    # Save the file. If save is canceled, break the loop.
                    if not self._handle_file_save(editor):
                        return
                elif choice == QMessageBox.StandardButton.Discard:
                    self.ui.tabs.removeTab(0)
                elif choice == QMessageBox.StandardButton.Cancel:
                    # User canceled, stop closing tabs
                    return
            else:
                self.ui.tabs.removeTab(0)
        
        # Ensure at least one tab is always open
        self._handle_file_new()

    def _handle_tab_changed(self, index: int):
        """Updates status bar and window title when the active tab changes."""
        self._update_status_bar()

    def _handle_file_new(self):
        """Creates a new, untitled tab with a unique name."""
        title = f"Untitled {self.untitled_counter}"
        self.untitled_counter += 1
        new_editor = self.ui.new_tab(title)
        
        # Connect the signals for the new editor to update the status bar
        new_editor.modification_state_changed.connect(self._update_status_bar)
        new_editor.cursorPositionChanged.connect(self._update_status_bar)
        
        self._update_status_bar()

    def _handle_file_save(self, editor: Optional[PyEdit] = None) -> bool:
        """Saves the current file or calls save_as if it's new, returns True on success."""
        editor = editor if editor else self.ui.get_current_editor()
        if editor:
            return self.file_manager.save_file(editor)
        return False

    def _handle_file_save_as(self):
        """Saves the current file to a new path."""
        editor = self.ui.get_current_editor()
        if editor:
            self.file_manager.save_file_as(editor)

    def _on_file_opened(self, file_path: str, content: str, title: str):
        """Slot for the file_opened_signal."""
        # Find if the file is already open
        for i in range(self.ui.tabs.count()):
            editor = self.ui.tabs.widget(i)
            if editor.file_path == file_path:
                self.ui.tabs.setCurrentIndex(i)
                self.ui.statusBar.showMessage(f"Switched to already open file: {file_path}")
                return
        
        # If not open, open a new tab
        editor = self.ui.new_tab(title)
        editor.setPlainText(content)
        editor.file_path = file_path
        editor.document().setModified(False)
        
        # Connect signals for this new editor
        editor.modification_state_changed.connect(self._update_status_bar)
        editor.cursorPositionChanged.connect(self._update_status_bar)

        self._add_to_recent_files(file_path)
        self._update_status_bar()

    def _on_file_saved(self, file_path: str):
        """Slot for the file_saved_signal."""
        self._update_status_bar()

    def _on_file_saved_as(self, file_path: str, title: str):
        """Slot for the file_saved_as_signal."""
        editor = self.ui.get_current_editor()
        if editor:
            editor.file_path = file_path
            self._add_to_recent_files(file_path)
            self._update_status_bar()
            
    def _add_to_recent_files(self, file_path: str):
        """Adds a file to the recent files list and updates the menu."""
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)
        self.recent_files.insert(0, file_path)
        self.recent_files = self.recent_files[:10]  # Keep list at max 10
        self.ui.update_recent_files_menu(self.recent_files)

    def _handle_duplicate_tab(self):
        """Duplicates the current tab's content into a new tab."""
        editor = self.ui.get_current_editor()
        if editor:
            new_editor = self.ui.new_tab(self.ui.tabs.tabText(self.ui.tabs.currentIndex()))
            new_editor.setPlainText(editor.toPlainText())
            new_editor.document().setModified(editor.document().isModified())
            new_editor.file_path = editor.file_path
            
            # Connect signals for the duplicated editor
            new_editor.modification_state_changed.connect(self._update_status_bar)
            new_editor.cursorPositionChanged.connect(self._update_status_bar)
            
    def _increase_font(self):
        """Increases the editor font size."""
        self.font_size += 1
        self.ui.set_font_size(self.font_size)

    def _decrease_font(self):
        """Decreases the editor font size."""
        if self.font_size > 1:
            self.font_size -= 1
            self.ui.set_font_size(self.font_size)

    def _toggle_theme(self):
        """Toggles between dark and light themes."""
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            self._apply_dark_theme()
        else:
            self.ui.setStyleSheet("") # Reset to default

    def _apply_dark_theme(self):
        """Applies a dark theme to the entire application."""
        self.ui.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #d4d4d4; }
            QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4; }
            QLineEdit { background-color: #252526; color: #d4d4d4; }
            QMenuBar { background-color: #252526; color: #d4d4d4; }
            QMenuBar::item:selected { background-color: #3f3f40; }
            QMenu { background-color: #252526; color: #d4d4d4; }
            QMenu::item:selected { background-color: #3f3f40; }
            QStatusBar { background-color: #007acc; color: #ffffff; }
        """)

    def _handle_go_to_line(self):
        """Prompts for a line number and moves the cursor."""
        editor = self.ui.get_current_editor()
        if not editor:
            return

        line_count = editor.document().blockCount()
        line_number, ok = QInputDialog.getInt(
            self.ui, "Go to Line", f"Enter line number (1-{line_count}):",
            min=1, max=line_count)

        if ok:
            cursor = QTextCursor(editor.document().findBlockByNumber(line_number - 1))
            editor.setTextCursor(cursor)
            # Update the status bar after moving the cursor
            self._update_status_bar()

    def _handle_find_replace(self):
        """
        Handles the Find and Replace dialog logic.
        This method is now more robust and handles all three actions:
        - "Find Next" searches for the next occurrence.
        - "Replace" replaces the current selection (if it matches) and finds the next.
        - "Replace All" replaces all occurrences in one pass.
        """
        editor = self.ui.get_current_editor()
        if not editor:
            QMessageBox.warning(self.ui, "Find/Replace", "No active editor to perform action on.")
            return

        dialog = FindReplaceDialog(self.ui)
        
        # Connect to the dialog's signals and show it
        if dialog.exec():
            params = dialog.get_search_params()
            find_text = params["find_text"]
            replace_text = params["replace_text"]
            action = params["action"]
            
            if not find_text:
                QMessageBox.warning(self.ui, "Find/Replace", "Please enter text to find.")
                return

            # Set up the search options based on checkboxes
            options = QTextDocument.FindFlag(0)
            if params["case_sensitive"]:
                options |= QTextDocument.FindFlag.FindCaseSensitively
            if params["whole_word"]:
                options |= QTextDocument.FindFlag.FindWholeWords
            
            cursor = editor.textCursor()

            if action == "find":
                # Find the next occurrence from the current cursor position
                if not editor.find(find_text, options):
                    # If not found, wrap around and start from the beginning
                    cursor.movePosition(QTextCursor.MoveOperation.Start)
                    editor.setTextCursor(cursor)
                    if not editor.find(find_text, options):
                        QMessageBox.information(self.ui, "Find Result", f"No occurrences of '{find_text}' found.")
            
            elif action == "replace":
                # Check if the current selection matches the find text
                if cursor.hasSelection() and cursor.selectedText() == find_text:
                    cursor.insertText(replace_text)
                    editor.setTextCursor(cursor) # This is important to update the cursor after insertion
                
                # Now find the next occurrence automatically
                if not editor.find(find_text, options):
                    QMessageBox.information(self.ui, "Replace Result", "No more occurrences found.")
                    
            elif action == "replace_all":
                # For "Replace All", it's more efficient to do a single text-based replacement.
                # First, ensure the cursor is at the beginning of the document
                cursor.movePosition(QTextCursor.MoveOperation.Start)
                editor.setTextCursor(cursor)

                content = editor.toPlainText()
                new_content = ""
                
                if not params["case_sensitive"]:
                    # Use a regex for case-insensitive and whole-word replacement
                    import re
                    flags = re.IGNORECASE if not params["case_sensitive"] else 0
                    if params["whole_word"]:
                        # This regex ensures we only match whole words
                        pattern = r'\b' + re.escape(find_text) + r'\b'
                        new_content = re.sub(pattern, replace_text, content, flags=flags)
                    else:
                        new_content = content.replace(find_text, replace_text)
                else:
                    new_content = content.replace(find_text, replace_text)
                        
                editor.setPlainText(new_content)
                QMessageBox.information(self.ui, "Replace All", f"All occurrences of '{find_text}' replaced.")

    def _send_command_to_process(self, command: str):
        """Sends a command to the process's standard input."""
        self.script_runner.write_to_stdin(command)
        
    def _run_current_script(self):
        """Runs the script in the current tab."""
        editor = self.ui.get_current_editor()
        if not editor or not editor.file_path or editor.document().isModified():
            QMessageBox.warning(self.ui, "Cannot Run Script", "Please save the file before running.")
            return

        self.ui.show_console()
        self.ui.console.setReadOnly(True)
        self.ui.console.clear()
        self.ui.stop_script_action.setEnabled(True)
        self.script_runner.run_script(editor.file_path)

    def _run_with_debugger(self):
        """Runs the script with the Python debugger."""
        editor = self.ui.get_current_editor()
        if not editor or not editor.file_path or editor.document().isModified():
            QMessageBox.warning(self.ui, "Cannot Run Script", "Please save the file before running.")
            return

        self.ui.show_console()
        self.ui.console.setReadOnly(False)
        self.ui.console.clear()
        self.ui.console.setPrompt("(pdb) ")
        self.ui.stop_script_action.setEnabled(True)
        self.script_runner.run_script(editor.file_path, debugger=True)

    def _on_script_finished(self, exit_code: int):
        """Slot for the finished_signal."""
        self.ui.stop_script_action.setEnabled(False)
        self.ui.console.setReadOnly(True)
        self.ui.console.appendPlainText(f"\n[Script finished with exit code {exit_code}]")

    def save_settings(self):
        """Saves current application settings and open tabs on exit."""
        saved_tabs = []
        for i in range(self.ui.tabs.count()):
            editor = self.ui.tabs.widget(i)
            # Use getattr for robustness
            file_path = getattr(editor, 'file_path', '')
            content = editor.toPlainText()
            is_dirty = editor.document().isModified()

            # Only save non-empty tabs or tabs with a file path.
            if file_path or content:
                file_data = {
                    "path": file_path,
                    "content": content,
                    "is_dirty": is_dirty
                }
                saved_tabs.append(file_data)
        
        valid_recent_files = [f for f in self.recent_files if QFileInfo(f).exists()]
        
        self.settings_manager.save_settings(
            self.font_size, valid_recent_files, self.dark_mode, saved_tabs
        )


# =========================================================================
# Main Entry Point
# =========================================================================

def main() -> None:
    """
    Main function to initialize and run the application.
    """
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("PythonFocusedEditor")
        app.setOrganizationName("PyEdit")
        
        ui = PythonFocusedEditorUI()
        controller = PythonFocusedEditorController(ui)
        
        app.aboutToQuit.connect(controller.save_settings)

        ui.show()
        sys.exit(app.exec())
    except Exception as e:
        QMessageBox.critical(None, "Application Error", f"An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()