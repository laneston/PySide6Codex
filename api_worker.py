import threading

from openai import OpenAI
from PySide6.QtCore import QObject, Signal


class StreamWorker(QObject):
    chunk_received = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, client: OpenAI, messages, model: str, max_tokens: int):
        super().__init__()
        self._client = client
        self._messages = messages
        self._model = model
        self._max_tokens = max_tokens
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None

    def cancel(self) -> None:
        """请求取消当前流式输出（线程将在下一个 chunk 时退出）。"""
        self._cancel_event.set()

    def run(self):
        try:
            stream = self._client.chat.completions.create(
                model=self._model,
                messages=self._messages,
                max_tokens=self._max_tokens,
                stream=True,
            )
            for chunk in stream:
                if self._cancel_event.is_set():
                    break
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    self.chunk_received.emit(delta.content)
            self.finished.emit()
        except Exception as e:  # noqa: BLE001
            if self._cancel_event.is_set():
                # 取消导致的异常不视为错误
                self.finished.emit()
            else:
                self.error.emit(str(e))

    def start(self):
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def wait(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)
