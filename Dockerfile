FROM python:3.12-slim

# Node.js（整套毕业率引擎需要）
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -e ".[web]"
# 下载站点运行时到 engine/vendor（构建机需能访问 yysls.leoq7.com；失败可在运行时重试）
RUN python scripts/fetch_engine.py || echo "警告：运行时未下载，容器内需重新执行 scripts/fetch_engine.py"

EXPOSE 8000
CMD ["python", "-m", "yanyun_gradecalc.web", "--host", "0.0.0.0", "--port", "8000"]
