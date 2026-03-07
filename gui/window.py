import os
import sys
from datetime import datetime

from PyQt6.QtCore import Qt, QEvent, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

# Allow running from project root or gui/ directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cortex import AGENT, USER, CONTEXT_LENGTH, ChatSession, stream_bot_reply, detect_emotion

_AVATAR_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "avatar-assets", "rina",
)
# Emotion states derived from available avatar images (filename without extension)
_EMOTIONS = sorted(
    os.path.splitext(f)[0]
    for f in os.listdir(_AVATAR_DIR)
    if f.endswith(".png")
)

_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #070714;
    color: #c8d8ff;
    font-family: 'Segoe UI', 'Ubuntu', 'Helvetica Neue', sans-serif;
}

QTextEdit {
    background-color: #0e0e28;
    color: #c8d8ff;
    border: 1px solid #1a1a3e;
    border-radius: 4px;
    selection-background-color: #2d2d6e;
    selection-color: #ffffff;
}

QPushButton {
    background-color: #0e1a3a;
    color: #4dd9ff;
    border: 1px solid #2d4d7a;
    border-radius: 4px;
    padding: 6px 16px;
    min-width: 60px;
}
QPushButton:hover {
    background-color: #1a2a4a;
    border-color: #4dd9ff;
}
QPushButton:pressed {
    background-color: #0a1428;
}
QPushButton:disabled {
    color: #2d3d5a;
    border-color: #141e30;
}

QPushButton#resetBtn {
    color: #ff7eb3;
    border-color: #5a1a35;
}
QPushButton#resetBtn:hover {
    background-color: #2a0e1e;
    border-color: #ff7eb3;
}
QPushButton#resetBtn:disabled {
    color: #3a1a28;
    border-color: #1a0a14;
}

QPushButton#regenBtn {
    color: #ffd080;
    border-color: #4a3a10;
}
QPushButton#regenBtn:hover {
    background-color: #2a200a;
    border-color: #ffd080;
}
QPushButton#regenBtn:disabled {
    color: #3a2e10;
    border-color: #1e1608;
}

QPushButton#scrollBtn {
    background-color: rgba(14, 26, 58, 200);
    color: #4dd9ff;
    border: 1px solid #4dd9ff;
    border-radius: 16px;
    padding: 0;
    min-width: 0;
    font-size: 16px;
}
QPushButton#scrollBtn:hover {
    background-color: rgba(26, 42, 74, 220);
}

QPushButton#tokenToggle {
    background: transparent;
    color: #3d5d8a;
    border: none;
    padding: 0 4px;
    min-width: 0;
    font-size: 14px;
}
QPushButton#tokenToggle:hover {
    color: #4dd9ff;
}

QScrollBar:vertical {
    background-color: #07071a;
    width: 8px;
    border: none;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #2d2d6e;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background-color: #4d4dae;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 0; }

QStatusBar {
    background-color: #050510;
    color: #3d5d8a;
    border-top: 1px solid #0e0e28;
    font-size: 11px;
}
QStatusBar QLabel {
    color: #3d5d8a;
    font-size: 11px;
    padding: 0 6px;
}
"""

# Muted color for timestamps
_TS_COLOR = "#3d5d8a"
# Speaker name colors
_COLOR_USER = "#a78bfa"   # soft purple
_COLOR_AGENT = "#4dd9ff"  # nebula cyan


class InputField(QTextEdit):
    """Single/multiline input: Enter submits, Shift+Enter inserts a newline."""
    submitted = pyqtSignal()

    def __init__(self, placeholder=""):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(72)
        self.setAcceptRichText(False)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.submitted.emit()
        else:
            super().keyPressEvent(event)


class AvatarLabel(QLabel):
    """Clickable avatar panel — emits clicked() on left press."""
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AvatarPopup(QWidget):
    """Floating window showing the avatar image at full size. Click or Esc to close."""

    def __init__(self, pixmap):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("Avatar")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet("background-color: #000000;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        screen = QApplication.primaryScreen().availableGeometry()
        fit = pixmap.scaled(
            screen.width(), screen.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(fit)
        self.resize(fit.width(), fit.height())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def mousePressEvent(self, event):
        self.close()


class ChatDisplay(QTextEdit):
    """Read-only chat log with Ctrl+scroll font zoom and a scroll-to-bottom button."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.viewport().installEventFilter(self)

        self._scroll_btn = QPushButton("↓", self)
        self._scroll_btn.setObjectName("scrollBtn")
        self._scroll_btn.setFixedSize(32, 32)
        self._scroll_btn.hide()
        self._scroll_btn.clicked.connect(self._scroll_to_bottom)

        self.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

    def _scroll_to_bottom(self):
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def _on_scroll_changed(self, value):
        at_bottom = value >= self.verticalScrollBar().maximum()
        self._scroll_btn.setVisible(not at_bottom)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_scroll_btn()

    def _reposition_scroll_btn(self):
        btn = self._scroll_btn
        x = self.width() - btn.width() - 12
        y = self.height() - btn.height() - 12
        btn.move(x, y)
        btn.raise_()

    def eventFilter(self, obj, event):
        if obj is self.viewport() and event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if event.angleDelta().y() > 0:
                    self.zoomIn(1)
                else:
                    self.zoomOut(1)
                return True  # consume — don't also scroll
        return super().eventFilter(obj, event)


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


class EmotionWorker(QThread):
    detected = pyqtSignal(str)

    def __init__(self, reply_text, emotions):
        super().__init__()
        self.reply_text = reply_text
        self.emotions = emotions

    def run(self):
        emotion = detect_emotion(self.reply_text, self.emotions)
        self.detected.emit(emotion)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(AGENT)
        self.session = ChatSession()
        self.worker = None
        self._build_ui()
        self._build_statusbar()
        self._set_avatar("default")
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

        self.avatar_label = AvatarLabel()
        self.avatar_label.setMinimumWidth(280)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.avatar_label.clicked.connect(self._show_avatar_popup)
        self._avatar_state = "default"
        top.addWidget(self.avatar_label)

        self.chat_display = ChatDisplay()
        top.addWidget(self.chat_display, stretch=1)

        root.addLayout(top, stretch=1)

        # Bottom: input + Send + Reset
        bottom = QHBoxLayout()

        self.input_field = InputField("Say something...")
        self.input_field.submitted.connect(self._send)
        bottom.addWidget(self.input_field, stretch=1)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._send)
        bottom.addWidget(self.send_button)

        self.regen_button = QPushButton("Regen")
        self.regen_button.setObjectName("regenBtn")
        self.regen_button.setToolTip("Regenerate last reply")
        self.regen_button.clicked.connect(self._regen)
        self.regen_button.setEnabled(False)
        bottom.addWidget(self.regen_button)

        self.reset_button = QPushButton("Reset")
        self.reset_button.setObjectName("resetBtn")
        self.reset_button.clicked.connect(self._reset)
        bottom.addWidget(self.reset_button)

        root.addLayout(bottom)
        self.resize(960, 640)

    def _build_statusbar(self):
        sb = self.statusBar()

        self._token_label = QLabel("")
        self._token_label.hide()
        sb.addPermanentWidget(self._token_label)

        self._token_toggle = QPushButton("≈")
        self._token_toggle.setObjectName("tokenToggle")
        self._token_toggle.setFixedSize(24, 18)
        self._token_toggle.setToolTip("Toggle token count")
        self._token_toggle.clicked.connect(
            lambda: self._token_label.setVisible(not self._token_label.isVisible())
        )
        sb.addPermanentWidget(self._token_toggle)

        font_down = QPushButton("A-")
        font_down.setObjectName("tokenToggle")
        font_down.setFixedSize(28, 18)
        font_down.setToolTip("Decrease font size")
        font_down.clicked.connect(lambda: self.chat_display.zoomOut(1))
        sb.addPermanentWidget(font_down)

        font_up = QPushButton("A+")
        font_up.setObjectName("tokenToggle")
        font_up.setFixedSize(28, 18)
        font_up.setToolTip("Increase font size")
        font_up.clicked.connect(lambda: self.chat_display.zoomIn(1))
        sb.addPermanentWidget(font_up)

    def _update_token_count(self):
        est = self.session.token_estimate
        self._token_label.setText(f"~{est:,} / {CONTEXT_LENGTH:,} ctx tokens")

    # --- Avatar ---

    def _set_avatar(self, state="default"):
        self._avatar_state = state
        path = os.path.join(_AVATAR_DIR, f"{state}.png")
        if not os.path.exists(path):
            path = os.path.join(_AVATAR_DIR, "default.png")
        self._avatar_pixmap = QPixmap(path)
        self._refresh_avatar()

    def _refresh_avatar(self):
        if not hasattr(self, "_avatar_pixmap") or self._avatar_pixmap.isNull():
            return
        h = int(self.height() * 2 / 3)
        if h < 10:
            h = 480
        scaled = self._avatar_pixmap.scaledToHeight(
            h, Qt.TransformationMode.SmoothTransformation
        )
        self.avatar_label.setPixmap(scaled)

    def _show_avatar_popup(self):
        if not hasattr(self, "_avatar_pixmap") or self._avatar_pixmap.isNull():
            return
        self._popup = AvatarPopup(self._avatar_pixmap)
        self._popup.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_avatar()

    # --- History ---

    def _load_history(self):
        for role, text in self.session._turns:
            speaker = USER if role == "user" else AGENT
            self._append_message(speaker, text)
        self._update_token_count()

    def _append_message(self, speaker, text, ts=None):
        if ts is None:
            ts = datetime.now().strftime("%H:%M")
        color = _COLOR_USER if speaker == USER else _COLOR_AGENT
        self.chat_display.append(
            f'<span style="color:{_TS_COLOR}; font-size:0.85em">{ts}</span> '
            f'<b style="color:{color}">{speaker}:</b> {text}<br>'
        )

    # --- Send / Reply ---

    def _send(self):
        user_input = self.input_field.toPlainText().strip()
        if not user_input:
            return

        if user_input.lower() == "/reset":
            self._reset()
            return

        ts = datetime.now().strftime("%H:%M")
        self.input_field.clear()
        self._append_message(USER, user_input, ts=ts)
        self._dispatch_reply(user_input)

    def _on_token(self, token):
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(token)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()

    def _on_finished(self):
        self.chat_display.append("<br>")
        self._update_token_count()
        self._set_input_enabled(True)
        self._update_regen_button()
        self.input_field.setFocus()

        last_reply = next((t for r, t in reversed(self.session._turns) if r == "assistant"), None)
        if last_reply:
            self._emotion_worker = EmotionWorker(last_reply, _EMOTIONS)
            self._emotion_worker.detected.connect(self._set_avatar)
            self._emotion_worker.start()

    def _on_error(self, msg):
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(f"<br><i style='color:#ff6b6b'>[Error: {msg}]</i>")
        self.chat_display.setTextCursor(cursor)
        self._set_input_enabled(True)

    # --- Regen / Reset / helpers ---

    def _regen(self):
        user_text = self.session.pop_last_exchange()
        if user_text is None:
            return
        # Redraw history without the popped exchange
        self.chat_display.clear()
        for role, text in self.session._turns:
            speaker = USER if role == "user" else AGENT
            self._append_message(speaker, text)
        self._update_token_count()
        self._update_regen_button()
        # Re-display the user message, then stream a new reply
        self._append_message(USER, user_text)
        self._dispatch_reply(user_text)

    def _dispatch_reply(self, user_input):
        """Insert the agent header and start streaming a reply for user_input."""
        ts_reply = datetime.now().strftime("%H:%M")
        self.chat_display.append(
            f'<span style="color:{_TS_COLOR}; font-size:0.85em">{ts_reply}</span> '
            f'<b style="color:{_COLOR_AGENT}">{AGENT}:</b> '
        )
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)

        self._set_input_enabled(False)
        self.worker = ReplyWorker(self.session, user_input)
        self.worker.token_received.connect(self._on_token)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _reset(self):
        self.session.reset()
        self.chat_display.clear()
        self.input_field.clear()
        self._set_avatar("default")
        self._update_token_count()
        self._update_regen_button()

    def _update_regen_button(self):
        can = (len(self.session._turns) >= 2
               and self.session._turns[-1][0] == "assistant")
        self.regen_button.setEnabled(can)

    def _set_input_enabled(self, enabled: bool):
        self.input_field.setEnabled(enabled)
        self.send_button.setEnabled(enabled)
        self.reset_button.setEnabled(enabled)
        if not enabled:
            self.regen_button.setEnabled(False)


def run():
    app = QApplication(sys.argv)
    font = QFont("Ubuntu", 13)
    app.setFont(font)
    app.setStyleSheet(_STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
