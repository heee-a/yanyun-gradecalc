"""从 yysls.leoq7.com 管理器导出的数据文件更新本工具的数据。

数据来源（需先手工下载到 source_data/）：
  - site_max_values.json : 站点 app.min.js 内 MAX_VALUES（110阶词条满值，权威）
  - site_best40.json     : 站点 generated-best40-stats.js（各流派最优40词条分布）

用法: python scripts/update_from_site.py
效果: 更新 data/affix_max.json；用 best40 分布重写 builds/<流派>.json
     （已有计算器导入的流派保留 panel_stats，仅替换权重）。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "source_data"
DATA = ROOT / "data"
BUILDS = ROOT / "builds"


def main() -> None:
    maxes = json.loads((SRC / "site_max_values.json").read_text(encoding="utf-8"))
    best40 = json.loads((SRC / "site_best40.json").read_text(encoding="utf-8"))

    # ---- 1) 满值表 ----
    out_max = {
        "_meta": {
            "name": "110阶词条满值表",
            "source": "yysls.leoq7.com 装备毕业率管理器 (app.min.js MAX_VALUES)，2026-09 提取",
            "note": "数值为普通副词条满值；[转]词条与特定词条实测可略超满值，计算时封顶 100%。"
                    "指定武学技能类（如 无名剑法·蓄力技增伤）按“指定武学技能增伤”满值兜底",
        },
        "max": dict(sorted(maxes.items(), key=lambda x: -x[1])),
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "affix_max.json").write_text(
        json.dumps(out_max, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"affix_max.json: {len(maxes)} 条满值")

    # ---- 2) 流派权重（best40 分布 -> 归一化权重） ----
    BUILDS.mkdir(exist_ok=True)
    updated = []
    for build_name, entries in best40.items():
        counts: dict[str, float] = {}
        for e in entries:
            for k, c in e["statCounts"].items():
                counts[k] = counts.get(k, 0) + c
        total = sum(counts.values())
        weights = {k: round(c / total, 3) for k, c in sorted(counts.items(), key=lambda x: -x[1])}

        path = BUILDS / f"{build_name}.json"
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        data = {
            "name": build_name,
            "source_file": old.get("source_file", f"yysls.leoq7.com best40 ({len(entries)} 组)"),
            "weights_source": f"yysls.leoq7.com best40 最优配置词条分布（{total} 条）",
            "panel_stats": old.get("panel_stats", []),
            "affix_weights": weights,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        updated.append(build_name)
    print(f"builds/: {len(updated)} 个流派已按 best40 更新 -> {', '.join(updated)}")


if __name__ == "__main__":
    main()
