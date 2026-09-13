"""网页版测试（不依赖 OCR 模型）。"""

from __future__ import annotations

from yanyun_gradecalc.web import create_app


def test_index_served():
    app = create_app()
    c = app.test_client()
    r = c.get("/")
    assert r.status_code == 200
    assert "燕云毕业度计算器".encode() in r.data


def test_config_has_builds_and_max_table():
    app = create_app()
    c = app.test_client()
    data = c.get("/api/config").get_json()
    assert "破竹樽" in data["builds"] and "裂石威" in data["builds"]
    assert data["max_table"]["最大外功攻击"] == 105.6


def test_analyze_requires_image():
    app = create_app()
    c = app.test_client()
    r = c.post("/api/analyze")
    assert r.status_code == 400
    assert "图片" in r.get_json()["error"]
