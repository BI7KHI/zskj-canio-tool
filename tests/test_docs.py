"""
文档一致性自检：把 docs/PROTOCOL.md 里出现的报文示例逐条跑一遍。
运行: python tests/test_docs.py

这样文档一旦和代码脱节（例如改了 ID 构造或数据域映射），测试会立刻失败。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from canio import protocol as P      # noqa: E402

DOC = os.path.join(ROOT, "docs", "PROTOCOL.md")
FAIL = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAIL.append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"          got = {got!r}")
        print(f"          want= {want!r}")


def check_true(label, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAIL.append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  {extra}" if extra else ""))


text = open(DOC, encoding="utf-8").read()
print(f"读取 {os.path.relpath(DOC, ROOT)}  ({len(text)} 字符)")

# --------------------------------------------------------------------------- #
# 1) 校验「完整报文示例」表格里的每一行
# --------------------------------------------------------------------------- #
print()
print("=" * 74)
print("1) §8 完整报文示例 —— 与 canio.protocol 往返核对")
print("=" * 74)

# ```0x101` `03 00 00 ... ```
FRAME_RE = re.compile(
    r"`(0x[0-9A-Fa-f]+)`\s*`((?:[0-9A-Fa-f]{2}\s*){8})`")

section = text.split("## 8. 完整报文示例", 1)
body = section[1].split("## 9.", 1)[0] if len(section) > 1 else ""

rows = []
for line in body.splitlines():
    if not line.strip().startswith("|"):
        continue
    cols = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cols) < 3:
        continue
    scene, ftype, payload = cols[0], cols[1], cols[2]
    if "标准帧" not in ftype and "扩展帧" not in ftype:
        continue
    m = FRAME_RE.search(payload)
    if not m:
        continue
    rows.append((scene, ("扩展帧" in ftype), m.group(1),
                 bytes.fromhex(m.group(2).replace(" ", ""))))

check_true("从文档解析到报文示例", len(rows) >= 8, f"共 {len(rows)} 条")

for scene, ext, id_text, data in rows:
    can_id = int(id_text, 16)
    label = f"{scene} · {'扩展帧' if ext else '标准帧'} · {id_text}"
    # a) ID 能拆回 功能码 + 地址，且能重新合成
    parts = P.parse_id(can_id, ext)
    ok_id = (P.make_id(parts.func, parts.addr, ext) == can_id)
    ok_func = parts.func in P.FUNC_NAMES
    ok_data = len(data) == 8
    ok_parse = not P.parse_frame(P.CanFrame(can_id=can_id, data=data,
                                            extended=ext)).error
    # b) 扩展帧标志字节必须是 0xAA
    ok_magic = (not ext) or parts.magic_ok
    good = ok_id and ok_func and ok_data and ok_parse and ok_magic
    if not good:
        FAIL.append(label)
    detail = []
    if not ok_id:
        detail.append("ID 不可逆")
    if not ok_func:
        detail.append(f"未知功能码 0x{parts.func:02X}")
    if not ok_data:
        detail.append(f"数据域 {len(data)} 字节")
    if not ok_magic:
        detail.append("扩展帧标志非 0xAA")
    print(f"  [{'PASS' if good else 'FAIL'}] {label}"
          f"  ->  {parts.func_name} / 地址 {parts.addr}"
          + (f"  ⚠ {'; '.join(detail)}" if detail else ""))

# --------------------------------------------------------------------------- #
# 2) 校验 SLCAN 转换示例
# --------------------------------------------------------------------------- #
print()
print("=" * 74)
print("2) §9.1 SLCAN 转换示例")
print("=" * 74)


def slcan_of(label_id: str, ext: bool, data_hex: str) -> str:
    f = P.CanFrame(can_id=int(label_id, 16),
                   data=bytes.fromhex(data_hex.replace(" ", "")),
                   extended=ext)
    return f.to_slcan()


check("标准帧 0x101 03 00 00 00 00 F0 00 00",
      slcan_of("0x101", False, "0300000000F00000"),
      "t1010300000000F00000")
check("扩展帧 0xAA0101 03 00 00 00 00 F0 00 00",
      slcan_of("0xAA0101", True, "0300000000F00000"),
      "T00AA01010300000000F00000")

# 文档里出现的 SLCAN 字符串必须真的能被解析回来
for s in re.findall(r"`([tT][0-9A-Fa-f]{3,8}[0-9A-Fa-f]{16})`", body):
    f = P.frame_from_slcan(s)
    back = f.to_slcan() if f else None
    check(f"文档中的 SLCAN 串可往返: {s}", back, s)

# --------------------------------------------------------------------------- #
# 3) 校验文档正文里写到的关键事实
# --------------------------------------------------------------------------- #
print()
print("=" * 74)
print("3) 正文关键事实核对")
print("=" * 74)

# 「写地址用原地址回复」——用例已在 test_protocol 覆盖，这里核对文档确实写了
check_true("文档说明了『写参数用原地址回复』",
           "仍然用旧地址应答" in text or "原地址" in text)

# 扩展帧 ID 显示位数的说明必须存在（工具显示 8 位，手册写 6 位）
check_true("文档说明了扩展帧 ID 的补零差异",
           "关于 ID 的书写位数" in text)

# 波特率：500kbps = 0x09，且指出手册笔误
check_true("文档指出手册 500kbps 扩展帧示例是笔误",
           "笔误" in text)
check("代码里 0x09 = 500 kbps", P.BAUD_CODE_TO_BPS[0x09], 500_000)
check("代码里 0x06 = 200 kbps", P.BAUD_CODE_TO_BPS[0x06], 200_000)

# 主动上传间隔大端
check_true("文档说明主动上传间隔是大端",
           "大端" in text)
f = P.build_cfg_write_upload(1, 10)
check("代码 B3 帧为大端 00 0A",
      f.data_text, "B3 00 0A 00 00 00 00 00")

# 完整 48 路映射表存在
check_true("文档包含 48 路位映射表", text.count("| Bit0 |") >= 3)

print()
print("=" * 74)
if FAIL:
    print(f"结果: {len(FAIL)} 项失败")
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print("结果: 全部通过 ✔  文档与代码一致")
