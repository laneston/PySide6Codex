from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextBrowser, QTextEdit, QAbstractScrollArea

from markdown_renderer import render_markdown_to_html


class MarkdownChatView(QTextBrowser):
    """渲染 Markdown 的对话显示区，支持点击代码块下方的复制锚点。"""

    # 浅绿色背景
    BACKGROUND = "#eaf7ec"

    def __init__(self, parent=None):
        super().__init__(parent)
        # 关键：禁止 QTextBrowser 内建导航行为，避免 url 变化导致 scrollToAnchor 回退到 0
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.setReadOnly(True)
        self.setPlaceholderText("对话记录将显示在这里……")
        self.setStyleSheet(
            f"QTextBrowser {{ background-color: {self.BACKGROUND}; "
            f"border: 1px solid #cfe8d3; border-radius: 6px; padding: 4px; }}"
        )

    def set_markdown(self, md_text: str):
        self.setHtml(render_markdown_to_html(md_text))

    def scroll_to_end(self):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def scrollbar_position(self) -> int:
        return self.verticalScrollBar().value()

    def set_scrollbar_position(self, value: int) -> None:
        self.verticalScrollBar().setValue(value)

    def copy_and_restore(self, text: str) -> None:
        """复制文本并恢复滚动位置。

        QTextBrowser 在处理 anchor 点击后，会在事件循环下一帧再刷新一次滚动条
        （内建的 scrollToAnchor / ensureCursorVisible 逻辑）。因此必须在下一帧
        用 QTimer.singleShot(0) 再恢复一次滚动位置，才能确保界面不跳顶。
        """
        from PySide6.QtGui import QGuiApplication

        old_scroll = self.verticalScrollBar().value()
        QGuiApplication.clipboard().setText(text)
        # 第一恢复：立即恢复一次
        self.verticalScrollBar().setValue(old_scroll)
        # 第二恢复：下一帧再恢复一次，覆盖 QTextBrowser 内部后续滚动
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(old_scroll))


class PlainPasteTextEdit(QTextEdit):
    """只粘贴纯文本的 QTextEdit。

    默认 QTextEdit 粘贴时会保留源格式（字号、颜色、字体等），
    从浏览器或 Word 复制内容后会把样式一并带入输入框。
    重写 insertFromMimeData 强制走 insertPlainText，只保留纯文本。
    """

    def insertFromMimeData(self, source):  # noqa: N802 (Qt 命名风格)
        if source.hasText():
            self.insertPlainText(source.text())
        else:
            super().insertFromMimeData(source)
