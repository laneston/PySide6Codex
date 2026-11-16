import sys

from PySide6.QtWidgets import QApplication

from main_window import MainWindow
from session_selector import SessionSelector


class AppController:
    """管理 SessionSelector 与 MainWindow 的切换。"""

    def __init__(self):
        self.win: MainWindow | None = None

    def run(self) -> int:
        # 第一步：弹出会话选择
        if not self._pick_session_and_open():
            return 0

        # 第二步：进入事件循环
        return QApplication.instance().exec()

    def _pick_session_and_open(self) -> bool:
        selector = SessionSelector()
        if selector.exec() != SessionSelector.DialogCode.Accepted:
            return False
        sid = selector.chosen_session()
        if not sid:
            return False
        self._open_main_window(sid)
        return True

    def _open_main_window(self, session_id: str) -> None:
        self.win = MainWindow(session_id)
        self.win.switch_session_requested.connect(self._on_switch_requested)
        self.win.show()

    def _on_switch_requested(self) -> None:
        """主窗口请求切换会话时，重新打开选择器。"""
        QApplication.processEvents()
        # 主窗口会自行 close；这里直接重开选择器
        if self._pick_session_and_open():
            return
        # 用户在选择器里取消（未选择），则退出程序
        QApplication.instance().quit()


def main() -> int:
    app = QApplication(sys.argv)
    controller = AppController()
    return controller.run()


if __name__ == "__main__":
    sys.exit(main())
