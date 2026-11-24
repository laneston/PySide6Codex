import threading

from openai import OpenAI
from PySide6.QtCore import QObject, Signal


class StreamWorker(QObject):
    chunk_received = Signal(str)
    reasoning_chunk = Signal(str)  # 新增：思维链增量
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        client: OpenAI,
        messages,
        model: str,
        max_tokens: int,
        reasoning_effort: str = "high",  # 新增：low / high / max
        thinking_enabled: bool = True,  # 新增：是否开启思考模式
    ):
        super().__init__()
        self._client = client
        self._messages = messages
        self._model = model
        self._max_tokens = max_tokens
        self._reasoning_effort = reasoning_effort
        self._thinking_enabled = thinking_enabled
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None

    def cancel(self) -> None:
        """请求取消当前流式输出（线程将在下一个 chunk 时退出）。"""
        self._cancel_event.set()

    def run(self):
        try:
            kwargs = {
                "model": self._model,
                "messages": self._messages,
                "max_tokens": self._max_tokens,
                "stream": True,
                "reasoning_effort": self._reasoning_effort,
                "extra_body": {
                    "thinking": {
                        "type": "enabled" if self._thinking_enabled else "disabled"
                    }
                },
            }
            stream = self._client.chat.completions.create(**kwargs)
            for chunk in stream:
                if self._cancel_event.is_set():
                    break
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta is None:
                    continue
                # 思维链内容
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    self.reasoning_chunk.emit(reasoning)
                # 最终回答内容
                if delta.content:
                    self.chunk_received.emit(delta.content)
            self.finished.emit()
        except Exception as e:  # noqa: BLE001
            if self._cancel_event.is_set():
                self.finished.emit()
            else:
                self.error.emit(str(e))

    def start(self):
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def wait(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)
