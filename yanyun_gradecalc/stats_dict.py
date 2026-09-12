"""词条名字典：别名归一化、百分比/数值类型判断、[转]/荐 标记解析。"""

from __future__ import annotations

import re

# 标准词条名 -> 定义。type: flat=固定数值, percent=百分比
# aliases 用于 OCR 模糊匹配归一化（大小写无关，需先清洗空白）
CANONICAL_STATS: dict[str, dict] = {
    # 基础属性类（固定数值）
    "劲": {"type": "flat", "aliases": ["劲"]},
    "势": {"type": "flat", "aliases": ["势"]},
    "敏": {"type": "flat", "aliases": ["敏"]},
    "体魄": {"type": "flat", "aliases": ["体魄"]},
    "博学": {"type": "flat", "aliases": ["博学"]},
    "协调": {"type": "flat", "aliases": ["协调"]},
    "志趣": {"type": "flat", "aliases": ["志趣"]},
    # 攻击类
    "最大外功攻击": {"type": "flat", "aliases": ["最大外功攻击", "最大外攻", "最大外功攻"]},
    "最大鸣金攻击": {"type": "flat", "aliases": ["最大鸣金攻击", "最大鸣攻", "鸣金攻击"]},
    "最小外功攻击": {"type": "flat", "aliases": ["最小外功攻击", "最小外攻"]},
    "最小鸣金攻击": {"type": "flat", "aliases": ["最小鸣金攻击", "最小鸣攻"]},
    "外功穿透": {"type": "flat", "aliases": ["外功穿透", "穿透"]},
    "鸣金穿透": {"type": "flat", "aliases": ["鸣金穿透"]},
    # 暴击/命中类（百分比）
    "会心率": {"type": "percent", "aliases": ["会心率", "会心"]},
    "会意率": {"type": "percent", "aliases": ["会意率", "会意"]},
    "精准率": {"type": "percent", "aliases": ["精准率", "精准"]},
    "直接会心率": {"type": "percent", "aliases": ["直接会心率"]},
    "直接会意率": {"type": "percent", "aliases": ["直接会意率"]},
    # 增伤类（百分比）
    "对首领单位增伤": {"type": "percent", "aliases": ["对首领单位增伤", "首领增伤", "对首领增伤"]},
    "伤害加成": {"type": "percent", "aliases": ["伤害加成"]},
    "全武器增伤": {"type": "percent", "aliases": ["全武器增伤", "全武增"]},
    "会心伤害": {"type": "percent", "aliases": ["会心伤害"]},
    "会意伤害": {"type": "percent", "aliases": ["会意伤害"]},
    # 武学特技类（百分比），如 无名剑法·蓄力技增伤 —— 归一化时按“*增伤”动态识别
}

_PANEL_TO_AFFIX: dict[str, list[str]] = {
    # 计算器输入区面板属性 -> 对应装备词条
    "最小攻击": ["最小外功攻击"],
    "最大攻击": ["最大外功攻击", "最大鸣金攻击"],
    "穿透": ["外功穿透"],
    "伤害加成": ["伤害加成"],
    "外功": ["劲"],
    "会心率": ["会心率"],
    "会意率": ["会意率"],
    "精准率": ["精准率"],
    "直接会心率": ["直接会心率"],
    "直接会意率": ["直接会意率"],
    "会心伤害加成": ["会心伤害"],
    "会意伤害加成": ["会意伤害"],
    "首领增": ["对首领单位增伤"],
    "全武增": ["全武器增伤"],
    # DIY 计算器使用的简称
    "最小外攻": ["最小外功攻击"],
    "最大外攻": ["最大外功攻击"],
    "最小鸣金": ["最小鸣金攻击"],
    "最大鸣金": ["最大鸣金攻击"],
    "外攻穿透": ["外功穿透"],
    "鸣金穿透": ["鸣金穿透"],
    "直接会心": ["直接会心率"],
    "直接会意": ["直接会意率"],
    "会伤": ["会心伤害"],
    "会意伤": ["会意伤害"],
    "敏": ["敏"],
}

_CLEAN_RE = re.compile(r"[\s\[\]【】]")
_TURN_RE = re.compile(r"^转")
_REC_RE = re.compile(r"荐$")
_NUM_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(%?)$")


def clean_name(raw: str) -> str:
    """去掉空格/括号/换行，供匹配。"""
    return _CLEAN_RE.sub("", str(raw))


def split_affix_marker(name: str) -> tuple[str, bool, bool]:
    """从词条文本中剥离 [转] 前缀与 荐 标记，返回 (纯名, 是否转词条, 是否推荐)。"""
    is_conv = "转" in name and name.index("转") <= 1  # 仅识别开头的 [转]
    name = _TURN_RE.sub("", name)
    is_rec = name.endswith("荐")
    name = _REC_RE.sub("", name)
    return name, is_conv, is_rec


def normalize_stat(raw_name: str) -> str | None:
    """把 OCR 出的词条名归一化为标准名；含别名模糊匹配与“*增伤”特技规则。

    返回 None 表示无法识别（调用方按未知词条处理）。
    """
    name = clean_name(raw_name)
    name, _, _ = split_affix_marker(name)
    if not name:
        return None
    if name in CANONICAL_STATS:
        return name
    # 别名先查（如 首领增伤 -> 对首领单位增伤），再落到“*增伤”特技规则
    import difflib

    pool = {alias: std for std, d in CANONICAL_STATS.items() for alias in d["aliases"]}
    match = difflib.get_close_matches(name, list(pool), n=1, cutoff=0.72)
    if match:
        return pool[match[0]]
    if name.endswith("增伤"):
        return name  # 武学特技（如 无名剑法·蓄力技增伤）按原文保留
    return None


def stat_type(canonical: str) -> str:
    if canonical in CANONICAL_STATS:
        return CANONICAL_STATS[canonical]["type"]
    return "percent" if canonical.endswith("增伤") else "flat"


def parse_value(raw: str) -> tuple[float, str] | None:
    """解析数值文本 -> (数值, 'flat'|'percent')；无法解析返回 None。"""
    m = _NUM_RE.match(clean_name(str(raw)))
    if not m:
        return None
    return float(m.group(1)), ("percent" if m.group(2) else "flat")
