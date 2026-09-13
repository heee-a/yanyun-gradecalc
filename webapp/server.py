"""yanyun-gradecalc Web 服务：公开 OCR 识别 + 流派数据 + 管理导入接口。

数据边界（部署与面试时可讲）：
- 用户照片仅在内存中识别，服务端不落盘、不存储；
- 用户的方案保存在各自浏览器 localStorage，用户之间互不影响；
- 服务端唯一可变数据是管理员导入的流派/满值表（受 ADMIN_TOKEN 保护）。

启动: uvicorn server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]

app = FastAPI(
    title="yanyun-gradecalc web",
    description="拍照识别装备词条，按流派计算毕业度。照片仅在内存中处理，不落盘。",
    version="1.0.0")


# ---------------- OCR（懒加载 + EXIF 转正 + 旋转重试） ----------------
_ocr_fn = None       # bytes -> piece dict；可注入替换（测试）


def set_ocr_fn(fn) -> None:
    """注入 OCR 实现（测试用）：fn(image_bytes) -> piece dict。"""
    global _ocr_fn
    _ocr_fn = fn


def _default_ocr(image_bytes: bytes) -> dict:
    img = _prep_image(image_bytes)
    piece, rotated = _recognize_best(img)
    piece["rotated"] = rotated
    return piece


def _get_ocr():
    return _ocr_fn or _default_ocr


def _prep_image(image_bytes: bytes) -> np.ndarray:
    """解码 + EXIF 转正 + 大图降采样（≤2000px）。"""
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("无法解码图片，请换一张照片")
    ok, encoded = cv2.imencode(".png", img)
    pil = ImageOps.exif_transpose(Image.open(io.BytesIO(encoded.tobytes())))
    if max(pil.size) > 2000:
        pil.thumbnail((2000, 2000))
    rgb = np.array(pil.convert("RGB"))
    return rgb[:, :, ::-1]          # RGB -> BGR


def _recognize_best(img: np.ndarray) -> tuple[dict, int]:
    """识别；词条过少时自动旋转重试，返回 (结果, 旋转角度)。"""
    best = _get_ndarray_impl()(img)
    best_rot = 0
    if len(best.get("affixes", [])) >= 3:
        return best, best_rot
    for k in (1, 2, 3):             # 90 / 180 / 270 度
        cand = _get_ndarray_impl()(np.rot90(img, k=k))
        if len(cand.get("affixes", [])) > len(best.get("affixes", [])):
            best, best_rot = cand, k * 90
    return best, best_rot


_ndarray_impl = None


def _get_ndarray_impl():
    """ndarray -> piece dict 的真实实现（懒加载 RapidOCR）。"""
    global _ndarray_impl
    if _ndarray_impl is None:
        from yanyun_gradecalc.ocr import recognize as _recognize_impl

        def impl(img: np.ndarray) -> dict:
            import tempfile
            from dataclasses import asdict

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                cv2.imwrite(tmp.name, img)
                tmp_path = tmp.name
            try:
                return asdict(_recognize_impl(tmp_path))
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        _ndarray_impl = impl
    return _ndarray_impl


# ---------------- 路由 ----------------
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/meta")
def meta() -> JSONResponse:
    """前端一次性拉取计算所需的共享只读数据，之后的打分全部在浏览器本地完成。"""
    from yanyun_gradecalc.scoring import load_builds, load_max_table
    from yanyun_gradecalc.stats_dict import CANONICAL_STATS

    builds = load_builds(str(ROOT / "builds"))
    maxes = load_max_table(str(ROOT / "data" / "affix_max.json"))
    return JSONResponse({
        "builds": {k: v.get("affix_weights", {}) for k, v in builds.items()},
        "maxes": maxes,
        "known_stats": sorted(CANONICAL_STATS),
    })


@app.post("/api/ocr")
async def ocr(image: UploadFile = File(...)) -> dict:
    """照片 -> 结构化装备词条。无状态：图片不落盘、不存储。"""
    raw = await image.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "图片超过 20MB")
    try:
        piece = _get_ocr()(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    piece.pop("_rotated", None)
    return piece


def _check_admin(x_admin_token: str | None) -> None:
    expected = os.environ.get("ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(503, "导入功能未启用：服务端需设置 ADMIN_TOKEN 环境变量")
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(401, "管理令牌错误")


@app.post("/api/admin/import-builds", tags=["admin"])
async def admin_import_builds(
    files: list[UploadFile] = File(...),
    x_admin_token: str | None = None,
) -> dict:
    """更新接口：上传新的毕业率计算器 xlsx，导入为流派数据（需管理令牌）。

    重启后失效（写入 builds/ 目录的持久化以部署卷为准）。
    """
    _check_admin(x_admin_token)
    from yanyun_gradecalc.build_import import import_build

    imported, tmp_dir = [], Path(os.environ.get(
        "UPLOAD_DIR", ROOT / "builds" / "_uploads"))
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        if not f.filename.lower().endswith(".xlsx"):
            continue
        data = await f.read()
        tmp = tmp_dir / Path(f.filename).name
        tmp.write_bytes(data)
        build = import_build(tmp, ROOT / "builds")
        imported.append(json.loads(build.read_text(encoding="utf-8"))["name"])
    if not imported:
        raise HTTPException(400, "没有可导入的 xlsx 文件")
    return {"imported": imported}


# ---------------- 静态前端 ----------------
STATIC = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
