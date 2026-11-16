from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextBrowser, QTextEdit, QAbstractScrollArea

from markdown_renderer import render_markdown_to_html


class PlainPasteTextEdit(QTextEdit):
    """粘贴时自动去除富文本格式，仅保留纯文本（换行与空格不受影响）。"""

    def insertFromMimeData(self, source):  # noqa: N802
        if source.hasText():
            self.insertPlainText(source.text())
        else:
            super().insertFromMimeData(source)


class MarkdownChatView(QTextBrowser):
    """渲染 Markdown 的对话显示区，支持点击代码块下方的复制锚点。"""

    # 浅绿色背景
    BACKGROUND = "#eaf7ec"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.setPlaceholderText("对话记录将显示在这里……")
        self.setStyleSheet(
            f"QTextBrowser {{ background-color: {self.BACKGROUND}; "
            f"border: 1px solid #cfe8d3; border-radius: 6px; padding: 4px; }}"
        )
        # 确保滚动条位置控制可用
        self.setVerticalScrollBarPolicy(self.verticalScrollBarPolicy())

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
