"""下载 leoq7 管理器的运行时文件到 engine/vendor/（网页版整套毕业率引擎依赖）。

文件为 yysls.leoq7.com 公开服务的同款资源，仓库不入库，需要时运行：
    python scripts/fetch_engine.py
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

BASE = "https://yysls.leoq7.com/assets/js"
FILES = [
    "leoq7_generated-calc-metadata.js",
    "leoq7_generated-calc-strings.js",
    "leoq7_excel-runtime.js",
    "leoq7_generated-best40-stats.js",
    "leoq7_app.min.js",
]
WASM_URL = "https://yysls.leoq7.com/assets/js/wasm/yysls_calc.wasm"

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "engine" / "vendor"


def fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  已存在，跳过: {dest.name}")
        return
    print(f"  下载 {url}")
    with urllib.request.urlopen(url, timeout=60) as r:
        dest.write_bytes(r.read())
    print(f"  -> {dest} ({dest.stat().st_size:,} bytes)")


def main() -> None:
    print("下载引擎运行时（共 6 个文件）:")
    for f in FILES:
        fetch(f"{BASE}/{f}", VENDOR / f)
    fetch(WASM_URL, VENDOR / "wasm" / "yysls_calc.wasm")
    print("完成。现在可以启动: ygc-web")


if __name__ == "__main__":
    main()
