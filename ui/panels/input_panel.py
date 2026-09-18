"""输入通道监视面板。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .. import theme as T
from ..widgets import Card, InputTile

COLS = 8
CHANNEL_CHOICES = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48]


class InputPanel(QWidget):
    """数字量输入（X 端子）触发状态监视。"""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctl = controller
        self._count = 4
        self._tiles: dict[int, InputTile] = {}
        self._active: set[int] = set()
        self._history: list[set[int]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        bar = Card(flat=True)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("输入路数"))
        self.count_combo = QComboBox()
        for n in CHANNEL_CHOICES:
            self.count_combo.addItem(f"{n} 路", n)
        self.count_combo.setCurrentText("4 路")
        self.count_combo.setFixedWidth(88)
        self.count_combo.currentIndexChanged.connect(self._on_count_changed)
        row.addWidget(self.count_combo)

        row.addSpacing(10)
        self.read_btn = QPushButton("立即读取")
        self.clear_btn = QPushButton("清零计数")
        for b in (self.read_btn, self.clear_btn):
            b.setObjectName("Mini")
            row.addWidget(b)
        self.read_btn.clicked.connect(lambda: self.ctl.read_inputs())
        self.clear_btn.clicked.connect(self._clear_counts)

        row.addStretch(1)
        self.summary = QLabel("触发 0 / 共 4")
        self.summary.setObjectName("Mono")
        row.addWidget(self.summary)
        bar.add_layout(row)
        root.addWidget(bar)

        card = Card("输入通道状态",
                    "Bit=1 表示该路已触发（外部开关导通）；对应功能码 0x03")
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.grid.setSpacing(9)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.grid_host)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        card.body.addWidget(scroll)
        card.body.setStretch(0, 1)
        root.addWidget(card, 1)

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
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._tiles.clear()
        for ch in range(1, self._count + 1):
            tile = InputTile(ch)
            r, c = divmod(ch - 1, COLS)
            self.grid.addWidget(tile, r, c)
            self._tiles[ch] = tile
        self.sync(self._active)
        self._update_summary()

    # ------------------------------------------------------------------ #
    def sync(self, channels) -> None:
        chs = set(channels)
        changed = chs != self._active
        self._active = chs
        for ch, tile in self._tiles.items():
            tile.set_active(ch in chs)
        if changed:
            self._history.append(set(chs))
            if len(self._history) > 500:
                del self._history[:100]
        self._update_summary()

    def _clear_counts(self) -> None:
        for t in self._tiles.values():
            t.reset_count()

    def _update_summary(self) -> None:
        n = len([c for c in self._active if 1 <= c <= self._count])
        self.summary.setText(f"触发 {n} / 共 {self._count}")
        self.summary.setStyleSheet(
            f"color:{T.ACCENT if n else T.TEXT_MUTE}; font-family:{T.FONT_MONO};"
            f"font-weight:700;")
