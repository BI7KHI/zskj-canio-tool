"""
CANIO 数字量输入输出模块 (CAN 版) —— 通讯协议编解码层
================================================================

严格依据《数字量输入输出系列使用手册（CAN 版）V3.0》第 2 章「通讯协议」实现。

帧格式
------
* 标准帧：11 位 ID = [功能码(3bit)][地址(8bit)]
* 扩展帧：29 位 ID = [任意(5bit)][0xAA(8bit)][功能码(8bit)][地址(8bit)]

每个报文固定 8 个数据字节。第 1~6 字节依次表示 1~8 / 9~16 / 17~24 /
25~32 / 33~40 / 41~48 通道，字节内 Bit0 -> Bit7 对应低通道 -> 高通道。
第 7、8 字节保留。

功能码
------
0x01 写继电器状态     0x02 读继电器状态
0x03 读输入口状态     0x04 参数设置
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

DLEN = 8                      # 固定 8 字节数据域
MAX_CHANNELS = 48             # 数据域 6 字节 x 8 位 = 48 路
EXT_MAGIC = 0xAA              # 扩展帧 ID 中的标志字节

ADDR_MIN = 1
ADDR_MAX = 255

#: 功能码
FUNC_WRITE_RELAY = 0x01
FUNC_READ_RELAY = 0x02
FUNC_READ_INPUT = 0x03
FUNC_CONFIG = 0x04

FUNC_NAMES = {
    FUNC_WRITE_RELAY: "写继电器状态",
    FUNC_READ_RELAY: "读继电器状态",
    FUNC_READ_INPUT: "读输入口状态",
    FUNC_CONFIG: "参数设置",
}

#: 功能码 0x04 的参数子命令
CFG_READ_ADDR = 0xA1
CFG_READ_BAUD = 0xA2
CFG_WRITE_ADDR = 0xB1
CFG_WRITE_BAUD = 0xB2
CFG_WRITE_UPLOAD = 0xB3

CFG_NAMES = {
    CFG_READ_ADDR: "读取地址码 (0xA1)",
    CFG_READ_BAUD: "读取波特率码 (0xA2)",
    CFG_WRITE_ADDR: "写入地址码 (0xB1)",
    CFG_WRITE_BAUD: "写入波特率码 (0xB2)",
    CFG_WRITE_UPLOAD: "写入主动上传间隔 (0xB3)",
}

#: 波特率码 -> bps（手册 表2.6）
BAUD_CODE_TO_BPS: dict[int, int] = {
    0x02: 20_000,
    0x03: 50_000,
    0x04: 100_000,
    0x05: 125_000,
    0x06: 200_000,
    0x07: 250_000,
    0x08: 400_000,
    0x09: 500_000,
    0x0A: 800_000,
    0x0B: 1_000_000,
}
BPS_TO_BAUD_CODE: dict[int, int] = {v: k for k, v in BAUD_CODE_TO_BPS.items()}

#: 出厂默认参数（手册 2 章开头 / 3.3.1）
DEFAULT_ADDR = 1
DEFAULT_BPS = 250_000
DEFAULT_UPLOAD_MS = 0


def bps_label(bps: Optional[int]) -> str:
    if not bps:
        return "--"
    if bps >= 1_000_000:
        return "1 Mbps"
    return f"{bps // 1000} kbps"


def fmt_hex_id(can_id: int, extended: bool) -> str:
    """0x101 / 0xAA0101 —— 手册风格的 ID 显示。"""
    width = 8 if extended else 3
    return f"0x{can_id:0{width}X}"


def fmt_data(data: Sequence[int]) -> str:
    return " ".join(f"{b:02X}" for b in data)


# --------------------------------------------------------------------------- #
# 帧对象
# --------------------------------------------------------------------------- #

@dataclass
class CanFrame:
    """一条 CAN 报文（与传输层无关的通用表示）。"""

    can_id: int
    data: bytes = b""
    extended: bool = False
    timestamp: float = 0.0
    #: True = 本机发出，False = 由模块返回
    tx: bool = False
    #: 供界面显示的备注（例如 "写继电器 1-2,45-48"）
    note: str = ""

    @property
    def dlc(self) -> int:
        return len(self.data)

    @property
    def id_text(self) -> str:
        return fmt_hex_id(self.can_id, self.extended)

    @property
    def data_text(self) -> str:
        return fmt_data(self.data)

    def to_slcan(self) -> str:
        """转成 Lawicel/SLCAN ASCII 命令（不含结尾 CR）。"""
        body = "".join(f"{b:02X}" for b in self.data)
        if self.extended:
            return f"T{self.can_id:08X}{body}"
        return f"t{self.can_id:03X}{body}"

    def describe(self) -> str:
        """人类可读的整帧描述。"""
        parsed = parse_id(self.can_id, self.extended)
        return (f"{self.id_text}  [{parsed.func_name}] addr={parsed.addr}  "
                f"data= {self.data_text}")


# --------------------------------------------------------------------------- #
# ID 构造 / 解析
# --------------------------------------------------------------------------- #

@dataclass
class IdParts:
    """一个 CAN ID 的位域拆解结果。"""

    can_id: int
    extended: bool
    func: int
    addr: int
    magic_ok: bool = True
    arbitrary: int = 0          # 扩展帧 bits 28~24（任意值）
    func_known: bool = False

    @property
    def func_name(self) -> str:
        return FUNC_NAMES.get(self.func, f"未知功能码 0x{self.func:02X}")

    def bit_rows(self) -> list[tuple[str, str, str, str]]:
        """返回 (字段, 位范围, 二进制, 数值) 便于在界面上画位域表。"""
        if self.extended:
            bits = f"{self.can_id:029b}"
            rows = [
                ("任意", "28~24", bits[0:5],
                 f"0x{int(bits[0:5], 2):02X}"),
                ("标志 0xAA", "23~16", bits[5:13],
                 f"0x{int(bits[5:13], 2):02X}"),
                ("功能码", "15~8", bits[13:21],
                 f"0x{self.func:02X}  {self.func_name}"),
                ("地址码", "7~0", bits[21:29],
                 f"{self.addr}  (0x{self.addr:02X})"),
            ]
        else:
            bits = f"{self.can_id:011b}"
            rows = [
                ("功能码", "10~8", bits[0:3],
                 f"0x{self.func:X}  {self.func_name}"),
                ("地址码", "7~0", bits[3:11],
                 f"{self.addr}  (0x{self.addr:02X})"),
            ]
        return rows


def make_id(func: int, addr: int, extended: bool = False) -> int:
    """按手册生成 CAN ID。"""
    func &= 0x0F
    addr &= 0xFF
    if extended:
        return ((EXT_MAGIC & 0xFF) << 16) | ((func & 0xFF) << 8) | addr
    return ((func & 0x07) << 8) | addr


def parse_id(can_id: int, extended: bool) -> IdParts:
    """把 CAN ID 拆回功能码 + 地址码。"""
    if extended:
        arbitrary = (can_id >> 24) & 0x1F
        magic = (can_id >> 16) & 0xFF
        func = (can_id >> 8) & 0xFF
        addr = can_id & 0xFF
        return IdParts(can_id=can_id, extended=True, func=func, addr=addr,
                       magic_ok=(magic == EXT_MAGIC), arbitrary=arbitrary,
                       func_known=(func in FUNC_NAMES))
    func = (can_id >> 8) & 0x07
    addr = can_id & 0xFF
    return IdParts(can_id=can_id, extended=False, func=func, addr=addr,
                   func_known=(func in FUNC_NAMES))


# --------------------------------------------------------------------------- #
# 通道 <-> 数据域
# --------------------------------------------------------------------------- #

def channels_to_data(channels: Iterable[int]) -> bytes:
    """把通道号集合打包成 8 字节数据域（Bit=1 表示闭合/触发）。"""
    buf = bytearray(DLEN)
    for ch in channels:
        if 1 <= ch <= MAX_CHANNELS:
            idx = (ch - 1) // 8
            bit = (ch - 1) % 8
            buf[idx] |= 1 << bit
    return bytes(buf)


def data_to_channels(data: Sequence[int]) -> set[int]:
    """从数据域解出所有为 1 的通道号。"""
    out: set[int] = set()
    for idx in range(min(6, len(data))):
        byte = data[idx]
        for bit in range(8):
            if byte >> bit & 1:
                out.add(idx * 8 + bit + 1)
    return out


def channel_bit_table(data: Sequence[int], limit: int = MAX_CHANNELS
                      ) -> list[tuple[int, int, int]]:
    """返回 (通道号, 字节序号 0基, 位序号) -> 值的明细，用于位域展示。"""
    rows = []
    for ch in range(1, limit + 1):
        idx = (ch - 1) // 8
        bit = (ch - 1) % 8
        val = (data[idx] >> bit) & 1 if idx < len(data) else 0
        rows.append((ch, idx, bit, val))
    return rows


def compress_channel_ranges(channels: Iterable[int]) -> str:
    """把通道号压成 '1-2, 45-48' 这样的区间串。"""
    chs = sorted(set(channels))
    if not chs:
        return "无"
    parts, start, prev = [], chs[0], chs[0]
    for c in chs[1:]:
        if c == prev + 1:
            prev = c
            continue
        parts.append(f"{start}" if start == prev else f"{start}-{prev}")
        start = prev = c
    parts.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ", ".join(parts)


def parse_channel_spec(text: str, limit: int = MAX_CHANNELS) -> set[int]:
    """
    解析形如 ``1,2,45-48`` 的通道表达式（也是 compress 的逆运算）。

    容忍空格、中文逗号、分号；超出 1~limit 的通道会被丢弃。
    """
    out: set[int] = set()
    if not text:
        return out
    norm = text.replace("，", ",").replace("；", ",").replace(";", ",")
    norm = norm.replace(" ", "").replace("\t", "")
    for token in norm.split(","):
        if not token:
            continue
        if "-" in token[1:]:                     # 支持 "1-8"
            a, _, b = token.partition("-")
            try:
                lo, hi = int(a), int(b)
            except ValueError:
                continue
            if lo > hi:
                lo, hi = hi, lo
            out.update(range(max(1, lo), min(limit, hi) + 1))
        else:
            try:
                v = int(token)
            except ValueError:
                continue
            if 1 <= v <= limit:
                out.add(v)
    return out


# --------------------------------------------------------------------------- #
# 报文构造
# --------------------------------------------------------------------------- #

def build_frame(func: int, addr: int, data: bytes | bytearray | Sequence[int] = b"",
                extended: bool = False) -> CanFrame:
    """构造任意功能码的报文（数据域自动补齐到 8 字节）。"""
    buf = bytearray(DLEN)
    for i, b in enumerate(list(data)[:DLEN]):
        buf[i] = b & 0xFF
    return CanFrame(can_id=make_id(func, addr, extended), data=bytes(buf),
                    extended=extended)


def build_write_relay(addr: int, channels: Iterable[int], extended: bool = False) -> CanFrame:
    """功能码 0x01 —— 写继电器状态（整帧一次性写入，未列出的通道断开）。"""
    payload = channels_to_data(channels)
    f = build_frame(FUNC_WRITE_RELAY, addr, payload, extended)
    f.note = f"写继电器 {compress_channel_ranges(channels)}"
    return f


def build_read_relay(addr: int, extended: bool = False) -> CanFrame:
    f = build_frame(FUNC_READ_RELAY, addr, b"", extended)
    f.note = "读继电器状态"
    return f


def build_read_input(addr: int, extended: bool = False) -> CanFrame:
    f = build_frame(FUNC_READ_INPUT, addr, b"", extended)
    f.note = "读输入口状态"
    return f


def build_cfg_read_addr(addr: int, extended: bool = False) -> CanFrame:
    f = build_frame(FUNC_CONFIG, addr, bytes([CFG_READ_ADDR]), extended)
    f.note = "读取模块地址"
    return f


def build_cfg_read_baud(addr: int, extended: bool = False) -> CanFrame:
    f = build_frame(FUNC_CONFIG, addr, bytes([CFG_READ_BAUD]), extended)
    f.note = "读取模块波特率"
    return f


def build_cfg_write_addr(addr: int, new_addr: int, extended: bool = False) -> CanFrame:
    f = build_frame(FUNC_CONFIG, addr, bytes([CFG_WRITE_ADDR, new_addr & 0xFF]), extended)
    f.note = f"写入新地址 {new_addr}"
    return f


def build_cfg_write_baud(addr: int, baud_code: int, extended: bool = False) -> CanFrame:
    f = build_frame(FUNC_CONFIG, addr, bytes([CFG_WRITE_BAUD, baud_code & 0xFF]), extended)
    f.note = f"写入波特率码 0x{baud_code:02X}"
    return f


def build_cfg_write_upload(addr: int, interval_ms: int, extended: bool = False) -> CanFrame:
    """
    主动上传间隔：16 位无符号整型，单位 ms，最小 5ms，0 = 不上传。

    手册示例 `0x401 B3 00 0A ...` 的说明为「设置主动上传的间隔时间为 10ms」，
    即第 2 字节 = 高位、第 3 字节 = 低位 —— **大端序**。
    """
    iv = max(0, min(0xFFFF, int(interval_ms)))
    f = build_frame(FUNC_CONFIG, addr,
                    bytes([CFG_WRITE_UPLOAD, (iv >> 8) & 0xFF, iv & 0xFF]), extended)
    f.note = f"写入主动上传间隔 {iv} ms"
    return f


# --------------------------------------------------------------------------- #
# 报文解析
# --------------------------------------------------------------------------- #

@dataclass
class ParsedFrame:
    """对一条报文的完整语义解析结果，供界面展示。"""

    frame: CanFrame
    parts: IdParts
    raw_channels: set[int] = field(default_factory=set)
    #: 功能码 0x04 时生效
    cfg_cmd: Optional[int] = None
    cfg_value: Optional[int] = None
    error: str = ""

    @property
    def is_relay_frame(self) -> bool:
        return self.parts.func in (FUNC_WRITE_RELAY, FUNC_READ_RELAY)

    @property
    def is_input_frame(self) -> bool:
        return self.parts.func == FUNC_READ_INPUT

    def summary(self) -> str:
        if self.error:
            return f"解析失败：{self.error}"
        p = self.parts
        if not p.func_known:
            return f"未知功能码 0x{p.func:02X}"
        if p.func == FUNC_WRITE_RELAY:
            return f"写继电器 -> {compress_channel_ranges(self.raw_channels)} 闭合"
        if p.func == FUNC_READ_RELAY:
            return f"继电器状态 -> {compress_channel_ranges(self.raw_channels)} 闭合"
        if p.func == FUNC_READ_INPUT:
            return f"输入口状态 -> {compress_channel_ranges(self.raw_channels)} 触发"
        # 0x04
        name = CFG_NAMES.get(self.cfg_cmd or -1, f"未知子命令 0x{(self.cfg_cmd or 0):02X}")
        if self.cfg_cmd in (CFG_READ_ADDR, CFG_WRITE_ADDR):
            return f"{name} -> 地址 {self.cfg_value}"
        if self.cfg_cmd in (CFG_READ_BAUD, CFG_WRITE_BAUD):
            bps = BAUD_CODE_TO_BPS.get(self.cfg_value or -1)
            return f"{name} -> 0x{(self.cfg_value or 0):02X} ({bps_label(bps)})"
        if self.cfg_cmd == CFG_WRITE_UPLOAD:
            return f"{name} -> {self.cfg_value} ms"
        return name


def parse_frame(frame: CanFrame) -> ParsedFrame:
    """把一条报文解析成结构化语义。"""
    parts = parse_id(frame.can_id, frame.extended)
    pf = ParsedFrame(frame=frame, parts=parts)

    if frame.extended and not parts.magic_ok:
        pf.error = f"扩展帧标志字节应为 0xAA，实际 0x{(frame.can_id >> 16) & 0xFF:02X}"
        # 仍继续解析，方便调试

    data = frame.data
    if not parts.func_known:
        return pf

    if parts.func in (FUNC_WRITE_RELAY, FUNC_READ_RELAY, FUNC_READ_INPUT):
        pf.raw_channels = data_to_channels(data)
        return pf

    # 功能码 0x04
    if len(data) < 1:
        pf.error = "参数设置帧缺少子命令字节"
        return pf
    pf.cfg_cmd = data[0]
    if pf.cfg_cmd in (CFG_READ_ADDR, CFG_WRITE_ADDR, CFG_READ_BAUD, CFG_WRITE_BAUD):
        pf.cfg_value = data[1] if len(data) > 1 else None
    elif pf.cfg_cmd == CFG_WRITE_UPLOAD:
        if len(data) >= 3:
            pf.cfg_value = (data[1] << 8) | data[2]      # 大端 16 位（见手册示例）
        else:
            pf.error = "主动上传间隔应为 2 字节"
    return pf


def frame_from_slcan(text: str, timestamp: float = 0.0, tx: bool = False
                     ) -> Optional[CanFrame]:
    """解析 SLCAN ASCII 行，例如 't1010300000000F00000' / 'T0000AA0101...'。"""
    s = text.strip()
    if not s:
        return None
    kind, rest = s[0], s[1:]
    if kind in "tT":
        idlen = 8 if kind == "T" else 3
        if len(rest) < idlen:
            return None
        try:
            can_id = int(rest[:idlen], 16)
        except ValueError:
            return None
        hexdata = rest[idlen:]
        # 允许 0 / 2 位对齐的短数据域
        if len(hexdata) % 2:
            hexdata = hexdata[:-1]
        try:
            data = bytes.fromhex(hexdata)
        except ValueError:
            return None
        return CanFrame(can_id=can_id, data=data, extended=(kind == "T"),
                        timestamp=timestamp, tx=tx)
    if kind in "rR":
        # 远程帧，本模块协议不使用，仅记录
        return None
    return None


__all__ = [
    "CanFrame", "IdParts", "ParsedFrame",
    "DLEN", "MAX_CHANNELS", "EXT_MAGIC", "ADDR_MIN", "ADDR_MAX",
    "FUNC_WRITE_RELAY", "FUNC_READ_RELAY", "FUNC_READ_INPUT", "FUNC_CONFIG",
    "FUNC_NAMES", "CFG_NAMES", "CFG_READ_ADDR", "CFG_READ_BAUD",
    "CFG_WRITE_ADDR", "CFG_WRITE_BAUD", "CFG_WRITE_UPLOAD",
    "BAUD_CODE_TO_BPS", "BPS_TO_BAUD_CODE", "DEFAULT_ADDR", "DEFAULT_BPS",
    "DEFAULT_UPLOAD_MS",
    "make_id", "parse_id", "channels_to_data", "data_to_channels",
    "channel_bit_table", "compress_channel_ranges", "parse_channel_spec",
    "build_frame",
    "build_write_relay", "build_read_relay", "build_read_input",
    "build_cfg_read_addr", "build_cfg_read_baud", "build_cfg_write_addr",
    "build_cfg_write_baud", "build_cfg_write_upload",
    "parse_frame", "frame_from_slcan", "bps_label", "fmt_hex_id", "fmt_data",
]
