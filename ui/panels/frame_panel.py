"""原始 CAN 帧监视面板（含 SLCAN 原始日志）。"""
from __future__ import annotations

import csv
import time
from collections import deque
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QHeaderView,
                               QLabel, QPlainTextEdit, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from canio import protocol as P
from canio.transport.base import LogLine

from .. import theme as T
from ..widgets import Card

MAX_ROWS = 3000
MAX_LOG_LINES = 2000

HEADERS = ["#", "时间", "方向", "CAN ID", "帧型", "DLC", "数据域 (8 Byte)", "解析"]


class FramePanel(QWidget):
    """报文级 + 字节流级双层监视。"""

    frameActivated = Signal(object)          # 双击某行 -> 交给解析页

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctl = controller
        self._rows: deque[tuple] = deque(maxlen=MAX_ROWS)
        self._pending: list[tuple] = []
        self._paused = False
        self._seq = 0
        self._show_tx = True
        self._show_rx = True
        self._log_lines: deque[str] = deque(maxlen=MAX_LOG_LINES)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        # ---------------- 工具条 ---------------- #
        bar = Card(flat=True)
        row = QHBoxLayout()
        row.setSpacing(9)
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._on_pause)
        self.clear_btn = QPushButton("清空")
        self.export_btn = QPushButton("导出 CSV")
        for b in (self.pause_btn, self.clear_btn, self.export_btn):
            b.setObjectName("Mini")
            row.addWidget(b)

        row.addSpacing(8)
        self.cb_tx = QCheckBox("显示发送 TX")
        self.cb_tx.setChecked(True)
        self.cb_rx = QCheckBox("显示接收 RX")
        self.cb_rx.setChecked(True)
        self.cb_tx.toggled.connect(lambda v: setattr(self, "_show_tx", v))
        self.cb_rx.toggled.connect(lambda v: setattr(self, "_show_rx", v))
        row.addWidget(self.cb_tx)
        row.addWidget(self.cb_rx)

        self.autoscroll = QCheckBox("自动滚动")
        self.autoscroll.setChecked(True)
        row.addWidget(self.autoscroll)

        row.addStretch(1)
        self.count_lbl = QLabel("共 0 帧")
        self.count_lbl.setObjectName("Mono")
        row.addWidget(self.count_lbl)
        bar.add_layout(row)
        root.addWidget(bar)

        # ---------------- 分割：帧表 + ASCII 日志 ---------------- #
        split = QSplitter(Qt.Orientation.Vertical)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        hh = self.table.horizontalHeader()
        widths = [52, 124, 62, 96, 70, 48, 230, 280]
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)
        hh.setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        split.addWidget(self.table)

        logw = QWidget()
        lv = QVBoxLayout(logw)
        lv.setContentsMargins(0, 6, 0, 0)
        lv.setSpacing(5)
        head = QHBoxLayout()
        lab = QLabel("SLCAN / 传输层原始日志")
        lab.setObjectName("SectionLabel")
        head.addWidget(lab)
        head.addStretch(1)
        self.auto_log = QCheckBox("记录")
        self.auto_log.setChecked(True)
        head.addWidget(self.auto_log)
        self.clear_log_btn = QPushButton("清空日志")
        self.clear_log_btn.setObjectName("Mini")
        self.clear_log_btn.clicked.connect(self._clear_log)
        head.addWidget(self.clear_log_btn)
        lv.addLayout(head)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(MAX_LOG_LINES)
        self.log_view.setPlaceholderText("此处显示与调试器之间的原始 ASCII 交互 …")
        lv.addWidget(self.log_view)
        split.addWidget(logw)
        split.setSizes([430, 190])
        root.addWidget(split, 1)

        # 批量刷新定时器（高频报文下保护界面）
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(70)
        self._flush_timer.timeout.connect(self._flush)
        self._flush_timer.start()

    # ------------------------------------------------------------------ #
    def _on_pause(self, paused: bool) -> None:
        self.pause_btn.setText("继续" if paused else "暂停")
        self._paused = paused

    def _clear_log(self) -> None:
        self._log_lines.clear()
        self.log_view.clear()

    def clear(self) -> None:
        self._rows.clear()
        self._pending.clear()
        self.table.setRowCount(0)
        self.count_lbl.setText("共 0 帧")

    # ------------------------------------------------------------------ #
    # 数据入口
    # ------------------------------------------------------------------ #
    def on_frame(self, frame: P.CanFrame, parsed: P.ParsedFrame) -> None:
        if self._paused:
            return
        if frame.tx and not self._show_tx:
            return
        if (not frame.tx) and not self._show_rx:
            return
        self._pending.append((frame, parsed))

    def on_log(self, line: LogLine) -> None:
        if not self.auto_log.isChecked():
            return
        if self._paused:
            return
        colour = {"TX": "#C4B5FD", "RX": "#7DD3FC", "SYS": "#94A3B8"}.get(
            line.direction, "#94A3B8")
        stamp = time.strftime("%H:%M:%S")
        extra = f"   « {line.detail}" if line.detail else ""
        html = (f"<span style='color:#64748B'>{stamp}</span> "
                f"<span style='color:{colour};font-weight:600'>[{line.direction}]</span> "
                f"<span style='color:#CBD5E1'>{self._esc(line.text)}</span>"
                f"<span style='color:#64748B'>{self._esc(extra)}</span>")
        self.log_view.appendHtml(html)

    @staticmethod
    def _esc(s: str) -> str:
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    # ------------------------------------------------------------------ #
    def _flush(self) -> None:
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        table = self.table
        table.setUpdatesEnabled(False)
        try:
            for frame, parsed in batch:
                self._seq += 1
                self._append_row(frame, parsed, self._seq)
            # 裁剪超出上限的行
            excess = table.rowCount() - MAX_ROWS
            if excess > 0:
                for _ in range(excess):
                    table.removeRow(0)
            self.count_lbl.setText(f"共 {self._seq} 帧")
            if self.autoscroll.isChecked():
                table.scrollToBottom()
        finally:
            table.setUpdatesEnabled(True)

    def _append_row(self, frame: P.CanFrame, parsed: P.ParsedFrame, seq: int) -> None:
        t = self.table
        r = t.rowCount()
        t.insertRow(r)

        is_tx = frame.tx
        accent = T.TX if is_tx else T.RX
        ts = frame.timestamp if frame.timestamp else time.time()
        tstamp = time.strftime("%H:%M:%S", time.localtime(ts))
        sub = int((ts % 1) * 1000)
        parsed_ok = not parsed.error and parsed.parts.func_known

        cells = [
            (str(seq), T.TEXT_MUTE, False),
            (f"{tstamp}.{sub:03d}", T.TEXT_DIM, False),
            ("发送 ▲" if is_tx else "接收 ▼", accent, True),
            (frame.id_text, T.ACCENT if not is_tx else "#C4B5FD", True),
            ("扩展帧" if frame.extended else "标准帧", T.TEXT_DIM, False),
            (str(frame.dlc), T.TEXT_DIM, False),
            (frame.data_text, T.TEXT, True),
            (parsed.summary() if parsed_ok else (parsed.error or "—"),
             T.TEXT_DIM if parsed_ok else T.ERR, False),
        ]
        for col, (text, colour, mono) in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setForeground(QBrush(QColor(colour)))
            f = QFont(T.FONT_MONO if mono else T.FONT_UI, 10)
            if col == 2:
                f.setBold(True)
            item.setFont(f)
            if col in (0, 2, 4, 5):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if not parsed_ok and col == 7:
                item.setToolTip(parsed.error)
            if col == 4:
                item.setToolTip(parsed.parts.func_name if parsed_ok else "")
            t.setItem(r, col, item)

    def _on_double_click(self, item: QTableWidgetItem) -> None:
        row = item.row()
        # 序号列存在时用序号定位；这里直接按表内行号回溯
        if 0 <= row < self.table.rowCount():
            idtext = self.table.item(row, 3)
            dtext = self.table.item(row, 6)
            if idtext and dtext:
                try:
                    can_id = int(idtext.text(), 16)
                except ValueError:
                    return
                extended = self.table.item(row, 4).text() == "扩展帧"
                data = bytes.fromhex(dtext.text().replace(" ", ""))
                self.frameActivated.emit(
                    P.CanFrame(can_id=can_id, data=data, extended=extended))

    # ------------------------------------------------------------------ #
    def export_csv(self) -> Optional[str]:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出报文记录", "canio_frames.csv", "CSV 文件 (*.csv)")
        if not path:
            return None
        t = self.table
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(HEADERS)
            for r in range(t.rowCount()):
                w.writerow([t.item(r, c).text() if t.item(r, c) else ""
                            for c in range(t.columnCount())])
        return path
