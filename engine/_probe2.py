"""临时分析脚本 2：strings 全局名、WASM 加载方式、套装/弓决候选。"""

import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

V = r"E:\yanyun-gradecalc\engine\vendor"
strings = open(V + r"\leoq7_generated-calc-strings.js", encoding="utf-8").read()
runtime = open(V + r"\leoq7_excel-runtime.js", encoding="utf-8").read()

print("== strings 头 300 字 ==")
print(strings[:300])

print("\n== runtime WASM 加载 ==")
for pat in [r"instantiateStreaming", r"WebAssembly", r"WASM_URL", r"fetch\("]:
    for mm in list(re.finditer(pat, runtime))[:3]:
        s = max(0, mm.start() - 100)
        print(f"-- /{pat}/:", runtime[s: mm.end() + 200].replace("\n", " ")[:300])

print("\n== 弓决/套装候选 ==")
for pat in [r"bowLabels", r"setName", r"套装", r"弓决"]:
    for mm in list(re.finditer(pat, runtime))[:2]:
        s = max(0, mm.start() - 60)
        print(f"-- /{pat}/:", runtime[s: mm.end() + 260].replace("\n", " ")[:320])
