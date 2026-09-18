"""
打包脚本 —— 生成单文件绿色 EXE
================================================================

用法::

    python build.py              # 完整打包
    python build.py --clean      # 只清理构建产物
    python build.py --no-verify  # 打包后跳过自检

产物:  ``dist/CANIO继电器调试台.exe``  （单文件，双击即用，无需安装 Python）
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "CANIO继电器调试台"
ENTRY = os.path.join(ROOT, "app.py")
ICON = os.path.join(ROOT, "assets", "app.ico")
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")

#: 精简掉用不到的 Qt 模块与第三方库，显著缩小体积
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.QtQml", "PySide6.QtQmlModels", "PySide6.QtQmlWorkerScript",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtLocation", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtRemoteObjects", "PySide6.QtSensors",
    "PySide6.QtTextToSpeech", "PySide6.QtUiTools", "PySide6.QtSvgWidgets",
    "PySide6.QtSerialBus", "PySide6.QtSerialPort", "PySide6.QtNetwork",
    "PySide6.QtConcurrent", "PySide6.QtXml", "PySide6.QtDBus",
    # 系统里装了但本项目用不到的重量级库
    "matplotlib", "numpy", "pandas", "scipy", "PIL", "cv2", "onnxruntime",
    "tkinter", "unittest", "pydoc", "doctest", "pytest", "IPython",
    "pythonnet", "clr_loader", "pywebview", "Flask", "jinja2",
    "opencv-python", "rapidocr_onnxruntime", "pymupdf", "fitz",
]

HIDDEN = [
    "serial",
    "serial.tools",
    "serial.tools.list_ports",
    "serial.serialwin32",
    "canio.transport.pcan",
]


def clean() -> None:
    for d in (DIST, BUILD):
        if os.path.isdir(d):
            print(f"  清理 {d}")
            shutil.rmtree(d, ignore_errors=True)
    for f in os.listdir(ROOT):
        if f.endswith(".spec"):
            os.remove(os.path.join(ROOT, f))


def build() -> str:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--noconsole",
        "--name", APP_NAME,
        "--distpath", DIST,
        "--workpath", BUILD,
        "--specpath", BUILD,
    ]
    if os.path.exists(ICON):
        args += ["--icon", ICON]
        # 运行时也要能读到图标（用于窗口图标）
        args += ["--add-data", f"{ICON}{os.pathsep}assets"]
    for m in EXCLUDES:
        args += ["--exclude-module", m]
    for m in HIDDEN:
        args += ["--hidden-import", m]
    # 保证以项目根为导入根
    args += ["--paths", ROOT]
    args.append(ENTRY)

    print("\n  执行 PyInstaller …\n")
    t0 = time.time()
    proc = subprocess.run(args, cwd=ROOT)
    if proc.returncode != 0:
        print("\n  ✗ PyInstaller 失败", file=sys.stderr)
        sys.exit(proc.returncode)

    exe = os.path.join(DIST, APP_NAME + ".exe")
    if not os.path.exists(exe):
        # 有些环境会给中文名做替换，兜底找一下
        cands = [f for f in os.listdir(DIST) if f.lower().endswith(".exe")]
        if not cands:
            print("  ✗ 未找到生成的 exe", file=sys.stderr)
            sys.exit(1)
        exe = os.path.join(DIST, cands[0])

    print(f"\n  ✓ 打包完成，用时 {time.time() - t0:.1f}s")
    print(f"    {exe}   ({os.path.getsize(exe) / 1048576:.1f} MB)")
    return exe


def verify(exe: str) -> bool:
    """运行 exe 的 --check 模式，确认依赖与协议层在打包环境下正常。"""
    import json
    out = os.path.join(BUILD, "check.json")
    os.makedirs(BUILD, exist_ok=True)
    if os.path.exists(out):
        os.remove(out)
    print("\n  运行打包自检（--check）…")
    try:
        r = subprocess.run([exe, "--check", out], timeout=180)
    except subprocess.TimeoutExpired:
        print("  ✗ 自检超时", file=sys.stderr)
        return False
    if not os.path.exists(out):
        print(f"  ✗ 未生成自检报告（exit={r.returncode}）", file=sys.stderr)
        return False
    with open(out, encoding="utf-8") as fh:
        rep = json.load(fh)
    ok = rep.get("protocol_ok") and rep.get("ui_import") == "OK"
    print(f"    Python      : {rep.get('python','')[:40]}")
    print(f"    冻结包      : {rep.get('frozen')}")
    print(f"    PySide6     : {rep.get('pyside6')}")
    print(f"    pyserial    : {rep.get('pyserial')}")
    print(f"    协议层      : {rep.get('protocol')}  "
          f"({rep.get('protocol_sample_id')} {rep.get('protocol_sample_data')})")
    print(f"    UI 导入     : {rep.get('ui_import')}")
    print(f"    SLCAN/PCAN/模拟器: {rep.get('transport_slcan')} / "
          f"{rep.get('transport_pcan')} / {rep.get('transport_sim')}")
    print(f"    串口        : {rep.get('serial_ports')}")
    print(f"    => {'自检通过 ✔' if ok else '自检失败 ✗'}")
    return bool(ok)


def main() -> int:
    if "--clean" in sys.argv:
        clean()
        print("  已清理。")
        return 0

    print("=" * 70)
    print(f"  打包 {APP_NAME}")
    print("=" * 70)
    clean()
    exe = build()
    if "--no-verify" not in sys.argv:
        if not verify(exe):
            print("\n  ⚠ 自检未通过，请检查上面的输出。", file=sys.stderr)
            return 4
    print("\n" + "=" * 70)
    print(f"  完成：{exe}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
