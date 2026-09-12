"""yanyun-gradecalc: 燕云十六声装备毕业度计算器（拍照识别词条 → 按流派算毕业度）。

纯本地运行：OCR 在本机完成，不上传任何图片。
"""

__version__ = "0.1.0"

from . import build_import, ocr, scoring, stats_dict

__all__ = ["build_import", "ocr", "scoring", "stats_dict"]
