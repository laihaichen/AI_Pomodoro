#!/usr/bin/env python3
"""
output_all_python.py
导出项目根目录及其子目录下所有 .py 文件（排除自身）到 all_python_code.txt
"""

import pathlib

ROOT = pathlib.Path(__file__).parent.resolve()
OUTPUT = ROOT / "all_python_code.txt"
SELF = pathlib.Path(__file__).resolve()

py_files = sorted(
    p for p in ROOT.rglob("*.py")
    if p.resolve() != SELF
)

with OUTPUT.open("w", encoding="utf-8") as out:
    for py in py_files:
        rel = py.relative_to(ROOT)
        out.write("=" * 72 + "\n")
        out.write(f"FILE: {rel}\n")
        out.write("=" * 72 + "\n")
        try:
            out.write(py.read_text(encoding="utf-8"))
        except Exception as e:
            out.write(f"[读取失败: {e}]\n")
        out.write("\n\n")

print(f"✅ 已导出 {len(py_files)} 个文件 → {OUTPUT}")
