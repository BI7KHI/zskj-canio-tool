"""
会话层 / 传输层端到端自检（使用内置模拟器，无需硬件）。
运行: python tests/test_session.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canio import protocol as P
from canio.session import DeviceSession
from canio.transport import SimulatorTransport, VirtualModule

FAIL = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAIL.append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}"
          + ("" if ok else f"\n          got ={got!r}\n          want={want!r}"))


def check_true(label, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAIL.append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  {extra}" if extra else ""))


def new_session(num_relays=4, num_inputs=4, addr=1):
    mod = VirtualModule(addr=addr, num_relays=num_relays, num_inputs=num_inputs,
                        latency=0.002)
    tr = SimulatorTransport([mod], random_inputs=False)
    tr.open()
    s = DeviceSession(tr, addr=addr)
    return s, tr, mod


print("=" * 74)
print("1) 标准帧：写继电器 / 读继电器 / 读输入")
print("=" * 74)
s, tr, mod = new_session()
try:
    check_true("写入继电器 1,3 成功", s.write_relays({1, 3}))
    check("模块内部继电器状态 = {1,3}", sorted(mod.relays), [1, 3])
    check("读回继电器状态 = {1,3}", sorted(s.read_relays() or []), [1, 3])

    # 4 路模块：写入超范围通道 (7) 应被忽略
    s.write_relays({2, 7})
    check("超范围通道 7 被忽略 = {2}", sorted(mod.relays), [2])

    # 全部断开
    s.write_relays(set())
    check("全部断开", sorted(s.read_relays() or []), [])

    # 单路操作（读-改-写）
    s.write_relays({1, 2})
    s.write_relay(3, True)
    check("单路闭合后 = {1,2,3}", sorted(s.read_relays() or []), [1, 2, 3])
    s.write_relay(2, False)
    check("单路断开后 = {1,3}", sorted(s.read_relays() or []), [1, 3])

    # 输入状态
    mod.inputs = {2, 4}
    check("读输入 = {2,4}", sorted(s.read_inputs() or []), [2, 4])
finally:
    s.close()

print()
print("=" * 74)
print("2) 参数设置：地址 / 波特率 / 主动上传间隔")
print("=" * 74)
s, tr, mod = new_session()
try:
    check("读地址 = 1", s.read_address(), 1)
    check("读波特率码 = 0x07 (250kbps)", s.read_baud(), 0x07)

    check_true("写波特率码 0x09 (500kbps)", s.write_baud(0x09))
    # 手册 3.4：波特率需断电重启才生效 —— 此处应只进入「待生效」
    check("模块波特率码暂未变化", mod.baud_code, 0x07)
    check("模块待生效波特率码 = 0x09", mod.pending_baud_code, 0x09)
    check("会话待生效波特率码 = 0x09", s.state.pending_baud_code, 0x09)
    check("回读波特率码仍为 0x07", s.read_baud(), 0x07)

    check_true("写主动上传间隔 10ms", s.write_upload_interval(10))
    # 主动上传间隔「参数设置后立即生效」（手册 2.3.3）
    check("模块 upload_ms = 10 (立即生效)", mod.upload_ms, 10)

    check_true("写地址 = 8", s.write_address(8))
    check("模块地址暂未变化 = 1", mod.addr, 1)
    check("模块待生效地址 = 8", mod.pending_addr, 8)
    check("会话地址未被误改 = 1", s.state.addr, 1)
    check("回读地址仍为 1", s.read_address(), 1)

    # 断电重启 -> 新地址/波特率生效
    tr.power_cycle()
    check("重启后模块地址 = 8", mod.addr, 8)
    check("重启后模块波特率码 = 0x09", mod.baud_code, 0x09)
    s.state.addr = 8
    check("按新地址读波特率 = 0x09", s.read_baud(), 0x09)
finally:
    s.close()

print()
print("=" * 74)
print("3) 扩展帧模式 (0xAA0101)")
print("=" * 74)
s, tr, mod = new_session()
try:
    s.apply_extended(True)
    check_true("扩展帧写继电器成功", s.write_relays({1, 4}))
    check("模块继电器 = {1,4}", sorted(mod.relays), [1, 4])
    check("扩展帧读回 = {1,4}", sorted(s.read_relays() or []), [1, 4])

    seen = []
    s.set_handlers(on_frame=lambda f, p: seen.append(f))
    s.read_relays()
    time.sleep(0.05)
    check_true("总线上的帧确为扩展帧",
               seen and all(f.extended for f in seen),
               f"ids={[hex(f.can_id) for f in seen]}")
    check_true("扩展帧 ID 形如 0xAA02xx",
               all((f.can_id >> 16) & 0xFF == P.EXT_MAGIC for f in seen))
finally:
    s.close()

print()
print("=" * 74)
print("4) 多路规格：16 / 32 / 48 路继电器")
print("=" * 74)
for n in (16, 32, 48):
    s, tr, mod = new_session(num_relays=n, num_inputs=n)
    try:
        want = set(range(1, n + 1))
        s.write_relays(want)
        got = s.read_relays() or set()
        check(f"{n} 路全闭合往返一致", got, want)
        data = P.channels_to_data(want)
        check(f"{n} 路数据域前 {n // 8} 字节全 FF",
              data[:n // 8], b"\xff" * (n // 8))
    finally:
        s.close()

print()
print("=" * 74)
print("5) 地址扫描（总线搜索）")
print("=" * 74)
mods = [VirtualModule(addr=a, num_relays=4, num_inputs=4, latency=0.001)
        for a in (1, 5, 12)]
tr = SimulatorTransport(mods, random_inputs=False)
tr.open()
s = DeviceSession(tr, addr=1)
try:
    found = s.scan_addresses(1, 20, timeout=0.08)
    check("扫描到 {1,5,12}", sorted(found), [1, 5, 12])
finally:
    s.close()

print()
print("=" * 74)
print("6) 周期轮询 与 状态回调")
print("=" * 74)
s, tr, mod = new_session()
try:
    events = {"inputs": [], "relays": []}
    s.set_handlers(on_state=lambda ch: events["inputs"].append(set(ch["inputs"]))
                   if "inputs" in ch else None)
    mod.inputs = {1}
    s.start_polling(interval_ms=30)
    time.sleep(0.25)
    mod.inputs = {1, 3}
    time.sleep(0.30)
    s.stop_polling()
    check_true("轮询期间收到了输入状态更新",
               any(v == {1, 3} for v in events["inputs"]),
               f"observed={events['inputs']}")
    check_true("统计里有收包", s.stats.rx > 0,
               f"tx={s.stats.tx} rx={s.stats.rx}")
finally:
    s.close()

print()
print("=" * 74)
print("7) 超时处理（不存在的地址）")
print("=" * 74)
s, tr, mod = new_session(addr=1)
try:
    s.state.addr = 99
    t0 = time.monotonic()
    r = s.read_relays(timeout=0.15)
    dt = time.monotonic() - t0
    check("不存在的地址返回 None", r, None)
    check_true("超时时间合理 (0.1~0.6s)", 0.10 <= dt <= 0.60, f"{dt:.3f}s")
    check_true("超时计数递增", s.stats.timeouts >= 1)
finally:
    s.close()

print()
print("=" * 74)
print("8) 主动上传（模块周期推送输入状态）")
print("=" * 74)
s, tr, mod = new_session()
try:
    mod.inputs = {2}
    s.write_upload_interval(20)
    got = []
    s.set_handlers(on_frame=lambda f, p: got.append(p) if p.is_input_frame else None)
    time.sleep(0.35)
    mod.upload_ms = 0
    check_true("收到模块主动上传的输入帧", len(got) >= 2, f"count={len(got)}")
finally:
    s.close()

print()
print("=" * 74)
if FAIL:
    print(f"结果: {len(FAIL)} 项失败 -> {FAIL}")
    sys.exit(1)
print("结果: 全部通过 ✔  会话层 / 传输层 / 模拟器 端到端正常")
