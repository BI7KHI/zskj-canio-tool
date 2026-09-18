"""
CANIO 继电器调试台 —— 程序入口
================================================================

用法::

    python app.py                 # 直接运行
    python app.py --selftest      # 跑一遍协议自检后退出

打包::

    python build.py               # 生成 dist/CANIO调试台.exe
"""
from __future__ import annotations

import os
import sys

# 允许以「源码目录」或「打包后 exe」两种方式导入本包
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _run_selftest() -> int:
    """执行 tests/ 下的自检脚本。"""
    import subprocess
    tests = ["tests/test_protocol.py", "tests/test_session.py",
             "tests/test_docs.py"]
    rc = 0
    for t in tests:
        path = os.path.join(_HERE, t)
        if not os.path.exists(path):
            continue
        print(f"\n===== {t} =====")
        r = subprocess.run([sys.executable, path], cwd=_HERE)
        rc = rc or r.returncode
    return rc


def _run_check(outfile: str) -> int:
    """
    打包自检：把关键依赖与协议自检结果写成 JSON。

    因为 --noconsole 的 exe 没有 stdout，只能靠输出文件来确认打包是否完整。
    """
    import json
    import platform
    report: dict = {"python": sys.version, "platform": platform.platform(),
                    "frozen": bool(getattr(sys, "frozen", False))}
    try:
        from PySide6 import __version__ as pyside_ver
        report["pyside6"] = pyside_ver
    except Exception as exc:                          # pragma: no cover
        report["pyside6"] = f"FAIL: {exc}"
    try:
        import serial
        report["pyserial"] = serial.__version__
    except Exception as exc:
        report["pyserial"] = f"FAIL: {exc}"
    try:
        from canio import protocol as P
        f = P.build_write_relay(1, {1, 2, 45, 46, 47, 48})
        report["protocol"] = "OK"
        report["protocol_sample_id"] = f.id_text
        report["protocol_sample_data"] = f.data_text
        report["protocol_ok"] = (f.id_text == "0x101"
                                 and f.data_text == "03 00 00 00 00 F0 00 00")
    except Exception as exc:
        report["protocol"] = f"FAIL: {exc}"
        report["protocol_ok"] = False
    try:
        from canio.transport import (HAVE_PCAN, HAVE_SLCAN,
                                     SimulatorTransport, list_serial_ports)
        t = SimulatorTransport()
        t.open()
        t.close()
        report["transport_slcan"] = HAVE_SLCAN
        report["transport_pcan"] = HAVE_PCAN
        report["transport_sim"] = "OK"
        report["serial_ports"] = [p[0] for p in list_serial_ports()]
    except Exception as exc:
        report["transport_sim"] = f"FAIL: {exc}"
    try:
        from ui.main_window import MainWindow          # noqa: F401
        report["ui_import"] = "OK"
    except Exception as exc:
        report["ui_import"] = f"FAIL: {exc}"
    try:
        with open(outfile, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
    except Exception:
        return 3
    return 0 if report.get("protocol_ok") and report.get("ui_import") == "OK" else 4


def main() -> int:
    if "--selftest" in sys.argv:
        return _run_selftest()

    if "--check" in sys.argv:
        i = sys.argv.index("--check")
        out = sys.argv[i + 1] if len(sys.argv) > i + 1 else "canio_check.json"
        # 有窗口环境下也能跑：用 offscreen 平台避免弹窗
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            _app = QApplication.instance() or QApplication([])
        except Exception:
            _app = None
        return _run_check(out)

    try:
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:                       # pragma: no cover
        print("缺少 PySide6，请先执行：  pip install PySide6", file=sys.stderr)
        print(f"（{exc}）", file=sys.stderr)
        return 2

    # Qt6 默认已启用高 DPI 缩放，无需再设置 AA_UseHighDpiPixmaps
    app = QApplication(sys.argv)
    app.setApplicationName("CANIO 继电器调试台")
    app.setApplicationDisplayName("CANIO 继电器调试台")
    app.setOrganizationName("CANIO Tools")
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from ui.theme import apply_theme
    from ui.main_window import MainWindow

    apply_theme(app)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
