import os
import sys

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

# Allow running from project root or gui/ directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cortex import AGENT, USER, ChatSession, stream_bot_reply

_AVATAR_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "avatar-assets", "rina")


class ReplyWorker(QThread):
    token_received = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, session, user_input):
        super().__init__()
        self.session = session
        self.user_input = user_input

    def run(self):
        try:
            for token in stream_bot_reply(self.session, self.user_input):
                self.token_received.emit(token)
        except Exception as e:
            self.error.emit(str(e))
        self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(AGENT)
        self.session = ChatSession()
        self.worker = None
        self._build_ui()
        self._load_history()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Top: avatar panel (left) + chat display (right)
        top = QHBoxLayout()
        top.setSpacing(8)

        self.avatar_label = QLabel()
        self.avatar_label.setFixedWidth(220)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
        self._set_avatar("default")
        top.addWidget(self.avatar_label)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        top.addWidget(self.chat_display, stretch=1)

        root.addLayout(top, stretch=1)

        # Bottom: input + send button
        bottom = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Say something...")
        self.input_field.returnPressed.connect(self._send)
        bottom.addWidget(self.input_field, stretch=1)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._send)
        bottom.addWidget(self.send_button)

        root.addLayout(bottom)
        self.resize(960, 640)

    def _set_avatar(self, state="default"):
        path = os.path.join(_AVATAR_DIR, f"{state}.png")
        if not os.path.exists(path):
            path = os.path.join(_AVATAR_DIR, "default.png")
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            pixmap = pixmap.scaledToWidth(
                self.avatar_label.width(),
                Qt.TransformationMode.SmoothTransformation,
            )
            self.avatar_label.setPixmap(pixmap)

    def _load_history(self):
        for role, text in self.session._turns:
            if role == "user":
                self._append_message(USER, text)
            else:
                self._append_message(AGENT, text)

    def _append_message(self, speaker, text):
        self.chat_display.append(f"<b>{speaker}:</b> {text}<br>")

    def _send(self):
        user_input = self.input_field.text().strip()
        if not user_input:
            return

        if user_input.lower() == "/reset":
            self.session.reset()
            self.chat_display.clear()
            self.input_field.clear()
            return

        self.input_field.clear()
        self._append_message(USER, user_input)

        # Insert the speaker label for the streaming reply
        self.chat_display.append(f"<b>{AGENT}:</b> ")
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)

        self._set_input_enabled(False)
        self.worker = ReplyWorker(self.session, user_input)
        self.worker.token_received.connect(self._on_token)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_token(self, token):
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(token)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()

    def _on_finished(self):
        self.chat_display.append("<br>")
        self._set_input_enabled(True)
        self.input_field.setFocus()

    def _on_error(self, msg):
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(f"<br><i>[Error: {msg}]</i>")
        self.chat_display.setTextCursor(cursor)
        self._set_input_enabled(True)

    def _set_input_enabled(self, enabled: bool):
        self.input_field.setEnabled(enabled)
        self.send_button.setEnabled(enabled)


def run():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
