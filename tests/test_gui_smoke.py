"""
GUI 端到端冒烟测试：用真实界面 + 内置模拟器跑通全流程，并输出截图。
运行: python tests/test_gui_smoke.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QPA_PLATFORM", "offscreen")
os.environ.setdefault("CANIO_NO_DIALOG", "1")

from PySide6.QtCore import Qt, QTimer            # noqa: E402
from PySide6.QtWidgets import QApplication       # noqa: E402

from ui.theme import apply_theme                 # noqa: E402
from ui.main_window import MainWindow            # noqa: E402
from canio import protocol as P                  # noqa: E402

FAIL = []
SHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "docs", "screenshots")
os.makedirs(SHOT_DIR, exist_ok=True)


def check(label, got, want):
    ok = got == want
    if not ok:
        FAIL.append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}"
          + ("" if ok else f"   got={got!r} want={want!r}"))


def check_true(label, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAIL.append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  {extra}" if extra else ""))


def pump(app, ms=250):
    """在等待期间持续处理事件。"""
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def shoot(win, name):
    path = os.path.join(SHOT_DIR, name)
    win.grab().save(path)
    print(f"      截图 -> {os.path.relpath(path)}")
    return path


app = QApplication(sys.argv)
apply_theme(app)
win = MainWindow()
win.resize(1480, 940)
win.show()
pump(app, 300)

print("=" * 74)
print("1) 选择一个串口 -> 断开态界面")
print("=" * 74)
check("标签页数量 = 5", win.tabs.count(), 5)
check("初始未连接", win.ctl.connected, False)
shoot(win, "01_未连接.png")

print()
print("=" * 74)
print("2) 选择模拟器并点击「连接」")
print("=" * 74)
idx = win.conn_panel.transport_combo.findText("模拟器 (无硬件)")
check_true("传输方式里有模拟器", idx >= 0)
win.conn_panel.transport_combo.setCurrentIndex(idx)
win.conn_panel.addr_spin.setValue(1)
check("模块地址 = 1", win.conn_panel.addr, 1)
check("CAN 波特率 = 250kbps", win.conn_panel.bitrate, 250_000)
check("帧格式 = 标准帧", win.conn_panel.frame_extended, False)

win.conn_panel.connect_btn.click()
pump(app, 1200)
check("已连接", win.ctl.connected, True)
check_true("状态药丸显示已连接", "已连接" in win.pill.text(), win.pill.text())
check_true("链路描述含模拟器", "模拟器" in win.link_lbl.text(), win.link_lbl.text())
check_true("模块处于在线状态", win.ctl.session.state.online, True)
shoot(win, "02_已连接.png")

print()
print("=" * 74)
print("3) 继电器控制：点击通道磁贴")
print("=" * 74)
mod = win.ctl.transport.module_for(1)
check_true("模拟器里存在地址 1 的模块", mod is not None)
check("模块继电器路数 = 4", mod.num_relays, 4)
check("初始全断开", sorted(mod.relays), [])

tiles = win.relay_panel._tiles
check("界面生成 4 个通道磁贴", len(tiles), 4)
tiles[1].click()
pump(app, 700)
check("Y1 吸合后模块状态 = {1}", sorted(mod.relays), [1])
check("Y1 磁贴为选中态", tiles[1].isChecked(), True)

tiles[3].click()
pump(app, 700)
check("Y1+Y3 吸合", sorted(mod.relays), [1, 3])
check("汇总文本正确", win.relay_panel.summary.text(), "闭合 2 / 共 4")

tiles[1].click()
pump(app, 700)
check("Y1 断开后 = {3}", sorted(mod.relays), [3])
shoot(win, "03_继电器控制.png")

print()
print("=" * 74)
print("4) 批量按钮：全部闭合 / 状态取反 / 全部断开")
print("=" * 74)
win.relay_panel.all_on_btn.click()
pump(app, 700)
check("全部闭合 -> {1,2,3,4}", sorted(mod.relays), [1, 2, 3, 4])
win.relay_panel.invert_btn.click()
pump(app, 700)
check("取反 -> 全断开", sorted(mod.relays), [])
win.relay_panel.all_on_btn.click()
pump(app, 700)
check("再全部闭合", sorted(mod.relays), [1, 2, 3, 4])
win.relay_panel.all_off_btn.click()
pump(app, 700)
check("全部断开", sorted(mod.relays), [])

print()
print("=" * 74)
print("5) 输入监视：注入信号后界面刷新")
print("=" * 74)
win.ctl.transport.random_inputs = False      # 测试需确定性，关闭随机抖动
win.ctl.transport.set_input(2, True, addr=1)
win.ctl.transport.set_input(4, True, addr=1)
win.ctl.read_inputs()
pump(app, 700)
inp = win.input_panel._tiles
check("输入 X2 显示为触发", inp[2].active, True)
check("输入 X4 显示为触发", inp[4].active, True)
check("输入 X1 未触发", inp[1].active, False)
check("输入汇总文本", win.input_panel.summary.text(), "触发 2 / 共 4")
win.ctl.transport.set_input(2, False, addr=1)
win.ctl.read_inputs()
pump(app, 700)
check("X2 取消触发", inp[2].active, False)
shoot(win, "04_输入监视.png")

print()
print("=" * 74)
print("6) 原始帧监视：报文被抓取")
print("=" * 74)
rows = win.frame_panel.table.rowCount()
check_true("报文表已有记录", rows > 0, f"rows={rows}")
# 至少包含一条 0x201(读继电器) 与 0x301(读输入)
ids = set()
for r in range(rows):
    it = win.frame_panel.table.item(r, 3)
    if it:
        ids.add(it.text())
check_true("出现读继电器帧 0x201", "0x201" in ids, f"ids={sorted(ids)[:8]}")
check_true("出现读输入帧 0x301", "0x301" in ids)
check_true("出现写继电器帧 0x101", "0x101" in ids)
win.tabs.setCurrentWidget(win.frame_panel)
pump(app, 300)
shoot(win, "05_原始帧监视.png")

print()
print("=" * 74)
print("7) 帧构造 / 地址解析")
print("=" * 74)
ap = win.analyzer_panel
ap.func_combo.setCurrentIndex(0)
ap.ch_spec.setText("1,2,45-48")
ap._refresh_preview()
pump(app, 150)
check("构造出的 ID = 0x101", ap._last_built.id_text, "0x101")
check("构造出的数据域 = 手册示例",
      ap._last_built.data_text, "03 00 00 00 00 F0 00 00")
ap.r_ext.setCurrentIndex(0)
ap.r_id.setText("0x101")
ap.r_data.setText("03 00 00 00 00 F0 00 00")
ap._do_resolve()
pump(app, 150)
check("解析结论", ap.r_summary.text(), "写继电器 -> 1-2, 45-48 闭合")
check("解析出通道", ap.r_ch.text(), "闭合通道 : 1-2, 45-48")
check("位域表行数(标准帧 2 行)", ap.bit_table.rowCount(), 2)

ap.r_ext.setCurrentIndex(1)
ap.r_id.setText("0xAA0101")
ap._do_resolve()
pump(app, 150)
check("扩展帧位域表行数 = 4", ap.bit_table.rowCount(), 4)
check_true("扩展帧标志校验通过", "0xAA 校验通过" in ap.r_magic.text(),
           ap.r_magic.text())
win.tabs.setCurrentWidget(ap)
pump(app, 300)
shoot(win, "06_帧构造与地址解析.png")

print()
print("=" * 74)
print("8) 模块参数：读取 / 改动需重启生效")
print("=" * 74)
cp = win.config_panel
win.tabs.setCurrentWidget(cp)
pump(app, 200)
check_true("界面显示地址 = 1", cp.v_addr.text().startswith("1"), cp.v_addr.text())
check("界面显示波特率 = 250 kbps", cp.v_bps.text(), "250 kbps")

cp.baud_combo.setCurrentIndex(cp.baud_combo.findData(0x09))
cp.baud_btn.click()
pump(app, 800)
check("模块波特率暂未变化", mod.baud_code, 0x07)
check("出现「需断电重启」提示", cp.baud_note.isVisible(), True)

cp.addr_spin.setValue(8)
cp.addr_btn.click()
pump(app, 800)
check("模块地址暂未变化 = 1", mod.addr, 1)
check("待生效地址 = 8", mod.pending_addr, 8)
shoot(win, "07_模块参数.png")

cp.power_btn.click()
pump(app, 800)
check("模拟断电重启后地址 = 8", mod.addr, 8)
check("模拟断电重启后波特率码 = 0x09", mod.baud_code, 0x09)

print()
print("=" * 74)
print("9) 扩展帧模式下再走一轮读写")
print("=" * 74)
win.ctl.session.state.addr = 8
win.conn_panel.addr_spin.blockSignals(True)
win.conn_panel.addr_spin.setValue(8)
win.conn_panel.addr_spin.blockSignals(False)
win.conn_panel.ext_radio.setChecked(True)
pump(app, 200)
win.relay_panel._apply({1, 2})
pump(app, 800)
check("扩展帧写继电器成功 = {1,2}", sorted(mod.relays), [1, 2])
check_true("会话处于扩展帧模式", win.ctl.session.extended, True)

print()
print("=" * 74)
print("10) 断开连接")
print("=" * 74)
win.conn_panel.disconnect_btn.click()
pump(app, 600)
check("已断开", win.ctl.connected, False)
check("状态药丸复位", win.pill.text(), "未连接")
check("继电器磁贴复位", sum(1 for t in win.relay_panel._tiles.values()
                              if t.isChecked()), 0)

print()
print("=" * 74)
print("11) 多路规格：切换到 16 路")
print("=" * 74)
win.conn_panel.transport_combo.setCurrentIndex(
    win.conn_panel.transport_combo.findText("模拟器 (无硬件)"))
# 步骤 9 把地址改成了 8，这里复位到 1，避免带着上次的地址重连
win.conn_panel.ext_radio.setChecked(False)
win.conn_panel.addr_spin.setValue(1)
win.conn_panel.connect_btn.click()
pump(app, 1000)
check("会话地址已复位为 1", win.ctl.addr, 1)
mod = win.ctl.transport.module_for(win.ctl.addr)   # 重连后是新传输层，必须重新取
check_true("重连后拿到新的虚拟模块", mod is not None)
win.relay_count_combo.setCurrentText("16 路")
win.input_count_combo.setCurrentText("16 路")
pump(app, 500)
check("继电器磁贴变为 16 个", len(win.relay_panel._tiles), 16)
check("输入磁贴变为 16 个", len(win.input_panel._tiles), 16)
win.relay_panel.all_on_btn.click()
pump(app, 900)
check("16 路全部闭合", sorted(mod.relays), list(range(1, 17)))
check("16 路模块规格已生效", mod.num_relays, 16)
win.tabs.setCurrentWidget(win.relay_panel)
pump(app, 300)
shoot(win, "08_16路继电器规格.png")
win.tabs.setCurrentWidget(win.analyzer_panel)
pump(app, 300)
shoot(win, "09_帧构造与地址解析_修复后.png")

win.close()
pump(app, 200)

print()
print("=" * 74)
if FAIL:
    print(f"结果: {len(FAIL)} 项失败")
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print(f"结果: 全部通过 ✔  截图已保存到 {SHOT_DIR}")
