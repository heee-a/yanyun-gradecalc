"""毕业度计算：词条得分 = 数值 / 满值(110阶)，按流派权重加权。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .ocr import Affix, Piece
from .stats_dict import stat_type

# 毕业档位阈值（可按习惯调整）
GRADES = [(90.0, "毕业"), (80.0, "准毕业"), (70.0, "可用"), (0.0, "过渡")]


def grade_of(score: float) -> str:
    """按阈值把 0~100 的分数映射为档位。"""
    return next(g for t, g in GRADES if score >= t)


def load_max_table(path: str | Path | None = None) -> dict:
    """加载 110 阶词条满值表。"""
    if path is None:
        path = Path(__file__).resolve().parent.parent / "data" / "affix_max.json"
        if not path.exists():
            path = Path("data/affix_max.json")
    return json.loads(Path(path).read_text(encoding="utf-8"))["max"]


def load_build(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_builds(builds_dir: str | Path = "builds") -> dict[str, dict]:
    d = Path(builds_dir)
    if not d.exists():
        raise FileNotFoundError("builds/ 目录不存在，先运行: ygc import-build <计算器xlsx或目录>")
    out = {}
    for p in sorted(d.glob("*.json")):
        build = load_build(p)
        out[build.get("name", p.stem)] = build
    return out


@dataclass
class AffixScore:
    affix: Affix
    roll: float | None      # 0~100，满值未知时为 None
    weight: float
    relevant: bool          # 是否被该流派看重
    base_stat: bool = False  # 疑似基础属性行（数值远超满值），已排除


@dataclass
class PieceScore:
    piece: Piece
    build: str
    score: float | None
    grade: str
    details: list[AffixScore] = field(default_factory=list)
    relevant_weight_sum: float = 0.0


def affix_roll(affix: Affix, max_table: dict) -> tuple[float | None, bool]:
    """词条滚动质量 0~100；满值未知返回 (None, False)。

    数值超过满值 1.3 倍视为基础属性行（词条滚动不可能超过满值），
    返回 (None, True) 表示“疑似基础属性，已排除”。
    指定武学技能类特技（如 无名剑法·蓄力技增伤）用“指定武学技能增伤”满值兜底。
    """
    max_val = max_table.get(affix.name)
    if not max_val and ("技增伤" in affix.name or "技能增伤" in affix.name):
        max_val = max_table.get("指定武学技能增伤")
    if not max_val or max_val <= 0:
        return None, False
    if affix.value > max_val * 1.3:
        return None, True
    return min(100.0, affix.value / max_val * 100.0), False


def weight_for(affix_name: str, weights: dict[str, float]) -> float:
    """查词条权重：先精确匹配，再按特技后缀匹配。

    OCR 识别出的是完整特技名（如 无名剑法·蓄力技增伤），流派数据里常只写
    特技核心名（蓄力技增伤），按“词条名以键结尾/键以词条名结尾”兜底。
    """
    if affix_name in weights:
        return float(weights[affix_name])
    best = None
    for k, v in weights.items():
        if k and (affix_name.endswith(k) or k.endswith(affix_name)):
            best = v if best is None else max(best, v)  # type: ignore[assignment]
    return float(best) if best is not None else 0.0


def score_piece(piece: Piece, build: dict, max_table: dict) -> PieceScore:
    """按流派权重给单件装备打毕业度（0~100）。

    流派不看的词条不计入分母，但会在明细中列出（relevant=False）。
    """
    weights: dict[str, float] = build.get("affix_weights", {})
    details: list[AffixScore] = []
    num = den = 0.0
    for a in piece.affixes:
        w = weight_for(a.name, weights)
        relevant = w > 0
        roll, is_base = (None, False)
        if relevant:
            roll, is_base = affix_roll(a, max_table)
        details.append(AffixScore(a, roll, w, relevant, is_base))
        if relevant and roll is not None and not is_base:
            num += w * roll
            den += w
    score = round(num / den, 1) if den > 0 else None
    grade = grade_of(score) if score is not None else "未知"
    return PieceScore(piece, build.get("name", "?"), score, grade, details, den)


def compare_builds(piece: Piece, builds: dict[str, dict], max_table: dict) -> list[PieceScore]:
    """同一件装备在所有流派下的毕业度排名（降序）。"""
    results = [score_piece(piece, b, max_table) for b in builds.values()]
    return sorted(results, key=lambda s: -(s.score if s.score is not None else -1))


def format_report(score: PieceScore) -> str:
    """人类可读的单件报告。"""
    p = score.piece
    lines = [f"◆ {p.source or '装备'}  {p.name} {p.tier}  {p.set_name}".rstrip()]
    if p.craft_score is not None:
        lines[0] += f"  造诣 {p.craft_score:.0f}"
    for d in score.details:
        mark = "✓" if d.relevant else "·"
        unit = "%" if d.affix.unit == "percent" else ""
        conv = "[转]" if d.affix.converted else ""
        dy = "[定音]" if d.affix.dingyin else ""
        if d.base_stat:
            val = f"{d.affix.value}{unit}（疑似基础属性行，已排除）"
        elif d.roll is None and d.relevant:
            val = f"{d.affix.value}{unit}（缺满值，无法评分）"
        elif d.roll is None:
            val = f"{d.affix.value}{unit}"
        else:
            val = f"{d.affix.value}{unit}（{d.roll:.0f}%）"
        lines.append(f"   {mark} {conv}{dy}{d.affix.name}: {val}  权重{d.weight:g}")
    if score.score is None:
        lines.append(f"   毕业度: 无法计算（该流派关注词条均缺满值）")
    else:
        lines.append(f"   ==> 「{score.build}」毕业度 {score.score}（{score.grade}）")
    return "\n".join(lines)
