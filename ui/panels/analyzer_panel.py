"""帧构造器 + 地址解析（位域拆解）面板。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QSpinBox, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from canio import protocol as P

from .. import theme as T
from ..widgets import ByteBitTable, Card, hint_label, section_label


def _lab(text: str, obj: str = "") -> QLabel:
    w = QLabel(text)
    if obj:
        w.setObjectName(obj)
    return w


def _mono(text: str, color: str = T.TEXT, size: int = 11,
          bold: bool = False) -> QLabel:
    w = QLabel(text)
    w.setStyleSheet(
        f"font-family:{T.FONT_MONO}; font-size:{size}px; color:{color};"
        f"font-weight:{'700' if bold else '400'}; background:transparent;")
    w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return w


def parse_id_text(text: str) -> Optional[int]:
    """接受 0x101 / 101 / AA0101 / 0xAA0101 等写法。"""
    s = text.strip().replace("0x", "").replace("0X", "").replace(" ", "")
    if not s:
        return None
    try:
        return int(s, 16)
    except ValueError:
        return None


def parse_data_text(text: str) -> Optional[bytes]:
    """接受 '03 00 F0' / '0300F0' / '03,00,F0' 等写法。"""
    s = (text.strip().replace("0x", "").replace("0X", "")
         .replace(",", " ").replace("-", " "))
    if not s:
        return b""
    s = "".join(s.split())
    if len(s) % 2:
        return None
    try:
        return bytes.fromhex(s)
    except ValueError:
        return None


class AnalyzerPanel(QWidget):
    """左边造帧，右边解帧 —— 调试时最常用的两个动作。"""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctl = controller
        self._last_built: Optional[P.CanFrame] = None
        #: 由主窗口注入，用于「全选」按钮取当前继电器路数
        self._relay_count_provider = None

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(12)
        root.addWidget(self._scrolled(self._build_builder()), 5)
        root.addWidget(self._scrolled(self._build_resolver()), 6)

        self._on_func_changed()
        self._refresh_preview()

    @staticmethod
    def _scrolled(widget: QWidget) -> QScrollArea:
        """内容较高的卡片放进滚动区，避免被挤压变形。"""
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(widget)
        return area

    # ================================================================== #
    # 左侧：帧构造器
    # ================================================================== #
    def _build_builder(self) -> QWidget:
        card = Card("CAN 帧构造器", "按手册生成报文")

        form = QFormLayout()
        form.setSpacing(7)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignVCenter)

        self.func_combo = QComboBox()
        for code in (P.FUNC_WRITE_RELAY, P.FUNC_READ_RELAY, P.FUNC_READ_INPUT,
                     P.FUNC_CONFIG):
            self.func_combo.addItem(f"0x{code:02X}  {P.FUNC_NAMES[code]}", code)
        self.func_combo.currentIndexChanged.connect(self._on_func_changed)

        self.b_addr = QSpinBox()
        self.b_addr.setRange(P.ADDR_MIN, P.ADDR_MAX)
        self.b_addr.setValue(P.DEFAULT_ADDR)
        self.b_addr.valueChanged.connect(self._refresh_preview)

        self.b_ext = QComboBox()
        self.b_ext.addItem("标准帧", False)
        self.b_ext.addItem("扩展帧", True)
        self.b_ext.currentIndexChanged.connect(self._refresh_preview)

        form.addRow("功能码", self.func_combo)
        form.addRow("模块地址", self.b_addr)
        form.addRow("帧格式", self.b_ext)
        card.add_layout(form)

        # ---- 动态参数区 ---- #
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_relay())
        self.stack.addWidget(self._page_read())
        self.stack.addWidget(self._page_config())
        card.add(self.stack)

        card.add(self._preview_box())
        return card

    # -- 动态页 ---------------------------------------------------------- #
    def _page_relay(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        v.addWidget(section_label("闭合通道（支持 1,2,45-48 写法）"))

        self.ch_spec = QLineEdit("1")
        self.ch_spec.setPlaceholderText("例如  1,2,45-48")
        self.ch_spec.textChanged.connect(self._refresh_preview)
        v.addWidget(self.ch_spec)

        quick = QHBoxLayout()
        quick.setSpacing(5)
        for text in ("1-4", "1-8", "全选", "清空"):
            b = QPushButton(text)
            b.setObjectName("Mini")
            b.clicked.connect(lambda _=False, t=text: self._quick_channels(t))
            quick.addWidget(b)
        quick.addStretch(1)
        v.addLayout(quick)
        v.addStretch(1)                 # 多余空间留在底部，控件保持紧凑
        return w

    def _quick_channels(self, which: str) -> None:
        if which == "清空":
            self.ch_spec.setText("")
        elif which == "全选":
            self.ch_spec.setText(f"1-{self.relay_count()}")
        else:
            self.ch_spec.setText(which)

    def relay_count(self) -> int:
        """当前界面配置的继电器路数（由主窗口注入）。"""
        if self._relay_count_provider is not None:
            try:
                return max(1, int(self._relay_count_provider()))
            except Exception:
                pass
        return 4

    def _page_read(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(hint_label(
            "手册 2.3.2 / 2.3.3：读继电器、读输入口时，发送报文的数据域内容任意，"
            "模块会用同样的数据域格式返回当前状态。此处按惯例填 8 个 0x00。"))
        v.addStretch(1)
        return w

    def _page_config(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(7)

        self.cfg_combo = QComboBox()
        self.cfg_combo.addItem("0xA1  读取地址码", P.CFG_READ_ADDR)
        self.cfg_combo.addItem("0xA2  读取波特率码", P.CFG_READ_BAUD)
        self.cfg_combo.addItem("0xB1  写入新地址码", P.CFG_WRITE_ADDR)
        self.cfg_combo.addItem("0xB2  写入新波特率码", P.CFG_WRITE_BAUD)
        self.cfg_combo.addItem("0xB3  写入主动上传间隔", P.CFG_WRITE_UPLOAD)
        self.cfg_combo.currentIndexChanged.connect(self._on_cfg_changed)
        v.addWidget(self.cfg_combo)

        self.cfg_stack = QStackedWidget()
        self.cfg_stack.addWidget(QWidget())                   # 无参数

        holder_addr = QWidget()
        fa = QFormLayout(holder_addr)
        fa.setContentsMargins(0, 0, 0, 0)
        self.cfg_addr = QSpinBox()
        self.cfg_addr.setRange(P.ADDR_MIN, P.ADDR_MAX)
        self.cfg_addr.setValue(2)
        self.cfg_addr.valueChanged.connect(self._refresh_preview)
        fa.addRow("新地址 (1~255)", self.cfg_addr)
        self.cfg_stack.addWidget(holder_addr)

        holder_baud = QWidget()
        fb = QFormLayout(holder_baud)
        fb.setContentsMargins(0, 0, 0, 0)
        self.cfg_baud = QComboBox()
        for code, bps in sorted(P.BAUD_CODE_TO_BPS.items()):
            self.cfg_baud.addItem(f"0x{code:02X}  {P.bps_label(bps)}", code)
        self.cfg_baud.setCurrentText("0x09  500 kbps")
        self.cfg_baud.currentIndexChanged.connect(self._refresh_preview)
        fb.addRow("新波特率码", self.cfg_baud)
        self.cfg_stack.addWidget(holder_baud)

        holder_iv = QWidget()
        fi = QFormLayout(holder_iv)
        fi.setContentsMargins(0, 0, 0, 0)
        self.cfg_iv = QSpinBox()
        self.cfg_iv.setRange(0, 60000)
        self.cfg_iv.setValue(10)
        self.cfg_iv.setSuffix(" ms")
        self.cfg_iv.setSpecialValueText("0 ms (关闭主动上传)")
        self.cfg_iv.valueChanged.connect(self._refresh_preview)
        fi.addRow("上传间隔 (大端)", self.cfg_iv)
        self.cfg_stack.addWidget(holder_iv)

        v.addWidget(self.cfg_stack)
        v.addWidget(hint_label("注意：地址码与波特率码写入后，需断电重启模块才生效。"))
        v.addStretch(1)
        return w

    def _on_cfg_changed(self) -> None:
        cmd = self.cfg_combo.currentData()
        idx = {P.CFG_READ_ADDR: 0, P.CFG_READ_BAUD: 0,
               P.CFG_WRITE_ADDR: 1, P.CFG_WRITE_BAUD: 2,
               P.CFG_WRITE_UPLOAD: 3}.get(cmd, 0)
        self.cfg_stack.setCurrentIndex(idx)
        self._refresh_preview()

    # -- 预览 ------------------------------------------------------------ #
    def _preview_box(self) -> QWidget:
        box = QGroupBox("生成结果")
        v = QVBoxLayout(box)
        v.setContentsMargins(11, 14, 11, 10)
        v.setSpacing(5)

        self.lb_id = _mono("CAN ID  : —", T.ACCENT, 12, True)
        self.lb_data = _mono("数据域 : —", T.TEXT, 12)
        self.lb_slcan = _mono("SLCAN  : —", T.TEXT_DIM, 10)
        for w in (self.lb_id, self.lb_data, self.lb_slcan):
            v.addWidget(w)

        self.lb_warn = hint_label("")
        self.lb_warn.setWordWrap(True)
        v.addWidget(self.lb_warn)

        row = QHBoxLayout()
        self.send_btn = QPushButton("发送此帧")
        self.send_btn.setObjectName("Primary")
        self.send_btn.clicked.connect(self._send_built)
        self.copy_btn = QPushButton("复制")
        self.copy_btn.setObjectName("Mini")
        self.copy_btn.clicked.connect(self._copy_built)
        row.addWidget(self.send_btn, 2)
        row.addWidget(self.copy_btn, 1)
        v.addLayout(row)
        return box

    # ================================================================== #
    # 右侧：地址解析
    # ================================================================== #
    def _build_resolver(self) -> QWidget:
        card = Card("地址解析 / 帧反解", "输入 CAN ID 或整帧，查看位域含义")

        # ---- 输入区 ---- #
        inp = QFormLayout()
        inp.setSpacing(7)
        inp.setLabelAlignment(Qt.AlignmentFlag.AlignRight
                              | Qt.AlignmentFlag.AlignVCenter)

        self.r_id = QLineEdit("0x101")
        self.r_id.setPlaceholderText("0x101  或  0xAA0101，也可粘贴整帧")
        self.r_id.textChanged.connect(self._do_resolve)

        self.r_ext = QComboBox()
        self.r_ext.addItem("标准帧 (11 位 ID)", False)
        self.r_ext.addItem("扩展帧 (29 位 ID)", True)
        self.r_ext.currentIndexChanged.connect(self._do_resolve)

        self.r_data = QLineEdit("03 00 00 00 00 F0 00 00")
        self.r_data.setPlaceholderText("数据域，例如  03 00 00 00 00 F0 00 00")
        self.r_data.textChanged.connect(self._do_resolve)

        inp.addRow("CAN ID", self.r_id)
        inp.addRow("帧格式", self.r_ext)
        inp.addRow("数据域", self.r_data)
        card.add_layout(inp)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.r_paste_btn = QPushButton("粘贴整帧")
        self.r_paste_btn.setObjectName("Mini")
        self.r_paste_btn.clicked.connect(self._paste_frame)
        self.r_demo_btn = QPushButton("填入手册示例")
        self.r_demo_btn.setObjectName("Mini")
        self.r_demo_btn.clicked.connect(self._fill_demo)
        self.r_send_btn = QPushButton("发送此帧")
        self.r_send_btn.setObjectName("Mini")
        self.r_send_btn.clicked.connect(self._send_resolved)
        row.addWidget(self.r_paste_btn)
        row.addWidget(self.r_demo_btn)
        row.addWidget(self.r_send_btn)
        row.addStretch(1)
        card.add_layout(row)

        # ---- 结论 ---- #
        self.r_summary = QLabel("—")
        self.r_summary.setWordWrap(True)
        self.r_summary.setStyleSheet(
            f"background:{T.BG_INPUT}; border:1px solid {T.BORDER}; border-radius:8px;"
            f"padding:8px 10px; color:{T.ACCENT}; font-weight:600;")
        card.add(self.r_summary)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.r_func = _mono("功能码 : —", T.TEXT, 11, True)
        self.r_addr = _mono("地址码 : —", T.TEXT, 11, True)
        self.r_magic = _mono("", T.TEXT_DIM, 10)
        grid.addWidget(self.r_func, 0, 0)
        grid.addWidget(self.r_addr, 0, 1)
        grid.addWidget(self.r_magic, 1, 0, 1, 2)
        card.add_layout(grid)

        # ---- 位域表 ---- #
        card.add(section_label("ID 位域拆解"))
        self.bit_table = QTableWidget(0, 4)
        self.bit_table.setHorizontalHeaderLabels(["字段", "位范围", "二进制", "数值 / 含义"])
        self.bit_table.horizontalHeader().setStretchLastSection(True)
        self.bit_table.verticalHeader().setVisible(False)
        self.bit_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.bit_table.setMaximumHeight(170)
        self.bit_table.setMinimumHeight(120)
        for i, w in enumerate((110, 80, 150, 200)):
            self.bit_table.setColumnWidth(i, w)
        card.add(self.bit_table)

        # ---- 数据域位映射 ---- #
        card.add(section_label("数据域 → 通道位映射"))
        self.bit_grid = ByteBitTable()
        card.add(self.bit_grid)

        self.r_ch = _mono("通道 : —", T.TEXT, 11, True)
        card.add(self.r_ch)
        return card

    # ================================================================== #
    # 逻辑
    # ================================================================== #
    def _on_func_changed(self) -> None:
        code = self.func_combo.currentData()
        if code == P.FUNC_WRITE_RELAY:
            self.stack.setCurrentIndex(0)
        elif code in (P.FUNC_READ_RELAY, P.FUNC_READ_INPUT):
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(2)
        self._refresh_preview()

    def build_frame(self) -> Optional[P.CanFrame]:
        """按当前界面参数生成报文。"""
        code = self.func_combo.currentData()
        addr = self.b_addr.value()
        ext = bool(self.b_ext.currentData())

        if code == P.FUNC_WRITE_RELAY:
            chans = P.parse_channel_spec(self.ch_spec.text())
            return P.build_write_relay(addr, chans, ext)
        if code == P.FUNC_READ_RELAY:
            return P.build_read_relay(addr, ext)
        if code == P.FUNC_READ_INPUT:
            return P.build_read_input(addr, ext)

        cmd = self.cfg_combo.currentData()
        if cmd == P.CFG_READ_ADDR:
            return P.build_cfg_read_addr(addr, ext)
        if cmd == P.CFG_READ_BAUD:
            return P.build_cfg_read_baud(addr, ext)
        if cmd == P.CFG_WRITE_ADDR:
            return P.build_cfg_write_addr(addr, self.cfg_addr.value(), ext)
        if cmd == P.CFG_WRITE_BAUD:
            return P.build_cfg_write_baud(addr, int(self.cfg_baud.currentData()), ext)
        return P.build_cfg_write_upload(addr, self.cfg_iv.value(), ext)

    def _refresh_preview(self) -> None:
        if not hasattr(self, "lb_id"):
            return
        f = self.build_frame()
        self._last_built = f
        if f is None:
            self.lb_id.setText("CAN ID  : —")
            self.lb_data.setText("数据域 : —")
            self.lb_slcan.setText("SLCAN  : —")
            return

        self.lb_id.setText(f"CAN ID  : {f.id_text}   ({'扩展帧' if f.extended else '标准帧'})")
        self.lb_data.setText(f"数据域 : {f.data_text}")
        self.lb_slcan.setText(f"SLCAN  : {f.to_slcan()}\\r")

        warns = []
        if f.extended:
            warns.append("扩展帧 ID 含标志字节 0xAA。")
        if self.func_combo.currentData() == P.FUNC_WRITE_RELAY:
            p = P.parse_frame(f)
            n = len(p.raw_channels)
            warns.append(f"将闭合 {n} 路：{P.compress_channel_ranges(p.raw_channels)}")
        if self.func_combo.currentData() == P.FUNC_CONFIG:
            cmd = self.cfg_combo.currentData()
            if cmd in (P.CFG_WRITE_ADDR, P.CFG_WRITE_BAUD):
                warns.append("⚠ 写入后需断电重启模块才生效。")
        self.lb_warn.setText("  ".join(warns))

    # -- 发送 ------------------------------------------------------------ #
    def _send_built(self) -> None:
        if self._last_built is None or not self.ctl.connected:
            return
        self.ctl.send_raw(self._last_built)

    def _copy_built(self) -> None:
        if self._last_built is None:
            return
        f = self._last_built
        QGuiApplication.clipboard().setText(
            f"{f.id_text}  {f.data_text}")

    # -- 解析 ------------------------------------------------------------ #
    def _split_frame_text(self, text: str):
        """把 '0x101 03 00 ...' 拆成 (id文本, 数据文本)。"""
        parts = text.replace(",", " ").split()
        if not parts:
            return "", ""
        return parts[0], " ".join(parts[1:])

    def _paste_frame(self) -> None:
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            return
        id_txt, data_txt = self._split_frame_text(text)
        self.r_id.setText(id_txt)
        if data_txt:
            self.r_data.setText(data_txt)
        # 自动判断标准/扩展
        cid = parse_id_text(id_txt)
        if cid is not None and cid > 0x7FF:
            self.r_ext.setCurrentIndex(1)

    def _fill_demo(self) -> None:
        self.r_ext.setCurrentIndex(0)
        self.r_id.setText("0x101")
        self.r_data.setText("03 00 00 00 00 F0 00 00")

    def _do_resolve(self) -> None:
        raw = self.r_id.text().strip()
        if " " in raw:                       # 粘贴了整帧
            id_txt, data_txt = self._split_frame_text(raw)
            self.r_id.blockSignals(True)
            self.r_id.setText(id_txt)
            self.r_id.blockSignals(False)
            if data_txt:
                self.r_data.blockSignals(True)
                self.r_data.setText(data_txt)
                self.r_data.blockSignals(False)

        cid = parse_id_text(self.r_id.text())
        ext = bool(self.r_ext.currentData())
        data = parse_data_text(self.r_data.text())

        if cid is None:
            self.r_summary.setText("请输入合法的十六进制 CAN ID，例如 0x101 或 0xAA0101")
            self.r_summary.setStyleSheet(
                f"background:{T.BG_INPUT}; border:1px solid {T.ERR}; border-radius:8px;"
                f"padding:8px 10px; color:{T.ERR}; font-weight:600;")
            self.bit_table.setRowCount(0)
            self.r_func.setText("功能码 : —")
            self.r_addr.setText("地址码 : —")
            self.r_magic.setText("")
            self.r_ch.setText("通道 : —")
            return

        parts = P.parse_id(cid, ext)
        frame = P.CanFrame(can_id=cid, data=data or b"", extended=ext)
        parsed = P.parse_frame(frame)

        ok = parts.func_known and not parsed.error
        self.r_summary.setText(parsed.summary() if ok
                               else (parsed.error or f"未知功能码 0x{parts.func:02X}"))
        border = T.ACCENT if ok else T.WARN
        color = T.ACCENT if ok else T.WARN
        self.r_summary.setStyleSheet(
            f"background:{T.BG_INPUT}; border:1px solid {border}; border-radius:8px;"
            f"padding:8px 10px; color:{color}; font-weight:600;")

        self.r_func.setText(f"功能码 : 0x{parts.func:02X}"
                            + (f"  ({parts.func_name})" if ok else "  (未定义)"))
        self.r_addr.setText(f"地址码 : {parts.addr}  (0x{parts.addr:02X})")
        if ext:
            if parts.magic_ok:
                self.r_magic.setText("标志字节 0xAA 校验通过 ✓")
                self.r_magic.setStyleSheet(
                    f"font-family:{T.FONT_MONO}; font-size:10px; color:{T.OK};"
                    f"background:transparent;")
            else:
                got = (cid >> 16) & 0xFF
                self.r_magic.setText(
                    f"⚠ 标志字节应为 0xAA，实际 0x{got:02X} —— 该 ID 不符合本模块协议")
                self.r_magic.setStyleSheet(
                    f"font-family:{T.FONT_MONO}; font-size:10px; color:{T.ERR};"
                    f"background:transparent;")
        else:
            self.r_magic.setText("标准帧：ID 高 3 位为功能码，低 8 位为地址码。")
            self.r_magic.setStyleSheet(
                f"font-family:{T.FONT_MONO}; font-size:10px; color:{T.TEXT_MUTE};"
                f"background:transparent;")

        # 位域表
        rows = parts.bit_rows()
        self.bit_table.setRowCount(len(rows))
        for r, (name, rng, bits, val) in enumerate(rows):
            for col, text in enumerate((name, rng, bits, val)):
                item = QTableWidgetItem(text)
                item.setFont(QFont(T.FONT_MONO, 10))
                if col == 3:
                    item.setForeground(QBrush(QColor(T.ACCENT)))
                elif col == 0:
                    item.setForeground(QBrush(QColor(T.TEXT)))
                else:
                    item.setForeground(QBrush(QColor(T.TEXT_DIM)))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter
                                      if col in (1, 2) else
                                      Qt.AlignmentFlag.AlignLeft
                                      | Qt.AlignmentFlag.AlignVCenter)
                self.bit_table.setItem(r, col, item)

        # 数据域位映射
        self.bit_grid.set_value(data or b"", limit_channels=P.MAX_CHANNELS)
        if parsed.parts.func in (P.FUNC_WRITE_RELAY, P.FUNC_READ_RELAY):
            self.r_ch.setText("闭合通道 : "
                              + P.compress_channel_ranges(parsed.raw_channels))
        elif parsed.parts.func == P.FUNC_READ_INPUT:
            self.r_ch.setText("触发通道 : "
                              + P.compress_channel_ranges(parsed.raw_channels))
        else:
            self.r_ch.setText("通道 : —（参数设置帧无通道数据）")

    def _send_resolved(self) -> None:
        cid = parse_id_text(self.r_id.text())
        if cid is None or not self.ctl.connected:
            return
        data = parse_data_text(self.r_data.text()) or b""
        self.ctl.send_raw(P.CanFrame(can_id=cid, data=data,
                                     extended=bool(self.r_ext.currentData())))

    # ------------------------------------------------------------------ #
    def load_frame(self, frame: P.CanFrame) -> None:
        """由报文监视页双击载入。"""
        self.r_ext.setCurrentIndex(1 if frame.extended else 0)
        self.r_id.setText(frame.id_text)
        self.r_data.setText(frame.data_text)
        self._do_resolve()
