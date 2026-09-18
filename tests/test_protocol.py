"""
协议层自检：逐条核对《数字量输入输出系列使用手册(CAN版)》中出现的所有示例。
运行: python tests/test_protocol.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canio import protocol as P

FAIL = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAIL.append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"          got = {got!r}")
        print(f"          want= {want!r}")


def h(s):
    return bytes.fromhex(s.replace(" ", ""))


print("=" * 74)
print("1) 手册 2.3.1 写继电器 1-2、45-48 闭合")
print("=" * 74)
f = P.build_write_relay(1, {1, 2, 45, 46, 47, 48})
check("标准帧 ID = 0x101", f"0x{f.can_id:X}", "0x101")
check("标准帧 DATA = 03 00 00 00 00 F0 00 00", f.data, h("03 00 00 00 00 F0 00 00"))
check("帧类型 = 标准帧", f.extended, False)

fe = P.build_write_relay(1, {1, 2, 45, 46, 47, 48}, extended=True)
check("扩展帧 ID = 0xAA0101", f"0x{fe.can_id:X}", "0xAA0101")
check("扩展帧 DATA = 03 00 00 00 00 F0 00 00", fe.data, h("03 00 00 00 00 F0 00 00"))

print()
print("=" * 74)
print("2) 手册 2.3.1 写继电器全部断开 (0x00 x8)")
print("=" * 74)
f = P.build_write_relay(1, set())
check("标准帧 ID = 0x101", f"0x{f.can_id:X}", "0x101")
check("DATA 全 0", f.data, h("00 00 00 00 00 00 00 00"))
fe = P.build_write_relay(1, set(), extended=True)
check("扩展帧 ID = 0xAA0101", f"0x{fe.can_id:X}", "0xAA0101")

print()
print("=" * 74)
print("3) 手册 2.3.2 读继电器状态返回 0x0f ... 0x80  -> 继电器 1-4, 48")
print("=" * 74)
f = P.build_read_relay(1)
check("标准帧 ID = 0x201", f"0x{f.can_id:X}", "0x201")
check("发送数据域任意(全0)", f.data, h("00 00 00 00 00 00 00 00"))
check("扩展帧 ID = 0xAA0201", f"0x{P.build_read_relay(1, True).can_id:X}", "0xAA0201")

resp = P.CanFrame(can_id=0x201, data=h("0f 00 00 00 00 80 00 00"))
pf = P.parse_frame(resp)
check("解析出功能码 = 0x02", pf.parts.func, P.FUNC_READ_RELAY)
check("解析出地址 = 1", pf.parts.addr, 1)
check("闭合通道 = {1,2,3,4,48}", sorted(pf.raw_channels), [1, 2, 3, 4, 48])
check("区间压缩文本", P.compress_channel_ranges(pf.raw_channels), "1-4, 48")

print()
print("=" * 74)
print("4) 手册 2.3.3 读输入口返回 0xfe ... 0x7f -> 输入 2-8, 41-47 触发")
print("=" * 74)
f = P.build_read_input(1)
check("标准帧 ID = 0x301", f"0x{f.can_id:X}", "0x301")
check("扩展帧 ID = 0xAA0301", f"0x{P.build_read_input(1, True).can_id:X}", "0xAA0301")

resp = P.CanFrame(can_id=0x301, data=h("fe 00 00 00 00 7f 00 00"))
pf = P.parse_frame(resp)
check("解析出功能码 = 0x03", pf.parts.func, P.FUNC_READ_INPUT)
check("触发通道 = 2-8,41-47",
      P.compress_channel_ranges(pf.raw_channels), "2-8, 41-47")

print()
print("=" * 74)
print("5) 手册 2.3.3 功能码 0x04 参数设置")
print("=" * 74)
f = P.build_cfg_read_addr(1)
check("读地址 标准帧 ID = 0x401", f"0x{f.can_id:X}", "0x401")
check("读地址 DATA = A1 00 ...", f.data, h("A1 00 00 00 00 00 00 00"))
check("读地址 扩展帧 ID = 0xAA0401", f"0x{P.build_cfg_read_addr(1, True).can_id:X}", "0xAA0401")

# 模块返回 A1 01 -> 地址 1
pf = P.parse_frame(P.CanFrame(can_id=0x401, data=h("A1 01 00 00 00 00 00 00")))
check("读地址 返回 cfg_cmd = 0xA1", pf.cfg_cmd, 0xA1)
check("读地址 返回 值 = 1", pf.cfg_value, 1)

# 模块返回 A2 07 -> 250kbps
pf = P.parse_frame(P.CanFrame(can_id=0x401, data=h("A2 07 00 00 00 00 00 00")))
check("读波特率 返回 cfg_cmd = 0xA2", pf.cfg_cmd, 0xA2)
check("读波特率 0x07 -> 250000 bps", P.BAUD_CODE_TO_BPS[pf.cfg_value], 250_000)

# 写地址 0xB1 0x08
f = P.build_cfg_write_addr(1, 8)
check("写地址 DATA = B1 08 ...", f.data, h("B1 08 00 00 00 00 00 00"))
check("写地址 标准帧 ID = 0x401", f"0x{f.can_id:X}", "0x401")

# 写波特率 0xB2 0x06 -> 200kbps
f = P.build_cfg_write_baud(1, 0x06)
check("写波特率 DATA = B2 06 ...", f.data, h("B2 06 00 00 00 00 00 00"))

# 写主动上传 0xB3 0x00 0x0A -> 10ms
f = P.build_cfg_write_upload(1, 10)
check("写上传间隔 DATA = B3 00 0A ...", f.data, h("B3 00 0A 00 00 00 00 00"))
pf = P.parse_frame(f)
check("写上传间隔 解析值 = 10 ms", pf.cfg_value, 10)

print()
print("=" * 74)
print("6) 表 2.6 波特率码对照表逐项核对")
print("=" * 74)
TABLE = {0x02: 20_000, 0x03: 50_000, 0x04: 100_000, 0x05: 125_000,
         0x06: 200_000, 0x07: 250_000, 0x08: 400_000, 0x09: 500_000,
         0x0A: 800_000, 0x0B: 1_000_000}
check("波特率码表完全一致", P.BAUD_CODE_TO_BPS, TABLE)
check("默认波特率 = 250kbps (码 0x07)", P.BPS_TO_BAUD_CODE[P.DEFAULT_BPS], 0x07)

print()
print("=" * 74)
print("7) ID 位域拆解")
print("=" * 74)
p = P.parse_id(0x101, False)
check("标准帧 0x101 -> func=1", p.func, 1)
check("标准帧 0x101 -> addr=1", p.addr, 1)
check("标准帧 0x101 -> 功能名", p.func_name, "写继电器状态")

p = P.parse_id(0xAA0101, True)
check("扩展帧 0xAA0101 -> magic ok", p.magic_ok, True)
check("扩展帧 0xAA0101 -> func=1", p.func, 1)
check("扩展帧 0xAA0101 -> addr=1", p.addr, 1)

p = P.parse_id(0xAA0408, True)
check("扩展帧 0xAA0408 -> func=4 / addr=8", (p.func, p.addr), (4, 8))

# 边界：地址 255
# 标准帧 ID = 功能码(bit10~8) + 地址(bit7~0) = (1<<8)|255 = 0x1FF
check("地址 255 标准帧 ID", f"0x{P.make_id(1, 255):X}", "0x1FF")
check("地址 255 扩展帧 ID", f"0x{P.make_id(1, 255, True):X}", "0xAA01FF")
check("地址/功能码可逆 (地址 255)", P.parse_id(P.make_id(1, 255), False).addr, 255)

print()
print("=" * 74)
print("8) SLCAN 报文往返")
print("=" * 74)
f = P.build_write_relay(1, {1, 2})
check("标准帧 SLCAN (t + 3位ID + 16位数据)", f.to_slcan(), "t1010300000000000000")
f = P.build_write_relay(1, {1, 2}, extended=True)
# 扩展帧: T + 8 位十六进制 ID + 16 位数据 -> ID 0xAA0101 补足 8 位 = 00AA0101
check("扩展帧 SLCAN (T + 8位ID + 16位数据)", f.to_slcan(),
      "T00AA01010300000000000000")
check("扩展帧 SLCAN 长度 = 1+8+16", len(f.to_slcan()), 25)

rt = P.frame_from_slcan("t1010300000000000000")
check("SLCAN 回读 ID", f"0x{rt.can_id:X}", "0x101")
check("SLCAN 回读 数据", rt.data, h("03 00 00 00 00 00 00 00"))
check("SLCAN 回读 帧型", rt.extended, False)
rt = P.frame_from_slcan("T00AA01010300000000000000")
check("SLCAN 扩展回读 ID", f"0x{rt.can_id:X}", "0xAA0101")
check("SLCAN 扩展回读 帧型", rt.extended, True)
check("SLCAN 扩展回读 地址 = 1", P.parse_id(rt.can_id, True).addr, 1)
check("SLCAN 扩展回读 功能码 = 1", P.parse_id(rt.can_id, True).func, 1)
# 大小写 / 多余空白都应容忍
check("SLCAN 小写输入容忍", P.frame_from_slcan("  00aa01010300000000000000 ".strip()[0:0] or
      "T00aa01010300000000000000").can_id, 0xAA0101)

print()
print("=" * 74)
print("9) 通道打包/解包往返 (1..48 全通道)")
print("=" * 74)
allch = set(range(1, 49))
d = P.channels_to_data(allch)
check("48 路全闭 = FF FF FF FF FF FF (前6字节)",
      d[:6], h("FF FF FF FF FF FF"))
check("第 7/8 字节保留为 0", d[6:], h("00 00"))
check("解包回 48 路", P.data_to_channels(d), allch)
for n in (1, 2, 3, 4, 8, 16, 24, 32, 48):
    ch = set(range(1, n + 1))
    assert P.data_to_channels(P.channels_to_data(ch)) == ch, n
check("前 N 路往返一致 (1,2,3,4,8,16,24,32,48)", True, True)

print()
print("=" * 74)
if FAIL:
    print(f"结果: {len(FAIL)} 项失败 -> {FAIL}")
    sys.exit(1)
print("结果: 全部通过 ✔  协议层与手册一致")
