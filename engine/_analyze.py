"""临时分析脚本：解析 excel-runtime.js 的 API 面与数据来源。"""

import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

JS = r"E:\yanyun-gradecalc\engine\vendor\leoq7_excel-runtime.js"
js = open(JS, encoding="utf-8").read()

rm = re.search(r"const\s+runtime\s*=\s*\{", js)
print("== runtime 对象体（前 1100 字）==")
print(js[rm.start(): rm.start() + 1100].replace("\n", " "))

for pat in [r"function calculate\(", r"function collectBonuses", r"rotation\s*=|rotation\.baseline",
            r"getRotation\w*", r"ROTATIONS", r"equippedItems", r"mainStat", r"subStats"]:
    ms = list(re.finditer(pat, js))
    print(f"\n### /{pat}/ x{len(ms)}")
    for mm in ms[:3]:
        s = max(0, mm.start() - 140)
        print("  …", js[s: mm.end() + 240].replace("\n", " ")[:380])
