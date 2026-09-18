"""
SLCAN / Lawicel ASCII 串口传输层
================================================================

适用于 CANable、CANtact，以及绝大多数 CH340 / CH343 / CP2102 / FT232 /
STM32-VCP 等 USB-CAN 转接器。

协议命令（均为 ASCII，以 CR 结尾）
----------------------------------
``S<n>``  设置 CAN 波特率        ``O``     打开 CAN 通道
``C``     关闭 CAN 通道          ``F``     读状态标志
``V``     读版本/序列号          ``tIIIDDDD...``  发送标准帧
``TIIIIIIIIDDDD...``            发送扩展帧

其中 ``t`` 帧为 3 位十六进制 ID + 最多 16 位十六进制数据；
``T`` 帧为 8 位十六进制 ID + 最多 16 位十六进制数据。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Optional

from ..protocol import CanFrame, EXT_MAGIC, frame_from_slcan
from .base import CanTransport, TransportError, TransportUnavailable

try:                                    # pyserial 为可选依赖
    import serial
    from serial.tools import list_ports as _list_ports
    _HAVE_SERIAL = True
except Exception:                       # pragma: no cover
    serial = None                        # type: ignore
    _list_ports = None                   # type: ignore
    _HAVE_SERIAL = False

#: CAN 波特率 -> SLCAN 的 S 码
BPS_TO_S_CODE: dict[int, int] = {
    10_000: 0,
    20_000: 1,
    50_000: 2,
    100_000: 3,
    125_000: 4,
    250_000: 5,
    500_000: 6,
    800_000: 7,
    1_000_000: 8,
}
S_CODE_TO_BPS: dict[int, int] = {v: k for k, v in BPS_TO_S_CODE.items()}

#: 串口端（USB 侧）常见波特率
HOST_BAUDS = [9600, 19200, 38400, 57600, 115200, 230400, 250000, 500000,
              921600, 1000000, 2000000]


def list_serial_ports() -> list[tuple[str, str]]:
    """返回 [(设备名, 描述), ...]，按设备名排序。"""
    if not _HAVE_SERIAL:
        return []
    out = []
    for p in _list_ports.comports():
        desc = p.description or ""
        if p.manufacturer and p.manufacturer not in desc:
            desc = f"{desc} ({p.manufacturer})".strip()
        out.append((p.device, desc))
    out.sort(key=lambda t: (len(t[0]), t[0]))
    return out


class SlcanTransport(CanTransport):
    """基于串口的 SLCAN 传输。"""

    display_name = "SLCAN (串口)"

    def __init__(self, port: str = "", host_baud: int = 115200,
                 can_bitrate: int = 250_000, open_delay: float = 0.08,
                 echo_suppress: bool = True) -> None:
        super().__init__()
        self.port = port
        self.host_baud = int(host_baud)
        self.can_bitrate = int(can_bitrate)
        self.open_delay = float(open_delay)
        self.echo_suppress = bool(echo_suppress)

        self._ser: Optional["serial.Serial"] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._buf = bytearray()
        self._write_lock = threading.Lock()
        self._recent_tx: deque[tuple[bytes, float]] = deque(maxlen=64)
        self.version = ""

    # ------------------------------------------------------------------ #
    @classmethod
    def is_available(cls) -> bool:
        return _HAVE_SERIAL

    @classmethod
    def supported_bitrates(cls) -> list[int]:
        return sorted(BPS_TO_S_CODE)

    # ------------------------------------------------------------------ #
    def open(self) -> None:
        if self._open:
            return
        if not _HAVE_SERIAL:
            raise TransportUnavailable("未安装 pyserial，无法使用串口传输")
        if not self.port:
            raise TransportError("未选择串口")

        code = BPS_TO_S_CODE.get(self.can_bitrate)
        if code is None:
            raise TransportError(
                f"SLCAN 不支持 {self.can_bitrate // 1000} kbps"
                "（仅支持 10/20/50/100/125/250/500/800/1000 kbps）")

        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.host_baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.05,
                write_timeout=1.0,
            )
        except Exception as exc:
            raise TransportError(f"打开串口 {self.port} 失败：{exc}") from exc

        self._stop.clear()
        self._buf.clear()
        self._recent_tx.clear()

        self._emit_log("SYS", f"已打开串口 {self.port} @ {self.host_baud} bps")

        try:
            self._ser.reset_input_buffer()
            self._ser.reset_output_buffer()
        except Exception:
            pass

        # ---- SLCAN 初始化时序：C -> S<n> -> O ---- #
        self._raw_write("C")
        time.sleep(self.open_delay)
        self._raw_write(f"S{code}")
        time.sleep(self.open_delay)
        self._raw_write("O")
        time.sleep(self.open_delay)

        self._open = True
        self._rx_thread = threading.Thread(target=self._reader_loop,
                                           name="slcan-rx", daemon=True)
        self._rx_thread.start()

        # 尽力读取版本号（并非所有适配器都支持）
        try:
            self._raw_write("V")
        except Exception:
            pass

        self._emit_log(
            "SYS",
            f"CAN 通道已打开：S{code} = {self.can_bitrate // 1000} kbps"
            + ("  (标准帧/扩展帧均可)" if True else ""))

    def close(self) -> None:
        if not self._open and self._ser is None:
            return
        was_open = self._open
        self._open = False
        self._stop.set()

        if self._ser is not None:
            if was_open:
                try:
                    self._raw_write("C")
                except Exception:
                    pass
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

        if self._rx_thread is not None and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
        self._rx_thread = None
        self._emit_log("SYS", "串口已关闭")

    # ------------------------------------------------------------------ #
    def _raw_write(self, cmd: str) -> None:
        if self._ser is None:
            raise TransportError("串口未打开")
        line = cmd + "\r"
        with self._write_lock:
            self._ser.write(line.encode("ascii"))
            self._ser.flush()
        self._emit_log("TX", cmd.strip())

    def send(self, frame: CanFrame) -> None:
        if not self._open:
            raise TransportError("CAN 通道未打开")
        body = "".join(f"{b:02X}" for b in frame.data)
        if frame.extended:
            cmd = f"T{frame.can_id:08X}{body}"
        else:
            cmd = f"t{frame.can_id:03X}{body}"
        self._raw_write(cmd)
        if self.echo_suppress:
            key = (frame.can_id.to_bytes(4, "big") + (b"\x01" if frame.extended else b"\x00")
                   + bytes(frame.data))
            self._recent_tx.append((key, time.monotonic()))

    # ------------------------------------------------------------------ #
    def _reader_loop(self) -> None:
        while not self._stop.is_set():
            try:
                ser = self._ser
                if ser is None:
                    break
                chunk = ser.read(256)
            except Exception as exc:
                if not self._stop.is_set():
                    self._emit_error(f"串口读取错误：{exc}")
                break
            if not chunk:
                continue
            self._buf.extend(chunk)
            self._drain_buffer()
        self._buf.clear()

    def _drain_buffer(self) -> None:
        """按 CR / LF 切分，逐条处理 SLCAN 回复。"""
        while True:
            idx = -1
            for i, b in enumerate(self._buf):
                if b in (0x0D, 0x0A):
                    idx = i
                    break
            if idx < 0:
                return
            raw = bytes(self._buf[:idx])
            del self._buf[: idx + 1]
            if not raw:
                continue
            self._handle_line(raw.decode("ascii", "replace").strip())

    def _handle_line(self, line: str) -> None:
        if not line:
            return
        head = line[0]
        # 收帧
        if head in "tT":
            frame = frame_from_slcan(line, timestamp=time.time(), tx=False)
            if frame is None:
                self._emit_log("RX", line, "无法解析的帧")
                return
            if self.echo_suppress and self._is_recent_echo(frame):
                self._emit_log("SYS", f"(忽略回显) {line}")
                return
            self._emit_log("RX", line)
            self._emit_frame(frame)
            return
        if head in "rR":
            self._emit_log("RX", line, "远程帧")
            return
        if head == "V":
            self.version = line[1:].strip()
            self._emit_log("SYS", f"适配器版本：{self.version}")
            return
        if head == "F":
            self._emit_log("SYS", f"状态标志：{line[1:]}")
            return
        if head == "Z":
            self._emit_log("SYS", f"时间戳设置：{line[1:]}")
            return
        if head == "S":
            self._emit_log("RX", line, "波特率回显")
            return
        if head in "CO":
            self._emit_log("RX", line, "通道命令回显")
            return
        if head == "\a":                        # BEL = 命令失败
            self._emit_error("适配器返回 BEL：命令执行失败")
            return
        self._emit_log("SYS", f"未知回复：{line!r}")

    def _is_recent_echo(self, frame: CanFrame) -> bool:
        key = (frame.can_id.to_bytes(4, "big")
               + (b"\x01" if frame.extended else b"\x00") + bytes(frame.data))
        now = time.monotonic()
        for k, t in reversed(self._recent_tx):
            if k == key and (now - t) < 1.0:
                return True
        return False

    # ------------------------------------------------------------------ #
    @property
    def description(self) -> str:
        return (f"SLCAN {self.port} @{self.host_baud} "
                f"| CAN {self.can_bitrate // 1000}kbps")

    def read_status_flags(self) -> None:
        """发送 F 命令查询总线状态。"""
        if self._open:
            self._raw_write("F")


__all__ = ["SlcanTransport", "list_serial_ports", "BPS_TO_S_CODE",
           "S_CODE_TO_BPS", "HOST_BAUDS"]
