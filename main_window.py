import base64
import mimetypes
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from api_worker import StreamWorker
from chat_store import (
    clear_session_messages,
    get_session_name,
    image_abs_path,
    load_messages,
    save_image,
    save_messages,
)
from chat_widgets import MarkdownChatView, PlainPasteTextEdit
from markdown_renderer import decode_copy_url, render_markdown_body

# ---- 配置 ----
load_dotenv()
API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not API_KEY:
    print("错误：未设置 DEEPSEEK_API_KEY", file=sys.stderr)
    sys.exit(1)

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com", timeout=300.0)

MODEL_TEXT = "deepseek-chat"
MODEL_VISION = "deepseek-flash"
MAX_TOKENS = 8192
IMAGE_INLINE_SAFE_BYTES = 20 * 1024 * 1024

TEXT_EXTENSIONS = {
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cc",
    ".cxx",
    ".json",
    ".txt",
    ".md",
    ".py",
    ".csv",
    ".xml",
    ".yaml",
    ".yml",
    ".log",
    ".ini",
    ".cfg",
    ".toml",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".sh",
    ".bat",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _escape_html(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class MainWindow(QMainWindow):
    # 用户点击"切换会话"时发出，由上层 AppController 处理
    switch_session_requested = Signal()

    def __init__(self, session_id: str):
        super().__init__()
        self.session_id = session_id
        self.session_name = get_session_name(session_id)

        self.setWindowTitle(f"DeepSeek 桌面客户端 · {self.session_name}")
        self.resize(1100, 780)

        # ---------- 状态 ----------
        self.messages: list[dict] = load_messages(session_id)
        self.uploaded_files: list[dict] = []
        self.generating = False
        self.current_reply = ""
        self.pending_user_text = ""
        self._pending_text = ""
        self.worker = None
        self._streaming_start_pos = 0
        self._image_cache: dict[str, str] = {}

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(50)
        self._flush_timer.timeout.connect(self._flush_chunks)

        # ---------- UI ----------
        self._build_ui()

        # ---------- 恢复历史 ----------
        if self.messages:
            self._render_messages_to_view()
            self.statusBar().showMessage(
                f"已恢复对话「{self.session_name}」（{len(self.messages)} 条消息）",
                3000,
            )
        else:
            self.statusBar().showMessage(f"新对话「{self.session_name}」已创建", 3000)

    def closeEvent(self, event):  # noqa: N802
        if self.worker is not None:
            try:
                self.worker.cancel()
                self.worker.wait(timeout=1.0)
            except Exception:  # noqa: BLE001
                pass
        super().closeEvent(event)

    # ==================== UI 构建 ====================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        # 顶层布局：上方内容区（stretch=1）+ 底部固定栏
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ---------- 顶部工具条（切换会话） ----------
        top_bar = QHBoxLayout()
        self.switch_btn = QPushButton("🔙 切换会话")
        self.switch_btn.setStyleSheet(
            "QPushButton { padding: 6px 14px; border: 1px solid #d0d7de; "
            "border-radius: 6px; background: #ffffff; font-size: 13px; }"
            "QPushButton:hover { background: #f2f7ff; }"
        )
        self.switch_btn.clicked.connect(self._on_switch_session)
        top_bar.addWidget(self.switch_btn)
        top_bar.addStretch(1)

        self.session_label = QLabel(f"当前会话：{self.session_name}")
        self.session_label.setStyleSheet("font-size: 13px; color: #555;")
        top_bar.addWidget(self.session_label)
        root.addLayout(top_bar)

        # ---------- 中部内容区（左聊天 / 右附件） ----------
        splitter = QSplitter(Qt.Horizontal)

        # ---- 左侧（聊天视图） ----
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_view = MarkdownChatView()
        self.chat_view.anchorClicked.connect(self._on_anchor_clicked)
        left_layout.addWidget(self.chat_view, stretch=1)
        splitter.addWidget(left)

        # ---- 右侧（附件） ----
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_title = QLabel("待分析附件：")
        right_title.setStyleSheet("font-size: 13px; color: #333;")
        right_layout.addWidget(right_title)
        self.file_list = QListWidget()
        self.file_list.setStyleSheet(
            "QListWidget { background: #ffffff; border: 1px solid #e1e4e8; "
            "border-radius: 6px; }"
        )
        right_layout.addWidget(self.file_list, stretch=1)
        splitter.addWidget(right)

        splitter.setSizes([800, 300])
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)  # ← 内容区吃掉剩余空间

        # ---------- 底部：输入 + 右侧按钮竖排 ----------
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self.input_box = PlainPasteTextEdit()
        self.input_box.setPlaceholderText("输入需求，或拖入/选择代码、JSON、图片文件……")
        self.input_box.setFixedHeight(96)
        self.input_box.setStyleSheet(
            "QTextEdit { background: #ffffff; border: 1px solid #d0d7de; "
            "border-radius: 6px; padding: 6px; font-size: 13px; }"
        )
        bottom.addWidget(self.input_box, stretch=1)

        # 按钮竖排（右下角同一列）
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)

        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedWidth(120)
        self.send_btn.setStyleSheet(self._primary_btn_css())
        self.send_btn.clicked.connect(self.send_message)
        btn_col.addWidget(self.send_btn)

        self.attach_btn = QPushButton("📎 上传文件")
        self.attach_btn.setFixedWidth(120)
        self.attach_btn.setStyleSheet(self._secondary_btn_css())
        self.attach_btn.clicked.connect(self.attach_file)
        btn_col.addWidget(self.attach_btn)

        self.clear_btn = QPushButton("🗑 清空消息")
        self.clear_btn.setFixedWidth(120)
        self.clear_btn.setStyleSheet(self._danger_btn_css())
        self.clear_btn.clicked.connect(self.clear_history)
        btn_col.addWidget(self.clear_btn)

        btn_col.addStretch(1)
        bottom.addLayout(btn_col)

        root.addLayout(bottom)

    @staticmethod
    def _primary_btn_css() -> str:
        return (
            "QPushButton { background:#1976d2; color:#fff; border:none; "
            "border-radius:6px; padding:8px 12px; font-weight:600; font-size:13px; }"
            "QPushButton:hover { background:#1565c0; }"
            "QPushButton:disabled { background:#b0bec5; }"
        )

    @staticmethod
    def _secondary_btn_css() -> str:
        return (
            "QPushButton { background:#ffffff; color:#333; "
            "border:1px solid #d0d7de; border-radius:6px; padding:8px 12px; "
            "font-size:13px; }"
            "QPushButton:hover { background:#f2f7ff; }"
            "QPushButton:disabled { color:#b0bec5; }"
        )

    @staticmethod
    def _danger_btn_css() -> str:
        return (
            "QPushButton { background:#fff1f0; color:#d4380d; "
            "border:1px solid #ffccc7; border-radius:6px; padding:8px 12px; "
            "font-size:13px; }"
            "QPushButton:hover { background:#ffe7e5; }"
            "QPushButton:disabled { color:#b0bec5; }"
        )

    # ---------- 切换会话 ----------
    def _on_switch_session(self):
        if self.generating:
            QMessageBox.information(self, "提示", "请等待当前回复完成后再切换对话。")
            return
        self.switch_session_requested.emit()
        self.close()

    # ---------- 复制锚点（保持滚动位置） ----------
    def _on_anchor_clicked(self, url):
        code = decode_copy_url(url.toString())
        if code is None:
            return
        # 先把滚动交给 widget 内部做两段恢复（立即 + 下一帧），彻底避免跳顶
        self.chat_view.copy_and_restore(code)
        self.statusBar().showMessage("代码已复制到剪贴板", 2000)

    # ---------- 文件加载 ----------
    def attach_file(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择文件（可多选）",
            "",
            "代码/文本 (*.c *.cpp *.h *.hpp *.json *.txt *.md *.py *.csv);;"
            "图片 (*.jpg *.jpeg *.png *.gif *.webp);;所有文件 (*)",
        )
        for path in paths or []:
            p = Path(path)
            ext = p.suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                self._load_image(p)
            elif ext in TEXT_EXTENSIONS:
                self._load_text(p)
            else:
                QMessageBox.warning(self, "不支持", f"暂不支持 {p.name}")

    def _load_text(self, path: Path):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="gbk", errors="ignore")
        self.uploaded_files.append({"type": "text", "name": path.name, "content": text})
        self.file_list.addItem(f"[文本] {path.name}")

    def _load_image(self, path: Path):
        if path.stat().st_size > IMAGE_INLINE_SAFE_BYTES:
            QMessageBox.warning(self, "图片过大", f"{path.name} 超过 20 MB 上限")
            return
        try:
            raw = path.read_bytes()
        except OSError as e:
            QMessageBox.warning(self, "读取失败", f"无法读取 {path.name}：{e}")
            return
        rel_name = save_image(self.session_id, raw, path.suffix)
        if not rel_name:
            QMessageBox.warning(self, "保存失败", "图片无法写入本地存储目录")
            return
        self.uploaded_files.append(
            {"type": "image", "name": path.name, "path": rel_name}
        )
        self.file_list.addItem(f"[图片] {path.name}")

    # ==================== 构造 API 请求 ====================
    IMAGE_HISTORY_LIMIT = 3

    def _build_api_messages(self) -> tuple[list[dict], bool]:
        api_messages: list[dict] = []
        has_image = False
        total = len(self.messages)
        for idx, msg in enumerate(self.messages):
            content = msg.get("content")
            in_recent = idx >= total - self.IMAGE_HISTORY_LIMIT
            if isinstance(content, list):
                blocks: list[dict] = []
                for item in content:
                    typ = item.get("type")
                    if typ == "text":
                        blocks.append({"type": "text", "text": item.get("text", "")})
                    elif typ == "image":
                        if not in_recent:
                            blocks.append(
                                {
                                    "type": "text",
                                    "text": f"[图片:{item.get('name', 'unknown')}（历史省略）]",
                                }
                            )
                            continue
                        data_url = self._read_image_as_data_url(item.get("path", ""))
                        if data_url:
                            blocks.append(
                                {"type": "image_url", "image_url": {"url": data_url}}
                            )
                            has_image = True
                        else:
                            name = item.get("name", "unknown")
                            blocks.append(
                                {"type": "text", "text": f"[图片缺失:{name}]"}
                            )
                api_messages.append({"role": msg["role"], "content": blocks})
            else:
                api_messages.append({"role": msg["role"], "content": content or ""})
        return api_messages, has_image

    def _read_image_as_data_url(self, rel_name: str) -> str | None:
        if not rel_name:
            return None
        if rel_name in self._image_cache:
            return self._image_cache[rel_name]
        path = image_abs_path(self.session_id, rel_name)
        if not path.exists():
            return None
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        data_url = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
        self._image_cache[rel_name] = data_url
        return data_url

    # ==================== 发送 ====================
    def send_message(self):
        if self.generating:
            return
        user_text = self.input_box.toPlainText().strip()
        if not user_text and not self.uploaded_files:
            return

        self.input_box.clear()
        self.pending_user_text = user_text
        self.current_reply = ""
        self._pending_text = ""

        text_parts: list[str] = []
        image_items: list[dict] = []
        for f in self.uploaded_files:
            if f["type"] == "text":
                text_parts.append(f"\n\n===== {f['name']} =====\n{f['content']}")
            elif f["type"] == "image":
                image_items.append({"path": f["path"], "name": f["name"]})

        full_user_text = user_text + "".join(text_parts)

        if image_items:
            user_content = [{"type": "text", "text": full_user_text}]
            for img in image_items:
                user_content.append(
                    {"type": "image", "path": img["path"], "name": img["name"]}
                )
            self.messages.append({"role": "user", "content": user_content})
        else:
            self.messages.append({"role": "user", "content": full_user_text})

        api_messages, has_image = self._build_api_messages()
        model = MODEL_VISION if has_image else MODEL_TEXT

        self.chat_view.append(f"\n🧑 你：{user_text}\n")
        for img in image_items:
            self.chat_view.append(f"[图片：{img['name']}]\n")
        self.chat_view.append("🤖 DeepSeek：")
        self._streaming_start_pos = self.chat_view.textCursor().position()

        self._set_generating(True)
        self.worker = StreamWorker(client, api_messages, model, MAX_TOKENS)
        self.worker.chunk_received.connect(self.on_chunk)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def _set_generating(self, flag):
        self.generating = flag
        for btn in (self.send_btn, self.attach_btn, self.clear_btn, self.switch_btn):
            btn.setEnabled(not flag)

    # ==================== 流式显示 ====================
    def on_chunk(self, text):
        self._pending_text += text
        self.current_reply += text
        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _flush_chunks(self):
        if not self._pending_text:
            self._flush_timer.stop()
            return
        text, self._pending_text = self._pending_text, ""
        cursor = self.chat_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.chat_view.setTextCursor(cursor)
        self.chat_view.ensureCursorVisible()

    # ==================== 完成 ====================
    def on_finished(self):
        self._flush_chunks()
        self._flush_timer.stop()

        reply = self.current_reply.strip()
        if reply:
            self.messages.append({"role": "assistant", "content": reply})
        else:
            self.messages.append({"role": "assistant", "content": "（本轮无输出）"})

        self._render_messages_to_view()
        save_messages(self.session_id, self.messages)

        self.uploaded_files.clear()
        self.file_list.clear()
        self.pending_user_text = ""
        self.current_reply = ""
        self._pending_text = ""
        self.worker = None
        self._set_generating(False)

    def _render_messages_to_view(self):
        html_parts: list[str] = []
        for msg in self.messages:
            role = msg.get("role")
            content = msg.get("content")

            if isinstance(content, list):
                texts: list[str] = []
                images: list[dict] = []
                for item in content:
                    typ = item.get("type")
                    if typ == "text":
                        texts.append(item.get("text", ""))
                    elif typ == "image":
                        images.append(item)
                text = "".join(texts)
                if role == "user":
                    html_parts.append(
                        f"<p><b>🧑 你：</b>{_escape_html(text).replace(chr(10), '<br/>')}</p>"
                    )
                    for img in images:
                        abs_path = image_abs_path(self.session_id, img.get("path", ""))
                        if abs_path.exists():
                            src = abs_path.as_uri()
                            html_parts.append(
                                f'<p><img src="{src}" '
                                f'style="max-width:400px;max-height:300px;" '
                                f'alt="{_escape_html(img.get("name", ""))}"/></p>'
                            )
                        else:
                            html_parts.append(
                                f"<p>[图片缺失："
                                f"{_escape_html(img.get('name', ''))}]</p>"
                            )
                else:
                    html_parts.append(
                        f"<p><b>🤖 DeepSeek：</b></p>"
                        f"{render_markdown_for_assistant(text)}"
                    )
            else:
                text = content or ""
                if role == "user":
                    html_parts.append(
                        f"<p><b>🧑 你：</b>{_escape_html(text).replace(chr(10), '<br/>')}</p>"
                    )
                elif role == "assistant":
                    html_parts.append(
                        f"<p><b>🤖 DeepSeek：</b></p>"
                        f"{render_markdown_for_assistant(text)}"
                    )

        self.chat_view.setHtml(
            f"<html><head><meta charset='utf-8'></head>"
            f"<body>{''.join(html_parts)}</body></html>"
        )
        # 移到末尾，显示最新消息
        cursor = self.chat_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_view.setTextCursor(cursor)
        self.chat_view.ensureCursorVisible()

    # ==================== 错误 ====================
    def on_error(self, msg):
        self._flush_chunks()
        self._flush_timer.stop()
        self.chat_view.append(f"\n[错误] {msg}\n")

        if self.messages and self.messages[-1].get("role") == "user":
            self.messages.pop()

        if self.pending_user_text and not self.input_box.toPlainText().strip():
            self.input_box.setPlainText(self.pending_user_text)

        self.uploaded_files.clear()
        self.file_list.clear()
        self._image_cache.clear()

        self.pending_user_text = ""
        self.current_reply = ""
        self._pending_text = ""
        self.worker = None
        self._set_generating(False)

    # ==================== 清空本会话 ====================
    def clear_history(self):
        if self.generating:
            return
        ret = QMessageBox.question(
            self,
            "确认清空",
            "将清空当前会话的全部消息与图片，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        self.messages.clear()
        self.chat_view.clear()
        self.uploaded_files.clear()
        self.file_list.clear()
        self.current_reply = ""
        self._pending_text = ""
        self._flush_timer.stop()
        self._image_cache.clear()
        clear_session_messages(self.session_id)
        self.statusBar().showMessage("本对话消息已清空", 2000)


def render_markdown_for_assistant(md_text: str) -> str:
    """渲染助手 Markdown 内容，仅返回 body 片段（含代码块复制锚点）。"""
    return render_markdown_body(md_text)
