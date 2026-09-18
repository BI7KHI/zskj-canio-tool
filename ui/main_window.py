"""CANIO 继电器调试台 —— 主窗口。"""
from __future__ import annotations

import os
import sys
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout,
                               QLabel, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSpinBox, QTabWidget,
                               QVBoxLayout, QWidget)

from canio import protocol as P

from . import theme as T
from .controller import SessionController
from .panels.analyzer_panel import AnalyzerPanel
from .panels.config_panel import ConfigPanel
from .panels.connection import ConnectionPanel
from .panels.frame_panel import FramePanel
from .panels.input_panel import InputPanel
from .panels.relay_panel import CHANNEL_CHOICES, RelayPanel
from .widgets import Card, StatChip, StatusPill, hint_label, section_label

#: 无界面环境（自动化测试）下抑制模态对话框，避免阻塞
SUPPRESS_DIALOGS = os.environ.get("CANIO_NO_DIALOG") == "1"


def _warn(parent, title: str, text: str) -> None:
    if SUPPRESS_DIALOGS:
        print(f"[dialog suppressed] {title}: {text}", file=sys.stderr)
        return
    QMessageBox.warning(parent, title, text)


def make_icon() -> QIcon:
    """程序图标：深底 + 青色继电器符号。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(T.ACCENT_DK))
    p.setPen(QColor(T.ACCENT))
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setPen(QColor("#EAFBFF"))
    f = QFont(T.FONT_MONO, 26)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), int(Qt.AlignmentFlag.AlignCenter), "IO")
    p.end()
    return QIcon(pm)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CANIO 继电器调试台  ·  中盛数字量输入输出系列 (CAN 版)")
        self.setWindowIcon(make_icon())
        self.resize(1440, 900)
        self.setMinimumSize(1120, 720)

        self.ctl = SessionController(self)
        self._connected = False
        self._last_sb_update = 0.0

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 12, 14, 8)
        outer.setSpacing(11)

        outer.addWidget(self._header())

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._sidebar(), 0)
        body.addWidget(self._tabs(), 1)
        outer.addLayout(body, 1)

        self._build_statusbar()
        self._wire()

        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(500)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start()

        self._on_connection_changed(False, "")

    # ================================================================== #
    # 顶部
    # ================================================================== #
    def _header(self) -> QWidget:
        w = QFrame()
        w.setObjectName("CardFlat")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 11, 16, 11)
        lay.setSpacing(13)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        t1 = QLabel("CANIO 继电器调试台")
        t1.setObjectName("Title")
        t2 = QLabel("中盛科技 · 数字量输入输出系列（CAN 版）·  依据使用手册 V3.0 通讯协议实现")
        t2.setObjectName("SubTitle")
        title_box.addWidget(t1)
        title_box.addWidget(t2)
        lay.addLayout(title_box)
        lay.addStretch(1)

        self.link_lbl = QLabel("—")
        self.link_lbl.setObjectName("Mono")
        self.link_lbl.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-family:{T.FONT_MONO}; font-size:11px;"
            f"background:transparent;")
        lay.addWidget(self.link_lbl)

        self.pill = StatusPill("未连接")
        lay.addWidget(self.pill)
        return w

    # ================================================================== #
    # 左侧栏
    # ================================================================== #
    def _sidebar(self) -> QWidget:
        host = QWidget()
        host.setFixedWidth(348)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(11)

        self.conn_panel = ConnectionPanel()
        lay.addWidget(self.conn_panel)
        lay.addWidget(self._card_profile())
        lay.addWidget(self._card_polling())
        lay.addWidget(self._card_stats())
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        outer = QVBoxLayout(host)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return host

    def _card_profile(self) -> Card:
        card = Card("模块规格", "选择与实际模块一致的路数")
        row = QHBoxLayout()
        row.setSpacing(7)
        col1 = QVBoxLayout()
        col1.setSpacing(3)
        col1.addWidget(section_label("继电器输出"))
        self.relay_count_combo = QComboBox()
        for n in CHANNEL_CHOICES:
            self.relay_count_combo.addItem(f"{n} 路", n)
        self.relay_count_combo.setCurrentText("4 路")
        col1.addWidget(self.relay_count_combo)
        col2 = QVBoxLayout()
        col2.setSpacing(3)
        col2.addWidget(section_label("数字量输入"))
        self.input_count_combo = QComboBox()
        for n in CHANNEL_CHOICES:
            self.input_count_combo.addItem(f"{n} 路", n)
        self.input_count_combo.setCurrentText("4 路")
        col2.addWidget(self.input_count_combo)
        row.addLayout(col1, 1)
        row.addLayout(col2, 1)
        card.add_layout(row)
        card.add(hint_label(
            "本协议数据域为 6 字节 × 8 位，单帧最多寻址 48 路。"
            "当前连接的 4 路模块请保持默认。"))
        return card

    def _card_polling(self) -> Card:
        card = Card("周期轮询", "自动刷新界面状态")
        self.poll_check = QCheckBox("启用自动轮询")
        card.add(self.poll_check)

        row = QHBoxLayout()
        row.addWidget(QLabel("间隔"))
        self.poll_interval = QSpinBox()
        self.poll_interval.setRange(50, 5000)
        self.poll_interval.setValue(200)
        self.poll_interval.setSuffix(" ms")
        self.poll_interval.setSingleStep(50)
        row.addWidget(self.poll_interval, 1)
        card.add_layout(row)

        self.poll_inputs = QCheckBox("读取输入口状态 (0x03)")
        self.poll_inputs.setChecked(True)
        self.poll_relays = QCheckBox("读取继电器状态 (0x02)")
        self.poll_relays.setChecked(True)
        card.add(self.poll_inputs)
        card.add(self.poll_relays)
        return card

    def _card_stats(self) -> Card:
        card = Card("通讯统计", "本会话累计")
        grid = QHBoxLayout()
        grid.setSpacing(7)
        self.chip_tx = StatChip("发送 TX", "0", T.TX)
        self.chip_rx = StatChip("接收 RX", "0", T.RX)
        self.chip_to = StatChip("超时", "0", T.WARN)
        self.chip_er = StatChip("错误", "0", T.ERR)
        for c in (self.chip_tx, self.chip_rx, self.chip_to, self.chip_er):
            grid.addWidget(c, 1)
        card.add_layout(grid)

        row = QHBoxLayout()
        self.reset_stats_btn = QPushButton("清零统计")
        self.reset_stats_btn.setObjectName("Mini")
        self.reset_stats_btn.clicked.connect(self._reset_stats)
        row.addWidget(self.reset_stats_btn)
        row.addStretch(1)
        card.add_layout(row)
        return card

    # ================================================================== #
    # 主标签页
    # ================================================================== #
    def _tabs(self) -> QWidget:
        self.tabs = QTabWidget()

        self.relay_panel = RelayPanel(self.ctl)
        self.input_panel = InputPanel(self.ctl)
        self.analyzer_panel = AnalyzerPanel(self.ctl)
        self.frame_panel = FramePanel(self.ctl)
        self.config_panel = ConfigPanel(self.ctl)

        self.analyzer_panel._relay_count_provider = (
            lambda: int(self.relay_count_combo.currentData()))

        self.tabs.addTab(self.relay_panel, "继电器控制")
        self.tabs.addTab(self.input_panel, "输入监视")
        self.tabs.addTab(self.analyzer_panel, "帧构造 / 地址解析")
        self.tabs.addTab(self.frame_panel, "原始帧监视")
        self.tabs.addTab(self.config_panel, "模块参数")
        return self.tabs

    # ================================================================== #
    # 状态栏
    # ================================================================== #
    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.sb_left = QLabel("就绪 —— 请选择调试器并点击「连接」")
        self.sb_left.setStyleSheet(
            f"color:{T.TEXT_DIM}; background:transparent; font-size:11px;")
        sb.addWidget(self.sb_left)
        self.sb_right = QLabel("")
        self.sb_right.setStyleSheet(
            f"color:{T.TEXT_MUTE}; font-family:{T.FONT_MONO}; font-size:11px;"
            f"background:transparent;")
        sb.addPermanentWidget(self.sb_right)

    def _status(self, text: str, colour: str = T.TEXT_DIM) -> None:
        self.sb_left.setText(text)
        self.sb_left.setStyleSheet(
            f"color:{colour}; background:transparent; font-size:11px;")

    # ================================================================== #
    # 信号连接
    # ================================================================== #
    def _wire(self) -> None:
        self.conn_panel.connectRequested.connect(self._on_connect)
        self.conn_panel.disconnectRequested.connect(self._on_disconnect)
        self.conn_panel.addr_spin.valueChanged.connect(
            lambda v: self.ctl.set_addr(v))
        self.conn_panel.std_radio.toggled.connect(
            lambda std: self.ctl.set_extended(not std))

        self.relay_count_combo.currentIndexChanged.connect(self._on_relay_count)
        self.input_count_combo.currentIndexChanged.connect(self._on_input_count)

        self.poll_check.toggled.connect(self._on_poll_toggled)
        for w in (self.poll_interval, self.poll_inputs, self.poll_relays):
            if hasattr(w, "valueChanged"):
                w.valueChanged.connect(self._restart_polling)
            else:
                w.toggled.connect(self._restart_polling)

        self.ctl.connectionChanged.connect(self._on_connection_changed)
        self.ctl.frameReceived.connect(self._on_frame)
        self.ctl.logReceived.connect(self.frame_panel.on_log)
        self.ctl.stateChanged.connect(self._on_state)
        self.ctl.errorOccurred.connect(self._on_error)
        self.ctl.busyChanged.connect(self._on_busy)

        self.frame_panel.frameActivated.connect(self._on_frame_activated)
        self.frame_panel.export_btn.clicked.connect(self._on_export)

    # ================================================================== #
    # 连接 / 断开
    # ================================================================== #
    def _on_connect(self) -> None:
        if self._connected:
            return
        kind = self.conn_panel.transport_kind
        if kind != "模拟器 (无硬件)":
            try:
                transport = self.conn_panel.build_transport()
            except Exception as exc:
                _warn(self, "参数错误", str(exc))
                return
            if getattr(transport, "port", "x") == "":
                _warn(self, "未选择串口",
                      "请先选择一个串口（可点击「刷新」重新枚举）。")
                return
        else:
            transport = self.conn_panel.build_transport()

        addr = self.conn_panel.addr
        ext = self.conn_panel.frame_extended
        self.pill.set_state("busy", "连接中…")
        self.conn_panel.connect_btn.setEnabled(False)
        self._status(f"正在打开 {transport.display_name} …", T.WARN)

        def work():
            transport.open()
            return transport

        def done(t):
            self.ctl.attach(t, addr, ext)
            if hasattr(t, "reconfigure"):
                t.reconfigure(addr, int(self.relay_count_combo.currentData()),
                              int(self.input_count_combo.currentData()))
            self._status("已连接，正在读取模块参数 …", T.OK)
            self.ctl.read_all(on_done=lambda *_: self._status(
                "连接就绪。可开始调试。", T.OK))
            if self.poll_check.isChecked():
                self._restart_polling()

        def fail(msg: str):
            self.pill.set_state("err", "连接失败")
            self.conn_panel.set_connected(False)
            self._status(f"连接失败：{msg}", T.ERR)
            _warn(
                self, "连接失败",
                f"无法打开 {transport.display_name}。\n\n{msg}\n\n"
                "排查建议：\n"
                "· SLCAN：确认串口未被其它软件占用（如串口助手、官方测试软件）\n"
                "· 确认 USB-CAN 转接器驱动已安装，设备管理器中能看到对应 COM 口\n"
                "· 检查 H(CAN+)/L(CAN-) 接线与终端电阻\n"
                "· 模块与调试器的 CAN 波特率必须一致\n"
                "· 若为 PCAN-Basic：确认 PCANBasic.dll 与驱动已安装")

        self.ctl.submit(work, on_done=done, on_error=fail)

    def _on_disconnect(self) -> None:
        self.ctl.stop_polling()
        self.ctl.detach()
        self._status("已断开连接。", T.TEXT_DIM)

    def _on_connection_changed(self, connected: bool, description: str) -> None:
        self._connected = connected
        self.conn_panel.set_connected(connected)
        for panel in (self.relay_panel, self.input_panel, self.analyzer_panel,
                      self.frame_panel, self.config_panel):
            panel.setEnabled(True)
        self.config_panel.set_enabled_state(connected)
        self.poll_check.setEnabled(connected)
        if connected:
            self.pill.set_state("ok", "已连接")
            self.link_lbl.setText(description)
        else:
            self.pill.set_state("off", "未连接")
            self.link_lbl.setText("—")
            self.relay_panel.sync_tiles(set())
            self.input_panel.sync(set())
            self.config_panel.sync({"online": False, "addr": None,
                                    "baud_code": None, "upload_ms": None})
        self._refresh_stats()

    def _on_busy(self, busy: bool) -> None:
        if busy and self._connected:
            self.pill.set_state("busy", "通讯中…")
        elif self._connected:
            self.pill.set_state("ok", "已连接")

    # ================================================================== #
    # 模块规格
    # ================================================================== #
    def _on_relay_count(self) -> None:
        n = int(self.relay_count_combo.currentData())
        self.relay_panel.set_channel_count(n)
        if self._connected and hasattr(self.ctl.transport, "reconfigure"):
            try:
                self.ctl.transport.reconfigure(
                    self.ctl.addr, n, int(self.input_count_combo.currentData()))
            except Exception:
                pass

    def _on_input_count(self) -> None:
        n = int(self.input_count_combo.currentData())
        self.input_panel.set_channel_count(n)
        if self._connected and hasattr(self.ctl.transport, "reconfigure"):
            try:
                self.ctl.transport.reconfigure(
                    self.ctl.addr, int(self.relay_count_combo.currentData()), n)
            except Exception:
                pass

    # ================================================================== #
    # 轮询
    # ================================================================== #
    def _on_poll_toggled(self, on: bool) -> None:
        if not self._connected:
            return
        if on:
            self._restart_polling()
        else:
            self.ctl.stop_polling()
            self._status("已停止自动轮询。", T.TEXT_DIM)

    def _restart_polling(self) -> None:
        if not self._connected or not self.poll_check.isChecked():
            return
        self.ctl.start_polling(self.poll_interval.value(),
                               self.poll_inputs.isChecked(),
                               self.poll_relays.isChecked())

    # ================================================================== #
    # 数据更新
    # ================================================================== #
    def _on_frame(self, frame: P.CanFrame, parsed: P.ParsedFrame) -> None:
        self.frame_panel.on_frame(frame, parsed)
        # 高频报文下没必要每帧都刷新状态栏，节流到 ~8Hz
        now = time.monotonic()
        if now - self._last_sb_update < 0.12:
            return
        self._last_sb_update = now
        self.sb_right.setText(f"最近 {frame.id_text}  {frame.data_text}")

    def _on_state(self, changed: dict) -> None:
        if "relays" in changed:
            self.relay_panel.sync_tiles(changed["relays"])
        if "inputs" in changed:
            self.input_panel.sync(changed["inputs"])
        self.config_panel.sync(changed)
        if "addr" in changed:
            self.conn_panel.addr_spin.blockSignals(True)
            self.conn_panel.addr_spin.setValue(changed["addr"])
            self.conn_panel.addr_spin.blockSignals(False)

    def _on_error(self, message: str) -> None:
        self._status(f"⚠ {message}", T.ERR)

    def _on_frame_activated(self, frame: P.CanFrame) -> None:
        self.analyzer_panel.load_frame(frame)
        self.tabs.setCurrentWidget(self.analyzer_panel)

    def _on_export(self) -> None:
        path = self.frame_panel.export_csv()
        if path:
            self._status(f"已导出：{path}", T.OK)

    # ================================================================== #
    def _refresh_stats(self) -> None:
        s = self.ctl.session.stats if self.ctl.session else None
        if s is None:
            for c, col in ((self.chip_tx, T.TX), (self.chip_rx, T.RX),
                           (self.chip_to, T.WARN), (self.chip_er, T.ERR)):
                c.set_value(0, T.TEXT_MUTE)
            return
        self.chip_tx.set_value(s.tx, T.TX if s.tx else T.TEXT_MUTE)
        self.chip_rx.set_value(s.rx, T.RX if s.rx else T.TEXT_MUTE)
        self.chip_to.set_value(s.timeouts, T.WARN if s.timeouts else T.TEXT_MUTE)
        self.chip_er.set_value(s.errors, T.ERR if s.errors else T.TEXT_MUTE)

    def _reset_stats(self) -> None:
        if self.ctl.session:
            self.ctl.session.stats.reset()
        self._refresh_stats()

    # ================================================================== #
    def closeEvent(self, event) -> None:
        try:
            self.ctl.stop_polling()
            self.ctl.detach()
        except Exception:
            pass
        super().closeEvent(event)
