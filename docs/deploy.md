# 公开部署与多人使用

## 多人互不影响（设计保证）

服务端是**无状态**的：每次拍照识别、每次整套计算都只是一次独立请求；
整套方案保存在**每个人自己手机的浏览器**（localStorage）里。
所以无论多少人同时用，谁的数据都不会影响谁，也不需要登录。

## 三种公开方式

### 1. 局域网内公开（零配置）

连同一个 Wi-Fi 的人都能用：`http://<电脑IP>:8000`（启动时自动打印）。
Windows 防火墙放行 8000 端口即可（仓库提供 `netsh` 规则见 README）。

### 2. 云服务器部署（推荐，真正公网可用）

工具是纯 Python + Node，一台最低配的国内云主机即可：

```bash
# 服务器上（需备案域名才能被微信正常打开）
docker build -t yanyun-gradecalc .
docker run -d -p 80:8000 --name yanyun yanyun-gradecalc
```

或不用 Docker：装 Python 3.10+ 与 Node 18+，`pip install -e ".[web]"` +
`python scripts/fetch_engine.py`，然后用 systemd/进程守护启动
`python -m yanyun_gradecalc.web --port 80`。

### 3. 内网穿透（临时演示）

`cloudflared tunnel --url http://localhost:8000 --protocol http2`
可生成临时公网地址，但 trycloudflare.com 域名在大陆网络常不可达；
需要稳定公网建议使用国内穿透服务（cpolar / 贝锐花生壳，需注册），
把隧道指向 `http://localhost:8000` 即可。

## 数据更新接口（管理员）

上传新的毕业率计算器 xlsx，自动提取流派并热重载，无需重启：

```bash
# 管理令牌在服务启动时打印（也可用环境变量 YGC_ADMIN_TOKEN 固定）
curl -X POST http://<地址>:8000/api/update-data \
  -H "X-Admin-Token: <令牌>" \
  -F "file=@新的计算器.xlsx"
```

- 会新建/覆盖对应流派 JSON（builds/），立即对所有人生效；
- 命令行同样可以：`ygc import-build <xlsx 或目录>`；
- 该接口受令牌保护，普通使用者无法改动全局数据。
