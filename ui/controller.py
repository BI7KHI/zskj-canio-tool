"""
会话控制器
================================================================

把 :class:`canio.session.DeviceSession` 的事件桥接成 Qt 信号，并把所有
可能阻塞的操作（打开串口、发送并等待应答、扫描地址 …）放到线程池执行，
保证界面永不卡顿。

**线程模型**：传输层回调在后台线程触发 -> 这里用 ``Signal.emit`` 投递到
Qt 主线程（队列连接），因此界面槽函数始终运行在 GUI 线程。
"""
from __future__ import annotations

import traceback
from typing import Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from canio import protocol as P
from canio.session import DeviceSession
from canio.transport.base import CanTransport, LogLine


# --------------------------------------------------------------------------- #
# 后台任务
# --------------------------------------------------------------------------- #
class _TaskSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Task(QRunnable):
    def __init__(self, fn: Callable, args: tuple, kwargs: dict):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _TaskSignals()
        # 关键：不能用 autoDelete —— 否则 C++ 对象可能在「跨线程排队」的信号
        # 尚未投递到主线程前就被销毁，导致 done/failed 信号静默丢失。
        # 由 SessionController 持有引用，任务结束后手动释放。
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:
            detail = f"{exc}"
            if not str(exc).strip():
                detail = traceback.format_exc(limit=2).strip().splitlines()[-1]
            self.signals.failed.emit(detail)
        else:
            self.signals.done.emit(result)


# --------------------------------------------------------------------------- #
# 控制器
# --------------------------------------------------------------------------- #
class SessionController(QObject):
    """界面与设备会话之间的唯一桥梁。"""

    frameReceived = Signal(object, object)      # CanFrame, ParsedFrame
    logReceived = Signal(object)                # LogLine
    errorOccurred = Signal(str)
    stateChanged = Signal(dict)                 # 变更字段
    connectionChanged = Signal(bool, str)       # (已连接?, 描述)
    busyChanged = Signal(bool)
    statsTick = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session: Optional[DeviceSession] = None
        self.transport: Optional[CanTransport] = None
        self._pool = QThreadPool.globalInstance()
        self._inflight = 0
        self._tasks: set[_Task] = set()      # 持有引用，防止任务被提前回收
        self.error_log: list[str] = []

        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(500)
        self._stats_timer.timeout.connect(self.statsTick.emit)

    # ------------------------------------------------------------------ #
    @property
    def connected(self) -> bool:
        return self.session is not None and self.session.is_open

    @property
    def addr(self) -> int:
        return self.session.state.addr if self.session else P.DEFAULT_ADDR

    @property
    def extended(self) -> bool:
        return self.session.extended if self.session else False

    # ------------------------------------------------------------------ #
    # 后台任务调度
    # ------------------------------------------------------------------ #
    def submit(self, fn: Callable, *args,
               on_done: Optional[Callable] = None,
               on_error: Optional[Callable] = None,
               **kwargs) -> None:
        task = _Task(fn, args, kwargs)
        self._tasks.add(task)
        self._inflight += 1
        if self._inflight == 1:
            self.busyChanged.emit(True)

        def _finish() -> None:
            self._tasks.discard(task)
            self._inflight = max(0, self._inflight - 1)
            if self._inflight == 0:
                self.busyChanged.emit(False)

        if on_done:
            task.signals.done.connect(on_done)
        if on_error:
            task.signals.failed.connect(on_error)
        # 统一错误上报
        task.signals.failed.connect(self._on_task_error)
        task.signals.done.connect(lambda *_: _finish())
        task.signals.failed.connect(lambda *_: _finish())
        self._pool.start(task)

    def _on_task_error(self, message: str) -> None:
        self.error_log.append(message)
        self.errorOccurred.emit(message)

    # ------------------------------------------------------------------ #
    # 连接 / 断开
    # ------------------------------------------------------------------ #
    def attach(self, transport: CanTransport, addr: int = P.DEFAULT_ADDR,
               extended: bool = False) -> None:
        """绑定一个已经打开好的传输层。"""
        self.detach()
        self.transport = transport
        self.session = DeviceSession(transport, addr=addr)
        self.session.extended = extended
        self.session.set_handlers(
            on_frame=self._on_frame,
            on_log=self._on_log,
            on_error=self._on_error,
            on_state=self._on_state,
        )
        self._stats_timer.start()
        self.connectionChanged.emit(True, transport.description)
        self.emit_full_state()

    def detach(self) -> None:
        self._stats_timer.stop()
        if self.session is not None:
            try:
                self.session.close()
            except Exception:
                pass
        self.session = None
        self.transport = None
        self.connectionChanged.emit(False, "")

    # ------------------------------------------------------------------ #
    # 传输层/会话回调（后台线程）-> Qt 信号（主线程）
    # ------------------------------------------------------------------ #
    def _on_frame(self, frame: P.CanFrame, parsed: P.ParsedFrame) -> None:
        self.frameReceived.emit(frame, parsed)

    def _on_log(self, line: LogLine) -> None:
        self.logReceived.emit(line)

    def _on_error(self, message: str) -> None:
        self.error_log.append(message)
        self.errorOccurred.emit(message)

    def _on_state(self, changed: dict) -> None:
        self.stateChanged.emit(changed)

    def emit_full_state(self) -> None:
        """把完整状态快照推给界面。

        ``_update_state`` 只在「值发生变化」时发信号；若读取到的值与默认值
        相同（例如模块地址本来就是 1），界面就永远收不到初始值。因此在
        连接完成、读取全部参数之后，必须主动补发一次完整快照。
        """
        if self.session is not None:
            self.stateChanged.emit(self.session.state.snapshot())

    # ------------------------------------------------------------------ #
    # 便捷操作（都在后台线程执行）
    # ------------------------------------------------------------------ #
    def set_relays(self, channels, on_done=None) -> None:
        if not self.session:
            return
        self.submit(self.session.write_relays, set(channels), on_done=on_done)

    def write_single(self, channel: int, on: bool, on_done=None) -> None:
        if not self.session:
            return
        self.submit(self.session.write_relay, channel, on, on_done=on_done)

    def read_relays(self, on_done=None) -> None:
        if self.session:
            self.submit(self.session.read_relays, on_done=on_done)

    def read_inputs(self, on_done=None) -> None:
        if self.session:
            self.submit(self.session.read_inputs, on_done=on_done)

    def read_all(self, on_done=None) -> None:
        if not self.session:
            return

        def work():
            result = (self.session.read_address(),
                      self.session.read_baud(),
                      self.session.read_relays(),
                      self.session.read_inputs())
            return result

        def _done(res):
            self.emit_full_state()      # 补发完整快照，保证界面拿到初值
            if on_done:
                on_done(res)

        self.submit(work, on_done=_done)

    def write_address(self, new_addr: int, on_done=None) -> None:
        if self.session:
            self.submit(self.session.write_address, new_addr, on_done=on_done)

    def write_baud(self, code: int, on_done=None) -> None:
        if self.session:
            self.submit(self.session.write_baud, code, on_done=on_done)

    def write_upload(self, ms: int, on_done=None) -> None:
        if self.session:
            self.submit(self.session.write_upload_interval, ms, on_done=on_done)

    def send_raw(self, frame: P.CanFrame) -> None:
        if self.session:
            self.submit(self.session.send_raw, frame)

    def scan(self, first: int, last: int, on_done=None) -> None:
        if self.session:
            self.submit(self.session.scan_addresses, first, last, 0.12,
                        on_done=on_done)

    def set_extended(self, extended: bool) -> None:
        if self.session:
            self.session.apply_extended(extended)

    def set_addr(self, addr: int) -> None:
        if self.session:
            self.session.state.addr = addr

    def start_polling(self, interval_ms: int, read_inputs: bool,
                      read_relays: bool) -> None:
        if self.session:
            self.session.start_polling(interval_ms, read_inputs, read_relays)

    def stop_polling(self) -> None:
        if self.session:
            self.session.stop_polling()

    @property
    def polling(self) -> bool:
        return bool(self.session and self.session.polling)
