"""OCR 识别：截图/照片 -> 装备词条结构。

使用 RapidOCR（onnxruntime），首次调用自动下载模型。针对斜拍屏幕照片的
配对算法：
  1. 纯数值框按 x 聚类，最大簇为“数值列”（装备照片里词条数值天然右对齐）；
  2. 词条名池保留全部左侧中文框（含 气血最大值 等基础属性行，用于对齐占位）；
  3. 名/值按 y 序做保序 1:1 动态规划配对，允许跳过名字（跳过有代价），
     且类型不兼容（百分比词条配到固定数值）直接禁止——斜拍偏移由此锁正；
  4. 配对后过滤基础属性行与界面噪音，只留装备词条。
解析与 OCR 引擎分离，可独立测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .stats_dict import normalize_stat, parse_value, split_affix_marker, stat_type

_OCR = None


def _get_ocr():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR

        _OCR = RapidOCR()
    return _OCR


@dataclass
class Affix:
    name: str            # 标准词条名（无法识别时保留清洗后的原文）
    raw_name: str        # OCR 原文拼接
    value: float
    unit: str            # flat / percent
    converted: bool = False   # [转] 词条
    recommended: bool = False  # 带 荐 标记
    known: bool = True   # 能否归一化到词条字典


@dataclass
class Piece:
    source: str = ""
    name: str = ""            # 装备名，如 承音 / 雁南飞甲
    slot: str = ""            # 部位，如 冠胄 / 胸甲
    craft_score: float | None = None  # 造诣
    tier: str = ""            # 装备等阶，如 110阶
    set_name: str = ""        # 套装，如 易相套装4/4
    affixes: list[Affix] = field(default_factory=list)


# 配对后要从词条里剔除的界面/基础属性行（仍参与对齐占位）
_UI_WORDS = ("装备等阶", "气血最大值", "外功防御", "耐久度", "穿戴等级",
             "体魄要求", "协调要求", "博学要求", "套装", "精英战令", "精英战今",
             "更多设置", "同名阶", "激活", "生效等级", "件套", "心法", "需求",
             "造诣", "造谐")
# 锚点行：与词条行交错出现、用于锁定左右列纵向偏移的基础属性行，配对不罚分
_ANCHOR_WORDS = ("气血最大值", "外功防御", "耐久度", "穿戴等级", "体魄要求",
                 "协调要求", "博学要求", "装备等阶", "造诣", "造谐")
_NOISE_PAIR_PENALTY = 150.0  # 非锚点 UI 名（套装名等）参与配对的罚分，防止吸走数值
_SLOT_WORDS = ("冠胄", "胸甲", "护腕", "腰带", "护腿", "鞋子", "项链", "戒指",
               "武器", "护手", "坠饰")
_INF = float("inf")
_SKIP_COST = 90.0     # 跳过一个名字的代价（须低于一次明显错配的偏差代价）
_VSKIP = 300.0        # 跳过一个数值的代价（杂散数字，能配则配）
_COST_CAP = 250.0     # 单次配对的纵向偏差代价上限


def _center(box) -> tuple[float, float]:
    xs = [float(p[0]) for p in box]
    ys = [float(p[1]) for p in box]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _fit_drift(points: list[tuple[float, float]]) -> tuple[float, float]:
    """最小二乘拟合 偏移 ≈ a + b·y（斜拍照片偏移随行位置线性变化）。"""
    n = len(points)
    if n < 3:
        b = 0.0
        a = sum(o for _, o in points) / n if n else 0.0
        return a, b
    sx = sum(x for x, _ in points)
    sy = sum(o for _, o in points)
    sxx = sum(x * x for x, _ in points)
    sxy = sum(x * o for x, o in points)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-9:
        return sy / n, 0.0
    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n
    return a, b


def recognize(image_path: str) -> Piece:
    """识别一张装备截图/照片，返回结构化 Piece。"""
    result, _ = _get_ocr()(str(image_path))
    return parse_ocr_result(result or [], source=str(image_path))


def recognize_image(data: bytes, max_side: int = 2200) -> Piece:
    """识别图片字节流（网页上传入口）。大图先等比缩小，显著加速 OCR。"""
    import cv2
    import numpy as np

    buf = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("无法解码图片，请换一张（支持 jpg/png/webp）")
    h, w = img.shape[:2]
    scale = max_side / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    result, _ = _get_ocr()(img)
    return parse_ocr_result(result or [], source="upload")


def parse_ocr_result(result, source: str = "") -> Piece:
    """把 RapidOCR 输出 [(box, text, score), ...] 解析为 Piece。"""
    piece = Piece(source=source)
    if not result:
        return piece

    boxes = []
    for box, text, *_ in result:
        cx, cy = _center(box)
        h = max(float(p[1]) for p in box) - min(float(p[1]) for p in box)
        boxes.append({"text": str(text).strip(), "x": cx, "y": cy, "h": h})

    _extract_metadata(piece, boxes)
    value_boxes = _find_value_column(boxes)
    if not value_boxes:
        return piece
    val_min_x = min(b["x"] for b in value_boxes)

    # 造诣：数值列之外、位置靠上的最大数字（界面里即 造诣 大字号数值）
    outside = [b for b in boxes if b not in value_boxes and parse_value(b["text"])
               and len(b["text"]) <= 6]
    if outside:
        top = [b for b in outside if b["y"] < min(v["y"] for v in value_boxes)]
        if top:
            piece.craft_score = max(parse_value(b["text"])[0] for b in top)  # type: ignore[union-attr]

    # 名字池：数值列左侧的全部中文框（含基础属性行，占位对齐用），剔除独立“荐”角标
    name_boxes = [
        b for b in boxes
        if b not in value_boxes and b["x"] < val_min_x - 20
        and _has_cjk(b["text"]) and b["text"] != "荐"
    ]
    name_boxes.sort(key=lambda b: b["y"])
    value_boxes.sort(key=lambda b: b["y"])

    pairs = _align(name_boxes, value_boxes)

    used_texts = set()
    for n, v in pairs:
        used_texts.add(n["text"])
        if any(w in n["text"] for w in _UI_WORDS):
            continue  # 基础属性/界面行
        raw = n["text"]
        core, is_conv, is_rec = split_affix_marker(raw.replace("[", "").replace("]", ""))
        std = normalize_stat(core)
        val, unit = parse_value(v["text"])  # type: ignore[misc]
        piece.affixes.append(Affix(name=std or core, raw_name=raw, value=val,
                                   unit=unit, converted=is_conv, recommended=is_rec,
                                   known=std is not None))

    # 装备名/部位：最上方的未占用中文框（至少 2 个汉字、非“荐”角标）
    for b in sorted(boxes, key=lambda b: b["y"]):
        t = b["text"].strip("←↑↖ ")
        if (not t or _is_noise(t) or t == "荐" or t.endswith("荐") or b in value_boxes
                or t in used_texts or not _has_cjk(t)):
            continue
        if sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff") < 2:
            continue
        if "·" in t and "阶" in t:
            piece.name, _, tier_part = t.partition("·")
            piece.tier = piece.tier or tier_part
        else:
            piece.name = piece.name or t
        break
    for b in boxes:
        t = b["text"]
        if t in _SLOT_WORDS and t != piece.name:
            piece.slot = piece.slot or t
    return piece


def _extract_metadata(piece: Piece, boxes) -> None:
    """套装名 / 等阶 / 造诣。"""
    for b in boxes:
        t = b["text"]
        if "套装" in t and not piece.set_name:
            piece.set_name = t
        elif "装备等阶" in t and not piece.tier:
            piece.tier = t.replace("装备等阶", "").strip()
    if not piece.tier:
        for b in boxes:
            if "110阶" in b["text"].replace("·", ""):
                piece.tier = "110阶"
                break


def _find_value_column(boxes) -> list[dict]:
    """纯数值框按 x 聚类，返回最大簇（词条数值天然右对齐成一列）。"""
    nums = []
    for b in boxes:
        pv = parse_value(b["text"])
        if pv is not None and len(b["text"]) <= 8:
            b = dict(b, value=pv[0], unit=pv[1])
            nums.append(b)
    if not nums:
        return []
    nums.sort(key=lambda b: b["x"])
    clusters: list[list[dict]] = [[nums[0]]]
    for b in nums[1:]:
        if b["x"] - clusters[-1][-1]["x"] <= 160:
            clusters[-1].append(b)
        else:
            clusters.append([b])
    best = max(clusters, key=len)
    return best if len(best) >= 2 else nums


def _align(names: list[dict], values: list[dict]) -> list[tuple[dict, dict]]:
    """保序 1:1 配对。DP：名字可跳过（小代价）、数值可跳过（大代价，用于杂散数字），
    类型不兼容禁止配对；纵向偏移基准取“整体平移 s”扫描出的最优中位偏移。"""

    def type_ok(n: dict, v: dict) -> bool:
        std = normalize_stat(n["text"])
        if std is None:
            return True  # 未知词条名不设类型约束
        return stat_type(std) == v["unit"]

    def pair_cost(n: dict, v: dict) -> float:
        pred = drift_a + drift_b * v["y"]
        d = min(abs(v["y"] - n["y"] - pred), _COST_CAP)
        if _is_soft_noise(n["text"]):
            d += _NOISE_PAIR_PENALTY
        return d

    # —— 估计纵向偏移的线性漂移（斜拍照片：偏移随行位置渐变） —— #
    best_cost, drift_a, drift_b = _INF, 150.0, 0.0
    for s in range(0, max(1, len(names) - len(values) + 1)):
        pts = [(values[k]["y"], values[k]["y"] - names[s + k]["y"])
               for k in range(len(values)) if s + k < len(names)]
        if len(pts) < max(1, len(values) // 2):
            continue
        a, b = _fit_drift(pts)
        cost = sum(abs(o - (a + b * y)) for y, o in pts) + sum(
            1000 for k, (y, o) in enumerate(pts)
            if k < len(values) and not type_ok(names[s + k], values[k]))
        if cost < best_cost:
            best_cost, drift_a, drift_b = cost, a, b

    # —— DP 精配 —— #
    n, m = len(names), len(values)
    inf = float("inf")
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    choice: list[list[tuple[str, int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for k in range(m + 1):
            cur = dp[i][k]
            if cur == inf:
                continue
            if i < n:  # 跳过名字 i
                if cur + _SKIP_COST < dp[i + 1][k]:
                    dp[i + 1][k] = cur + _SKIP_COST
                    choice[i + 1][k] = ("skip", i, k)
                if k < m and type_ok(names[i], values[k]):
                    c = cur + pair_cost(names[i], values[k])
                    if c < dp[i + 1][k + 1]:
                        dp[i + 1][k + 1] = c
                        choice[i + 1][k + 1] = ("pair", i, k)
            if k < m:  # 跳过数值 k（杂散数字）
                if cur + _VSKIP < dp[i][k + 1]:
                    dp[i][k + 1] = cur + _VSKIP
                    choice[i][k + 1] = ("vskip", i, k)

    pairs: list[tuple[dict, dict]] = []
    i, k = n, m
    while i > 0 or k > 0:
        ch = choice[i][k]
        if ch is None:
            break
        kind, pi, pk = ch
        if kind == "pair":
            pairs.append((names[pi], values[pk]))
        i, k = pi, pk
    pairs.reverse()
    return pairs


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _is_noise(text: str) -> bool:
    return any(w in text for w in _UI_WORDS)


def _is_soft_noise(text: str) -> bool:
    """非锚点的界面名（套装名等）：参与配对但付罚分，防止吸走词条数值。"""
    return _is_noise(text) and not any(w in text for w in _ANCHOR_WORDS)
