"""网页版小程序后端：手机/电脑浏览器拍照上传 -> 本地 OCR -> 返回识别与评分数据。

启动: python -m yanyun_gradecalc.web [--port 8000]
同一 Wi-Fi 下的手机可直接访问打印出的局域网地址。OCR 与毕业率引擎全程本机运行。

整套毕业率使用 leoq7 管理器同款 runtime（engine/ 目录，Node + WASM），
与网站计算逻辑完全一致；支持流派/心法/套装/弓决切换。
"""

from __future__ import annotations

import json
import queue
import shutil
import socket
import subprocess
import threading
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


class Engine:
    """engine/engine.mjs（Node 子进程）的行 JSON 协议封装。"""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._next_id = 0
        self._meta: dict | None = None
        self._error: str | None = None

    @property
    def script(self) -> Path:
        here = Path(__file__).resolve().parent.parent
        for c in (here / "engine" / "engine.mjs", Path("engine/engine.mjs")):
            if c.exists():
                return c
        raise FileNotFoundError("engine/engine.mjs 不存在（请在仓库根目录运行）")

    def _ensure(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        node = shutil.which("node")
        if not node:
            raise RuntimeError("未找到 node，请安装 Node.js（https://nodejs.org）")
        script = self.script
        self._proc = subprocess.Popen(
            [node, str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            cwd=str(script.parent.parent))
        threading.Thread(target=self._pump, daemon=True).start()
        ready = self._recv(90)
        if ready is None:
            raise RuntimeError("引擎启动超时")
        self._meta = ready.get("result")

    def _pump(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            line = line.strip()
            if line.startswith("{"):
                try:
                    self._queue.put(json.loads(line))
                except json.JSONDecodeError:
                    pass

    def _recv(self, timeout: float) -> dict | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def call(self, cmd: str, payload: dict | None = None, timeout: float = 120) -> dict:
        with self._lock:
            self._ensure()
            self._next_id += 1
            rid = self._next_id
            msg: dict = {"id": rid, "cmd": cmd}
            if payload is not None:
                msg["payload"] = payload
            assert self._proc and self._proc.stdin
            self._proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self._proc.stdin.flush()
            while True:
                m = self._recv(timeout)
                if m is None:
                    raise TimeoutError("引擎计算超时")
                if m.get("id") != rid:
                    continue
                if not m.get("ok"):
                    raise RuntimeError(str(m.get("error")))
                return m["result"]  # type: ignore[no-any-return]

    def meta(self) -> dict:
        if self._meta is not None:
            return self._meta
        return self.call("meta")


ENGINE = Engine()


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
            "affixes": [_affix_json(a) for a in piece.affixes],
            "base_stats": [_affix_json(a) for a in piece.base_stats],
            "max_table": max_table,
            "builds": {name: b.get("affix_weights", {}) for name, b in builds.items()},
        })

    @app.get("/api/engine")
    def engine_meta():
        try:
            info = ENGINE.meta()
            return jsonify({"available": True, **info})
        except Exception as e:  # node 缺失/脚本缺失等
            return jsonify({"available": False, "error": str(e)})

    @app.post("/api/gradrate")
    def gradrate():
        body = request.get_json(silent=True) or {}
        payload = {
            "className": body.get("className") or body.get("flowName") or "",
            "bow": body.get("bow") or "precision",
            "xinfa": body.get("xinfa") or [],
            "setName": body.get("setName") or "",
            "armory": body.get("armory") or "本系",
            "equippedItems": body.get("equippedItems") or {},
        }
        try:
            result = ENGINE.call("calc", payload)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        return jsonify(result)

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify({"error": "图片超过 32MB"}), 413

    return app


def _affix_json(a) -> dict:
    return {"name": a.name, "raw_name": a.raw_name, "value": a.value,
            "unit": a.unit, "converted": getattr(a, "converted", False),
            "recommended": getattr(a, "recommended", False),
            "dingyin": getattr(a, "dingyin", False),
            "known": a.known}


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
