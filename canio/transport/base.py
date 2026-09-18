"""CAN 传输层抽象接口。"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional

from ..protocol import CanFrame

#: 传输层事件回调
FrameCallback = Callable[[CanFrame], None]
LogCallback = Callable[["LogLine"], None]
ErrorCallback = Callable[[str], None]


@dataclass
class LogLine:
    """传输层原始交互日志（例如 SLCAN 的 ASCII 行）。"""

    direction: str          # "TX" | "RX" | "SYS"
    text: str
    detail: str = ""


class TransportError(Exception):
    """传输层打开/读写出错。"""


class TransportUnavailable(TransportError):
    """当前环境不支持该传输方式（dll 缺失、无串口等）。"""


class CanTransport(ABC):
    """所有传输方式的公共基类。

    约定：
      * ``open()`` / ``close()`` 由调用线程执行；
      * ``send()`` 线程安全；
      * 收到的报文通过 ``on_frame`` 回调送出，**回调运行在后台线程**，
        上层需自行切换到界面线程。
    """

    #: 界面上显示的名字
    display_name = "未命名"
    #: 该传输方式是否在当前机器上可用
    @classmethod
    def is_available(cls) -> bool:
        return True

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._open = False
        self._on_frame: Optional[FrameCallback] = None
        self._on_log: Optional[LogCallback] = None
        self._on_error: Optional[ErrorCallback] = None

    # -- 回调注册 ---------------------------------------------------------- #
    def set_callbacks(self, on_frame: Optional[FrameCallback] = None,
                      on_log: Optional[LogCallback] = None,
                      on_error: Optional[ErrorCallback] = None) -> None:
        self._on_frame = on_frame
        self._on_log = on_log
        self._on_error = on_error

    def _emit_frame(self, frame: CanFrame) -> None:
        cb = self._on_frame
        if cb:
            try:
                cb(frame)
            except Exception:                       # 回调异常不得打断收包线程
                pass

    def _emit_log(self, direction: str, text: str, detail: str = "") -> None:
        cb = self._on_log
        if cb:
            try:
                cb(LogLine(direction, text, detail))
            except Exception:
                pass

    def _emit_error(self, message: str) -> None:
        cb = self._on_error
        if cb:
            try:
                cb(message)
            except Exception:
                pass

    # -- 生命周期 ---------------------------------------------------------- #
    @property
    def is_open(self) -> bool:
        return self._open

    @abstractmethod
    def open(self) -> None:
        """打开通道，失败时抛出 TransportError。"""

    @abstractmethod
    def close(self) -> None:
        """关闭通道，必须可重复调用。"""

    @abstractmethod
    def send(self, frame: CanFrame) -> None:
        """发送一帧；未打开时抛出 TransportError。"""

    # -- 可选能力 ---------------------------------------------------------- #
    @classmethod
    def supported_bitrates(cls) -> list[int]:
        """该传输方式支持的 CAN 波特率（bps）。"""
        return []

    @property
    def description(self) -> str:
        """连接成功后用于状态栏的一句话描述。"""
        return self.display_name
