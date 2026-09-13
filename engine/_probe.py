"""临时分析脚本：探查 META/strings 里的流派、心法、套装、弓决与基准数据。"""

import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

V = r"E:\yanyun-gradecalc\engine\vendor"

meta = open(V + r"\leoq7_generated-calc-metadata.js", encoding="utf-8").read()
strings = open(V + r"\leoq7_generated-calc-strings.js", encoding="utf-8").read()

print("== metadata 顶层键 ==")
m = re.search(r"YYSLS_CALC_METADATA\s*=\s*\{", meta)
keys = re.findall(r"[\"']?(\w+)[\"']?\s*:", meta[m.end(): m.end() + 4000])
seen = []
for k in keys:
    if k not in seen:
        seen.append(k)
print(seen)

for key in ("classRotationStats", "flowIds", "classSetFields", "classXinfaFields", "flowNames"):
    mk = re.search(rf"[\"']?{key}[\"']?\s*:\s*(\{{|\[)", meta)
    if mk:
        seg = meta[mk.start(): mk.start() + 700]
        print(f"\n== {key} ==\n{seg[:700]}")

print("\n== strings 中的选项列表 ==")
sm = re.search(r"YYSLS_CALC_STRING_IDS\s*=\s*\{", strings)
body = strings[sm.end():]
# 抓所有数组字面量的键名
arrs = re.findall(r"[\"']?(\w+)[\"']?\s*:\s*\[", body)
print("数组键:", sorted(set(arrs))[:40])
# 心法/套装候选
for kw in ("心法", "套装", "弓决", "易水歌", "沧海帖", "易相", "玉斗"):
    hits = [mm.start() for mm in re.finditer(kw, body)][:1]
    for h in hits:
        print(f"-- {kw} @ {h}: …{body[max(0,h-80):h+320]}…".replace("\\n", " ")[:420])
