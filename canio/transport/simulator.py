"""
内置模拟器传输层
================================================================

在没有真实硬件的情况下，用软件完整仿真一台（或多台）中盛 CANIO
数字量输入输出模块，实现与真机一致的报文交互：

* 功能码 0x01 写继电器  -> 回显同样的数据域
* 功能码 0x02 读继电器  -> 返回当前继电器状态
* 功能码 0x03 读输入口  -> 返回当前输入状态
* 功能码 0x04 参数设置  -> 读/写 地址、波特率、主动上传间隔
* 支持标准帧与扩展帧；地址不匹配时静默丢弃（与总线行为一致）
* 可注入输入信号、可产生随机输入抖动
"""
from __future__ import annotations

import queue
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from ..protocol import (CFG_READ_ADDR, CFG_READ_BAUD, CFG_WRITE_ADDR,
                        CFG_WRITE_BAUD, CFG_WRITE_UPLOAD, CanFrame,
                        FUNC_CONFIG, FUNC_READ_INPUT, FUNC_READ_RELAY,
                        FUNC_WRITE_RELAY, MAX_CHANNELS,
                        build_frame, channels_to_data, data_to_channels,
                        parse_id)
from .base import CanTransport, TransportError


@dataclass
class VirtualModule:
    """一台被仿真的 CANIO 模块。"""

    addr: int = 1
    num_relays: int = 4
    num_inputs: int = 4
    baud_code: int = 0x07
    upload_ms: int = 0

    #: 地址 / 波特率修改后「断电重启」才生效（手册 3.4），此前先缓存为待生效值
    pending_addr: Optional[int] = None
    pending_baud_code: Optional[int] = None

    relays: set[int] = field(default_factory=set)
    inputs: set[int] = field(default_factory=set)
    #: 总线仿真：响应延迟（秒）
    latency: float = 0.004

    def in_range_relays(self, ch: int) -> bool:
        return 1 <= ch <= max(1, min(MAX_CHANNELS, self.num_relays))

    def power_cycle(self) -> None:
        """模拟「断电 5 秒后重新上电」，令地址 / 波特率修改真正生效。"""
        if self.pending_addr is not None:
            self.addr = self.pending_addr
            self.pending_addr = None
        if self.pending_baud_code is not None:
            self.baud_code = self.pending_baud_code
            self.pending_baud_code = None

    # -- 报文处理 ---------------------------------------------------------- #
    def handle(self, frame: CanFrame) -> Optional[CanFrame]:
        """返回回复帧；None 表示不应答。"""
        parts = parse_id(frame.can_id, frame.extended)
        if parts.addr != self.addr:
            return None                        # 总线上不理会其他地址
        if frame.extended and not parts.magic_ok:
            return None

        func = parts.func
        ext = frame.extended

        if func == FUNC_WRITE_RELAY:
            want = data_to_channels(frame.data)
            self.relays = {c for c in want if self.in_range_relays(c)}
            # 手册示例：写继电器后模块原样返回数据域
            return build_frame(FUNC_WRITE_RELAY, self.addr,
                               channels_to_data(self.relays), ext)

        if func == FUNC_READ_RELAY:
            return build_frame(FUNC_READ_RELAY, self.addr,
                               channels_to_data(self.relays), ext)

        if func == FUNC_READ_INPUT:
            return build_frame(FUNC_READ_INPUT, self.addr,
                               channels_to_data(self.inputs), ext)

        if func == FUNC_CONFIG:
            return self._handle_config(frame, ext)

        return None

    def _handle_config(self, frame: CanFrame, ext: bool) -> Optional[CanFrame]:
        data = list(frame.data) + [0] * 8
        cmd = data[0]
        if cmd == CFG_READ_ADDR:
            return build_frame(FUNC_CONFIG, self.addr,
                               bytes([CFG_READ_ADDR, self.addr]), ext)
        if cmd == CFG_READ_BAUD:
            return build_frame(FUNC_CONFIG, self.addr,
                               bytes([CFG_READ_BAUD, self.baud_code]), ext)
        if cmd == CFG_WRITE_ADDR:
            new = data[1]
            if 1 <= new <= 255:
                self.pending_addr = new           # 断电重启后才生效
            # 手册示例：模块用「原地址」回复（0x401 B1 08）
            return build_frame(FUNC_CONFIG, self.addr,
                               bytes([CFG_WRITE_ADDR, new]), ext)
        if cmd == CFG_WRITE_BAUD:
            code = data[1]
            self.pending_baud_code = code         # 断电重启后才生效
            return build_frame(FUNC_CONFIG, self.addr,
                               bytes([CFG_WRITE_BAUD, code]), ext)
        if cmd == CFG_WRITE_UPLOAD:
            iv = (data[1] << 8) | data[2]       # 大端
            self.upload_ms = iv
            return build_frame(FUNC_CONFIG, self.addr,
                               bytes([CFG_WRITE_UPLOAD, data[1], data[2]]), ext)
        return None

    def upload_frame(self) -> CanFrame:
        """主动上传帧（按手册约定上传输入口状态）。"""
        return build_frame(FUNC_READ_INPUT, self.addr,
                           channels_to_data(self.inputs), False)


class SimulatorTransport(CanTransport):
    """仿真传输：可驱动 1~N 台虚拟模块。"""

    display_name = "模拟器"

    def __init__(self, modules: Optional[list[VirtualModule]] = None,
                 random_inputs: bool = False,
                 input_flip_chance: float = 0.015) -> None:
        super().__init__()
        self.modules: list[VirtualModule] = modules or [VirtualModule()]
        #: 默认关闭随机抖动 —— 调试时应只反映用户真正注入的信号
        self.random_inputs = bool(random_inputs)
        self.input_flip_chance = float(input_flip_chance)

        self._txq: "queue.Queue[CanFrame]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_upload: dict[int, float] = {}
        self._rng = random.Random(20260101)

    # ------------------------------------------------------------------ #
    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def supported_bitrates(cls) -> list[int]:
        return [20_000, 50_000, 100_000, 125_000, 200_000, 250_000,
                400_000, 500_000, 800_000, 1_000_000]

    # ------------------------------------------------------------------ #
    def open(self) -> None:
        if self._open:
            return
        self._stop.clear()
        self._open = True
        self._worker = threading.Thread(target=self._loop, name="sim-can",
                                        daemon=True)
        self._worker.start()
        names = ", ".join(
            f"#{m.addr}({m.num_relays}路输出/{m.num_inputs}路输入)" for m in self.modules)
        self._emit_log("SYS", f"模拟器已启动：{names}")

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        self._stop.set()
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=1.0)
        self._worker = None

    # ------------------------------------------------------------------ #
    def send(self, frame: CanFrame) -> None:
        if not self._open:
            raise TransportError("模拟器未打开")
        self._emit_log("TX", frame.to_slcan())
        try:
            self._txq.put_nowait(frame)
        except queue.Full:                      # pragma: no cover
            pass

    # ------------------------------------------------------------------ #
    def _loop(self) -> None:
        next_upload = time.monotonic() + 0.1
        while not self._stop.is_set():
            # 1) 处理待发送帧
            try:
                frame = self._txq.get(timeout=0.005)
            except queue.Empty:
                frame = None
            if frame is not None:
                for mod in list(self.modules):
                    try:
                        reply = mod.handle(frame)
                    except Exception as exc:        # pragma: no cover
                        self._emit_error(f"模拟器处理异常：{exc}")
                        continue
                    if reply is not None:
                        time.sleep(mod.latency)
                        self._deliver(reply)
                        break                       # 一台模块应答即可

            # 2) 随机输入抖动
            now = time.monotonic()
            if self.random_inputs and (now - next_upload) > 0.05:
                next_upload = now
                for mod in self.modules:
                    self._jit_inputs(mod)

            # 3) 主动上传
            for mod in self.modules:
                if mod.upload_ms > 0:
                    last = self._last_upload.get(id(mod), 0.0)
                    if (now - last) * 1000.0 >= max(5, mod.upload_ms):
                        self._last_upload[id(mod)] = now
                        self._deliver(mod.upload_frame())

    def _jit_inputs(self, mod: VirtualModule) -> None:
        if mod.num_inputs <= 0:
            return
        if self._rng.random() < self.input_flip_chance:
            ch = self._rng.randint(1, mod.num_inputs)
            if ch in mod.inputs:
                mod.inputs.discard(ch)
            else:
                mod.inputs.add(ch)

    def _deliver(self, frame: CanFrame) -> None:
        self._emit_log("RX", frame.to_slcan())
        self._emit_frame(frame)

    # ------------------------------------------------------------------ #
    # 供界面使用的仿真控制
    # ------------------------------------------------------------------ #
    def set_input(self, channel: int, on: bool, addr: int = 1) -> None:
        for mod in self.modules:
            if mod.addr == addr:
                if on:
                    mod.inputs.add(channel)
                else:
                    mod.inputs.discard(channel)
                return
        raise ValueError(f"模拟器中没有地址为 {addr} 的模块")

    def module_for(self, addr: int) -> Optional[VirtualModule]:
        return next((m for m in self.modules if m.addr == addr), None)

    def power_cycle(self, addr: Optional[int] = None) -> None:
        """模拟断电重启，令待生效的地址 / 波特率真正生效。"""
        for mod in self.modules:
            if addr is None or mod.addr == addr:
                mod.power_cycle()
        self._emit_log("SYS", "模拟器：模块已断电重启，新地址/波特率生效")

    def reconfigure(self, addr: int, num_relays: int, num_inputs: int) -> None:
        """按界面上的机型设置调整虚拟模块规格。"""
        mod = self.module_for(addr)
        if mod is None:
            self.modules.append(VirtualModule(addr=addr, num_relays=num_relays,
                                              num_inputs=num_inputs))
        else:
            mod.num_relays = num_relays
            mod.num_inputs = num_inputs
            mod.relays = {c for c in mod.relays if c <= num_relays}
            mod.inputs = {c for c in mod.inputs if c <= num_inputs}

    @property
    def description(self) -> str:
        return f"模拟器 ({len(self.modules)} 台虚拟模块)"

