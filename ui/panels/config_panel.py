"""CANIO 模块参数设置面板（地址 / 波特率 / 主动上传 / 总线扫描）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from canio import protocol as P

from .. import theme as T
from ..widgets import Card, hint_label

WARN_BG = f"background:#2A2208; border:1px solid {T.WARN}; border-radius:8px;" \
          f"padding:8px 10px; color:{T.WARN}; font-weight:600;"


def _kv(label: str) -> tuple[QWidget, QLabel]:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lab = QLabel(label)
    lab.setStyleSheet(
        f"color:{T.TEXT_DIM}; font-size:11px; background:transparent;")
    lab.setFixedWidth(96)
    val = QLabel("—")
    val.setStyleSheet(
        f"color:{T.TEXT}; font-family:{T.FONT_MONO}; font-size:13px;"
        f"font-weight:700; background:transparent;")
    val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lay.addWidget(lab)
    lay.addWidget(val, 1)
    return w, val


class ConfigPanel(QWidget):
    """模块参数在线读写。"""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctl = controller

        root = QGridLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(12)

        root.addWidget(self._card_read(), 0, 0)
        root.addWidget(self._card_scan(), 0, 1)
        root.addWidget(self._card_addr(), 1, 0)
        root.addWidget(self._card_baud(), 1, 1)
        root.addWidget(self._card_upload(), 2, 0)
        self.sim_card = self._card_simulator()
        root.addWidget(self.sim_card, 2, 1)
        root.setRowStretch(3, 1)

    # ================================================================== #
    def _card_read(self) -> Card:
        card = Card("当前参数", "功能码 0x04 / 子命令 0xA1、0xA2")
        self.k_addr, self.v_addr = _kv("地址码")
        self.k_baud, self.v_baud = _kv("波特率码")
        self.k_bps, self.v_bps = _kv("实际波特率")
        self.k_up, self.v_up = _kv("主动上传")
        self.k_online, self.v_online = _kv("通讯状态")
        for w in (self.k_addr, self.k_baud, self.k_bps, self.k_up, self.k_online):
            card.add(w)

        row = QHBoxLayout()
        self.read_btn = QPushButton("读取全部参数")
        self.read_btn.setObjectName("Primary")
        self.read_btn.clicked.connect(lambda: self.ctl.read_all())
        row.addWidget(self.read_btn)
        row.addStretch(1)
        card.add_layout(row)
        return card

    def _card_addr(self) -> Card:
        card = Card("写入模块地址", "子命令 0xB1")
        row = QHBoxLayout()
        row.addWidget(QLabel("新地址"))
        self.addr_spin = QSpinBox()
        self.addr_spin.setRange(P.ADDR_MIN, P.ADDR_MAX)
        self.addr_spin.setValue(2)
        row.addWidget(self.addr_spin, 1)
        self.addr_btn = QPushButton("写入")
        self.addr_btn.clicked.connect(
            lambda: self.ctl.write_address(self.addr_spin.value(),
                                           on_done=lambda *_: self._after_write()))
        row.addWidget(self.addr_btn)
        card.add_layout(row)

        self.addr_note = hint_label("")
        self.addr_note.setStyleSheet(WARN_BG)
        self.addr_note.setVisible(False)
        card.add(self.addr_note)
        return card

    def _card_baud(self) -> Card:
        card = Card("写入波特率", "子命令 0xB2（手册 表2.6）")
        row = QHBoxLayout()
        row.addWidget(QLabel("波特率码"))
        self.baud_combo = QComboBox()
        for code, bps in sorted(P.BAUD_CODE_TO_BPS.items()):
            self.baud_combo.addItem(f"0x{code:02X}   {P.bps_label(bps)}", code)
        self.baud_combo.setCurrentIndex(
            list(sorted(P.BAUD_CODE_TO_BPS)).index(0x09))
        row.addWidget(self.baud_combo, 1)
        self.baud_btn = QPushButton("写入")
        self.baud_btn.clicked.connect(
            lambda: self.ctl.write_baud(int(self.baud_combo.currentData()),
                                        on_done=lambda *_: self._after_write()))
        row.addWidget(self.baud_btn)
        card.add_layout(row)

        self.baud_note = hint_label("")
        self.baud_note.setStyleSheet(WARN_BG)
        self.baud_note.setVisible(False)
        card.add(self.baud_note)
        return card

    def _card_upload(self) -> Card:
        card = Card("主动上传间隔", "子命令 0xB3 · 16 位大端 · 单位 ms")
        row = QHBoxLayout()
        self.up_spin = QSpinBox()
        self.up_spin.setRange(0, 60000)
        self.up_spin.setValue(0)
        self.up_spin.setSuffix("  ms")
        self.up_spin.setSpecialValueText("0 ms  (关闭主动上传)")
        row.addWidget(self.up_spin, 1)
        self.up_btn = QPushButton("写入")
        self.up_btn.clicked.connect(
            lambda: self.ctl.write_upload(self.up_spin.value()))
        row.addWidget(self.up_btn)
        card.add_layout(row)
        card.add(hint_label(
            "最小间隔 5ms，0 表示不主动上传。此参数「设置后立即生效」并掉电保存。"))
        return card

    def _card_scan(self) -> Card:
        card = Card("总线设备扫描", "按地址逐个读取，发现在线模块")
        row = QHBoxLayout()
        row.addWidget(QLabel("范围"))
        self.scan_from = QSpinBox()
        self.scan_from.setRange(1, 255)
        self.scan_from.setValue(1)
        self.scan_to = QSpinBox()
        self.scan_to.setRange(1, 255)
        self.scan_to.setValue(32)
        for s in (self.scan_from, self.scan_to):
            s.setFixedWidth(62)
        row.addWidget(self.scan_from)
        row.addWidget(QLabel("~"))
        row.addWidget(self.scan_to)
        self.scan_btn = QPushButton("开始扫描")
        self.scan_btn.clicked.connect(
            lambda: self.ctl.scan(self.scan_from.value(), self.scan_to.value(),
                                  on_done=self._on_scan_done))
        row.addWidget(self.scan_btn, 1)
        card.add_layout(row)

        self.scan_result = QLabel("尚未扫描")
        self.scan_result.setWordWrap(True)
        self.scan_result.setStyleSheet(
            f"background:{T.BG_INPUT}; border:1px solid {T.BORDER};"
            f"border-radius:8px; padding:8px 10px; color:{T.TEXT_DIM};"
            f"font-family:{T.FONT_MONO};")
        card.add(self.scan_result)
        return card

    def _card_simulator(self) -> Card:
        card = Card("模拟器工具", "仅在使用内置模拟器时可用")
        card.add(hint_label(
            "真机修改地址 / 波特率后必须断电重启才生效；此处可模拟该过程，"
            "也可以在总线上注入输入信号。"))

        row = QHBoxLayout()
        self.power_btn = QPushButton("模拟断电重启")
        self.power_btn.clicked.connect(self._sim_power_cycle)
        row.addWidget(self.power_btn, 1)
        card.add_layout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("注入输入通道"))
        self.sim_ch = QSpinBox()
        self.sim_ch.setRange(1, 48)
        self.sim_ch.setValue(1)
        self.sim_ch.setFixedWidth(62)
        row2.addWidget(self.sim_ch)
        self.sim_on = QPushButton("置为触发")
        self.sim_on.setObjectName("Mini")
        self.sim_on.clicked.connect(lambda: self._sim_input(True))
        self.sim_off = QPushButton("置为未触发")
        self.sim_off.setObjectName("Mini")
        self.sim_off.clicked.connect(lambda: self._sim_input(False))
        row2.addWidget(self.sim_on)
        row2.addWidget(self.sim_off)
        row2.addStretch(1)
        card.add_layout(row2)

        self.sim_jitter = QCheckBox("随机输入抖动（仅演示用）")
        self.sim_jitter.setToolTip(
            "开启后模拟器会随机翻转输入通道，用于演示界面动态效果。\n"
            "正式调试建议关闭，这样界面只反映你注入的信号。")
        self.sim_jitter.toggled.connect(self._sim_set_jitter)
        card.add(self.sim_jitter)

        self.sim_note = hint_label("")
        card.add(self.sim_note)
        return card

    # ================================================================== #
    def _after_write(self) -> None:
        show = True
        for note, text in (
            (self.addr_note, "地址已下发 —— 请给模块断电约 5 秒后重新上电，新地址才会生效。"),
            (self.baud_note, "波特率已下发 —— 请给模块断电约 5 秒后重新上电，"
                             "并同步把调试器波特率改成一致，否则将无法通讯。"),
        ):
            note.setText(text)
            note.setVisible(show)

    def _on_scan_done(self, found) -> None:
        if found is None:
            found = []
        if found:
            self.scan_result.setText(
                f"发现 {len(found)} 台模块，地址：" + ", ".join(str(a) for a in found))
            self.scan_result.setStyleSheet(
                f"background:#0C2A1B; border:1px solid {T.OK}; border-radius:8px;"
                f"padding:8px 10px; color:{T.OK}; font-family:{T.FONT_MONO};")
        else:
            self.scan_result.setText(
                "未发现任何应答。请检查：波特率是否一致、H/L 接线、终端电阻、"
                "模块地址是否在扫描范围内。")
            self.scan_result.setStyleSheet(
                f"background:#2A2208; border:1px solid {T.WARN}; border-radius:8px;"
                f"padding:8px 10px; color:{T.WARN}; font-weight:600;")

    # -- 模拟器 ---------------------------------------------------------- #
    def _is_simulator(self) -> bool:
        from canio.transport import SimulatorTransport
        return isinstance(self.ctl.transport, SimulatorTransport)

    def _sim_power_cycle(self) -> None:
        if self._is_simulator():
            self.ctl.transport.power_cycle()
            self.sim_note.setText("虚拟模块已重启，待生效的地址 / 波特率已生效。")
            self.ctl.read_all()

    def _sim_set_jitter(self, on: bool) -> None:
        if self._is_simulator():
            self.ctl.transport.random_inputs = bool(on)
            self.sim_note.setText(
                "已开启随机输入抖动（演示模式）。" if on else "已关闭随机输入抖动。")

    def _sim_input(self, on: bool) -> None:
        if not self._is_simulator():
            return
        try:
            self.ctl.transport.set_input(self.sim_ch.value(), on,
                                         addr=self.ctl.addr)
            self.sim_note.setText(
                f"已把输入 X{self.sim_ch.value()} 置为{'触发' if on else '未触发'}。")
            self.ctl.read_inputs()
        except Exception as exc:
            self.sim_note.setText(f"注入失败：{exc}")

    # ================================================================== #
    def sync(self, state: dict) -> None:
        """按会话状态刷新显示。"""
        addr = state.get("addr")
        if addr is not None:
            self.v_addr.setText(f"{addr}   (0x{addr:02X})")
            self.addr_spin.setValue(addr)

        code = state.get("baud_code")
        if code is not None:
            self.v_baud.setText(f"0x{code:02X}")
            bps = P.BAUD_CODE_TO_BPS.get(code)
            self.v_bps.setText(P.bps_label(bps) if bps else "未知档位")
            self.v_bps.setStyleSheet(
                f"color:{T.OK}; font-family:{T.FONT_MONO}; font-size:13px;"
                f"font-weight:700; background:transparent;")
            idx = self.baud_combo.findData(code)
            if idx >= 0:
                self.baud_combo.setCurrentIndex(idx)

        up = state.get("upload_ms")
        if up is not None:
            self.v_up.setText("关闭" if up == 0 else f"{up} ms")
            self.up_spin.setValue(up)

        pa = state.get("pending_addr")
        if pa is not None:
            self.addr_note.setText(
                f"已下发新地址 {pa} —— 需断电重启模块后才生效（真机）。")
            self.addr_note.setVisible(True)
        pb = state.get("pending_baud_code")
        if pb is not None:
            bps = P.BAUD_CODE_TO_BPS.get(pb)
            self.baud_note.setText(
                f"已下发波特率码 0x{pb:02X} ({P.bps_label(bps)}) —— "
                f"需断电重启模块后才生效，且调试器波特率要同步修改。")
            self.baud_note.setVisible(True)

        online = state.get("online")
        if online is not None:
            if online:
                self.v_online.setText("在线 ✓")
                self.v_online.setStyleSheet(
                    f"color:{T.OK}; font-family:{T.FONT_MONO}; font-size:13px;"
                    f"font-weight:700; background:transparent;")
            else:
                self.v_online.setText("无应答")
                self.v_online.setStyleSheet(
                    f"color:{T.TEXT_MUTE}; font-family:{T.FONT_MONO};"
                    f"font-size:13px; font-weight:700; background:transparent;")

        self.sim_card.setVisible(self._is_simulator())

    def set_enabled_state(self, connected: bool) -> None:
        for w in (self.read_btn, self.addr_btn, self.baud_btn, self.up_btn,
                  self.scan_btn, self.addr_spin, self.baud_combo, self.up_spin,
                  self.scan_from, self.scan_to, self.sim_ch, self.sim_on,
                  self.sim_off, self.power_btn, self.sim_jitter):
            w.setEnabled(connected)
