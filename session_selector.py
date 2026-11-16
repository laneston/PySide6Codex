from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chat_store import (
    create_session,
    delete_session,
    format_size,
    list_sessions,
)


class SessionRow(QWidget):
    """单条历史会话行：名称 + 大小 + 删除按钮。点击行主体即打开会话。"""

    open_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, session: dict, parent=None):
        super().__init__(parent)
        self.session_id = session["id"]
        self.setMinimumHeight(64)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 左侧：名称 + 大小
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        self.name_label = QLabel(session["name"])
        self.name_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #222;")
        # 让 QLabel 不拦截鼠标事件，确保点击文字也能触发父控件
        self.name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.size_label = QLabel(f"大小：{format_size(session['size_bytes'])}")
        self.size_label.setStyleSheet("font-size: 12px; color: #888;")
        self.size_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.size_label)
        layout.addLayout(text_layout, stretch=1)

        # 右侧：删除按钮
        self.del_btn = QPushButton("🗑 删除")
        self.del_btn.setFixedWidth(84)
        self.del_btn.setStyleSheet("""
            QPushButton {
                background-color: #fff1f0;
                color: #d4380d;
                border: 1px solid #ffccc7;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #ffe7e5; }
            QPushButton:pressed { background-color: #ffd8d6; }
            """)
        self.del_btn.clicked.connect(
            lambda: self.delete_requested.emit(self.session_id)
        )
        layout.addWidget(self.del_btn)

        self.setStyleSheet("""
            SessionRow {
                background-color: #ffffff;
            }
            SessionRow:hover {
                background-color: #f5f8ff;
            }
            """)

    def mouseReleaseEvent(self, event):
        # 点击行主体（非删除按钮区域）时打开会话；
        # 当鼠标在删除按钮上时，QPushButton 已经处理，这里跳过。
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self.del_btn.mapFrom(self, event.position().toPoint())
            if not self.del_btn.rect().contains(pos):
                self.open_requested.emit(self.session_id)
        super().mouseReleaseEvent(event)


class SessionSelector(QDialog):
    """启动时的会话选择窗口。选择或新建后返回 session_id。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DeepSeek 桌面客户端 · 选择对话")
        self.resize(640, 520)
        self.setStyleSheet("QDialog { background-color: #f7f8fa; }")

        self._chosen_id: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # ---- 标题 ----
        title = QLabel("新建对话")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #222;")
        root.addWidget(title)

        # ---- 新建行 ----
        create_row = QHBoxLayout()
        create_row.setSpacing(10)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("输入对话名称，例如：C++ 内存优化")
        self.name_input.setStyleSheet("""
            QLineEdit {
                padding: 8px 12px;
                font-size: 13px;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                background-color: #ffffff;
            }
            QLineEdit:focus {
                border: 1px solid #1976d2;
            }
            """)
        self.name_input.returnPressed.connect(self._on_create)
        create_row.addWidget(self.name_input, stretch=1)

        self.create_btn = QPushButton("➕ 新建对话")
        self.create_btn.setStyleSheet("""
            QPushButton {
                background-color: #1976d2;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #1565c0; }
            QPushButton:pressed { background-color: #0d47a1; }
            QPushButton:disabled { background-color: #b0bec5; }
            """)
        self.create_btn.clicked.connect(self._on_create)
        create_row.addWidget(self.create_btn)
        root.addLayout(create_row)

        # ---- 历史对话标题 ----
        history_title = QLabel("历史对话")
        history_title.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #222; margin-top: 8px;"
        )
        root.addWidget(history_title)

        # ---- 会话列表 ----
        self.session_list = QListWidget()
        self.session_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.session_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.session_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e1e4e8;
                border-radius: 8px;
                background-color: #ffffff;
                padding: 4px;
            }
            """)
        root.addWidget(self.session_list, stretch=1)

        # ---- 空列表提示 ----
        self.empty_label = QLabel("暂无历史对话，请在上方新建一个对话。")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #888; font-size: 13px;")
        root.addWidget(self.empty_label)

        # ---- 首次渲染 ----
        self._refresh_sessions()

    # ---------- 刷新会话列表 ----------
    def _refresh_sessions(self):
        self.session_list.clear()
        sessions = list_sessions()
        if not sessions:
            self.session_list.setVisible(False)
            self.empty_label.setVisible(True)
            return

        self.session_list.setVisible(True)
        self.empty_label.setVisible(False)

        for s in sessions:
            # 不把 parent 设成 session_list，否则 addItem 会再添加一次
            item = QListWidgetItem()
            row = SessionRow(s)
            item.setSizeHint(row.sizeHint())
            self.session_list.addItem(item)
            self.session_list.setItemWidget(item, row)
            row.open_requested.connect(self._on_open_session)
            row.delete_requested.connect(self._on_delete_session)

    # ---------- 新建 ----------
    def _on_create(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入对话名称")
            return
        try:
            sid = create_session(name)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "创建失败", str(e))
            return
        self._chosen_id = sid
        self.accept()

    # ---------- 打开历史会话 ----------
    def _on_open_session(self, session_id: str):
        self._chosen_id = session_id
        self.accept()

    # ---------- 删除历史会话 ----------
    def _on_delete_session(self, session_id: str):
        ret = QMessageBox.question(
            self,
            "确认删除",
            "删除后该会话的全部消息与图片将不可恢复，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        delete_session(session_id)
        self._refresh_sessions()

    # ---------- 对外接口 ----------
    def chosen_session(self) -> str | None:
        return self._chosen_id
