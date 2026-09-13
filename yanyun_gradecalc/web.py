"""网页版小程序后端：手机/电脑浏览器拍照上传 -> 本地 OCR -> 返回识别与评分数据。

启动: python -m yanyun_gradecalc.web [--port 8000]
同一 Wi-Fi 下的手机可直接访问打印出的局域网地址。OCR 全程本机运行。
"""

from __future__ import annotations

import socket
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from .ocr import recognize_image
from .scoring import load_builds, load_max_table

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _resolve_builds_dir(explicit: str | None) -> Path:
    cands: list[Path] = []
    if explicit:
        cands.append(Path(explicit))
    cands += [Path("builds"), Path(__file__).resolve().parent.parent / "builds"]
    for c in cands:
        if c.exists():
            return c
    raise FileNotFoundError(
        "找不到 builds/ 目录：先运行 `ygc import-build <计算器xlsx或目录>` 导入流派")


def create_app(builds_dir: str | None = None, max_table_path: str | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32MB
    builds = load_builds(_resolve_builds_dir(builds_dir))
    max_table = load_max_table(max_table_path)

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/api/config")
    def config():
        return jsonify({
            "builds": {name: b.get("affix_weights", {}) for name, b in builds.items()},
            "max_table": max_table,
        })

    @app.post("/api/analyze")
    def analyze():
        f = request.files.get("image")
        if f is None:
            return jsonify({"error": "没有收到图片字段 image"}), 400
        try:
            piece = recognize_image(f.read())
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({
            "piece": {
                "name": piece.name, "slot": piece.slot, "tier": piece.tier,
                "set_name": piece.set_name,
                "craft_score": piece.craft_score, "source": piece.source,
            },
            "affixes": [
                {"name": a.name, "raw_name": a.raw_name, "value": a.value,
                 "unit": a.unit, "converted": a.converted,
                 "recommended": a.recommended, "known": a.known}
                for a in piece.affixes
            ],
            "max_table": max_table,
            "builds": {name: b.get("affix_weights", {}) for name, b in builds.items()},
        })

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify({"error": "图片超过 32MB"}), 413

    return app


def _lan_ips() -> list[str]:
    ips = ["localhost"]
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # 不发包，仅取本机出口路由 IP
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return ips


def main(argv: list[str] | None = None) -> None:
    import argparse

    p = argparse.ArgumentParser(prog="ygc-web", description="燕云毕业度计算器网页版")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--builds-dir", default=None)
    p.add_argument("--max-table", default=None)
    args = p.parse_args(argv)

    app = create_app(args.builds_dir, args.max_table)
    print("网页版已就绪，浏览器打开：")
    for ip in _lan_ips():
        print(f"  http://{ip}:{args.port}")
    print("手机与电脑连同一 Wi-Fi 后可用局域网地址；若打不开，请在 Windows 防火墙放行 Python。")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
