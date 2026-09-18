"""继电器控制面板。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .. import theme as T
from ..widgets import Card, RelayTile, hint_label, section_label

COLS = 8

#: 可选继电器路数（受 CAN 数据域 6 字节 = 48 路限制）
CHANNEL_CHOICES = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48]


class RelayPanel(QWidget):
    """继电器吸合状态与批量控制。"""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctl = controller
        self._count = 4
        self._tiles: dict[int, RelayTile] = {}
        self._limit = 4                    # 界面只显示前 N 路
        self._desired: set[int] = set()
        self._writing = False
        self._dirty = False

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        # ---------------- 工具条 ---------------- #
        bar = Card(flat=True)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("继电器路数"))
        self.count_combo = QComboBox()
        for n in CHANNEL_CHOICES:
            self.count_combo.addItem(f"{n} 路", n)
        self.count_combo.setCurrentText("4 路")
        self.count_combo.setFixedWidth(88)
        self.count_combo.currentIndexChanged.connect(self._on_count_changed)
        row.addWidget(self.count_combo)

        row.addSpacing(10)
        self.all_on_btn = QPushButton("全部闭合")
        self.all_off_btn = QPushButton("全部断开")
        self.invert_btn = QPushButton("状态取反")
        self.read_btn = QPushButton("读取状态")
        self.read_btn.setObjectName("Mini")
        for b in (self.all_on_btn, self.all_off_btn, self.invert_btn):
            b.setObjectName("Mini")
        self.all_on_btn.clicked.connect(lambda: self._apply(set(range(1, self._count + 1))))
        self.all_off_btn.clicked.connect(lambda: self._apply(set()))
        self.invert_btn.clicked.connect(self._invert)
        self.read_btn.clicked.connect(lambda: self.ctl.read_relays())
        for b in (self.all_on_btn, self.all_off_btn, self.invert_btn, self.read_btn):
            row.addWidget(b)

        row.addStretch(1)
        self.summary = QLabel("闭合 0 / 共 4")
        self.summary.setObjectName("Mono")
        self.summary.setStyleSheet(
            f"color:{T.OK}; font-family:{T.FONT_MONO}; font-weight:700;")
        row.addWidget(self.summary)
        bar.add_layout(row)
        root.addWidget(bar)

        # ---------------- 磁贴网格 ---------------- #
        grid_card = Card("继电器吸合状态",
                         "点击通道卡片即可吸合 / 断开；对应功能码 0x01")
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.grid.setSpacing(9)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop
                               | Qt.AlignmentFlag.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.grid_host)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        grid_card.body.addWidget(scroll)
        grid_card.body.setStretch(0, 1)
        root.addWidget(grid_card, 1)

        self.rebuild()

    # ------------------------------------------------------------------ #
    @property
    def channel_count(self) -> int:
        return self._count

    def set_channel_count(self, n: int) -> None:
        idx = self.count_combo.findData(n)
        if idx >= 0 and idx != self.count_combo.currentIndex():
            self.count_combo.setCurrentIndex(idx)
        else:
            self._count = n
            self.rebuild()

    def _on_count_changed(self) -> None:
        self._count = int(self.count_combo.currentData())
        self.rebuild()

    def rebuild(self) -> None:
        """按当前路数重建磁贴网格。"""
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._tiles.clear()

        for ch in range(1, self._count + 1):
            tile = RelayTile(ch)
            tile.toggled_by_user.connect(self._on_tile_toggled)
            r, c = divmod(ch - 1, COLS)
            self.grid.addWidget(tile, r, c)
            self._tiles[ch] = tile
        self._desired = {ch for ch in self._desired if 1 <= ch <= self._count}
        self.sync_tiles(self._desired)
        self._update_summary()

    # ------------------------------------------------------------------ #
    def _on_tile_toggled(self, channel: int, on: bool) -> None:
        """用户点击通道 -> 立即乐观更新，并把「整组目标状态」下发给模块。"""
        if on:
            self._desired.add(channel)
        else:
            self._desired.discard(channel)
        self._update_summary()
        self._queue_write()

    def _apply(self, channels: set[int]) -> None:
        self._desired = {c for c in channels if 1 <= c <= self._count}
        self.sync_tiles(self._desired)
        self._update_summary()
        self._queue_write()

    def _invert(self) -> None:
        self._desired = set(range(1, self._count + 1)) - self._desired
        self.sync_tiles(self._desired)
        self._update_summary()
        self._queue_write()

    # ------------------------------------------------------------------ #
    def _queue_write(self) -> None:
        """
        串行化写入并合并连续点击。

        始终只保留「最后一次」的目标状态：写入进行中时仅置脏标记，
        写完后若状态又变则再发一次。这样既保证最终状态与界面一致，
        也避免多次点击产生的报文乱序。
        """
        if self._writing:
            self._dirty = True
            return
        if not self.ctl.connected:
            return
        self._writing = True
        target = set(self._desired)
        self.ctl.set_relays(target, on_done=lambda *_: self._write_finished())

    def _write_finished(self) -> None:
        self._writing = False
        if self._dirty:
            self._dirty = False
            self._queue_write()

    # ------------------------------------------------------------------ #
    def sync_tiles(self, channels) -> None:
        """按模块回报的状态刷新磁贴（不触发信号）。"""
        chs = set(channels)
        for ch, tile in self._tiles.items():
            want = ch in chs
            if tile.isChecked() != want:
                tile.blockSignals(True)
                tile.setChecked(want)
                tile.blockSignals(False)
                tile.update()
        self._desired = {c for c in chs if 1 <= c <= self._count}
        self._update_summary()

    def _update_summary(self) -> None:
        n = len([c for c in self._desired if 1 <= c <= self._count])
        self.summary.setText(f"闭合 {n} / 共 {self._count}")
        self.summary.setStyleSheet(
            f"color:{T.OK if n else T.TEXT_MUTE}; font-family:{T.FONT_MONO};"
            f"font-weight:700;")

    def set_enabled_state(self, enabled: bool) -> None:
        for b in (self.all_on_btn, self.all_off_btn, self.invert_btn,
                  self.read_btn, self.count_combo):
            b.setEnabled(True)
