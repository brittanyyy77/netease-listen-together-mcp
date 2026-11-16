# 网易云「一起听」MCP — Cloudflare Tunnel 方案 + 实时监听

> Fork 自 [BB0813/netease-listen-together-mcp](https://github.com/BB0813/netease-listen-together-mcp)（底座作者 zbqbbm），在此基础上增加了 **Cloudflare Tunnel 穿透方案**和**房间消息实时监听**功能。

## 和原版的区别

| 项目 | 原版 | 本仓库 |
|------|------|--------|
| 公网穿透 | FRP + Nginx + 自签证书 | Cloudflare Tunnel（零配置 HTTPS，不用维护 FRP） |
| 消息读取 | 手动调用 `get_room_messages` | 新增 `listener.py` 后台自动轮询，有新消息主动推送 |
| 部署位置 | VPS / NAS | VPS / NAS / 本地电脑都行 |

---

## 目录

- [快速开始](#快速开始)
- [方案一：Cloudflare Tunnel 穿透（推荐）](#方案一cloudflare-tunnel-穿透推荐)
- [方案二：FRP + Nginx（原版方案）](#方案二frp--nginx原版方案)
- [实时消息监听](#实时消息监听)
- [在 Aru 中接入](#在-aru-中接入)
- [踩坑补充](#踩坑补充)

---

## 快速开始

### 1. 准备凭据

你需要三样东西：

| 凭据 | 怎么拿 |
|------|--------|
| `NETEASE_COOKIE` | 浏览器登录 music.163.com → F12 → Application → Cookies，复制 `MUSIC_U` 和 `__csrf`，拼成 `"MUSIC_U=xxx; __csrf=xxx"` |
| `NETEASE_LISTEN_TOGETHER_ACCEPTOR_ID` | 你的网易云数字用户 ID（纯数字，不是昵称） |
| `MCP_AUTH_TOKEN` | 自己生成：`openssl rand -hex 32` |

### 2. 克隆和配置

```bash
git clone https://github.com/brittanyyy77/netease-listen-together-mcp.git
cd netease-listen-together-mcp
git checkout cloudflare-tunnel-and-listener

cp .env.example .env
chmod 600 .env
nano .env  # 填入你的三个凭据
```

### 3. 构建并启动

```bash
docker compose build
docker compose up -d
docker compose logs -f --tail=50
```

看到 `[supergateway] Listening on port 8000` 就说明服务起来了。

### 4. 本机自测

```bash
curl -sS http://127.0.0.1:8006/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  | grep -o '"name"' | wc -l
# 期望输出：29
```

---

## 方案一：Cloudflare Tunnel 穿透（推荐）

不需要 FRP、不需要 Nginx、不需要自签证书。Cloudflare 帮你搞定 HTTPS 和域名。

### 1. 安装 cloudflared

```bash
# Mac
brew install cloudflare/cloudflare/cloudflared

# Ubuntu/Debian
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb
```

### 2. 登录 Cloudflare

```bash
cloudflared tunnel login
# 浏览器会打开，选择你的域名授权
```

### 3. 创建 Tunnel

```bash
cloudflared tunnel create netease-mcp
# 记下输出的 Tunnel ID
```

### 4. 配置路由

编辑 `~/.cloudflared/config.yml`：

```yaml
tunnel: 你的Tunnel_ID
credentials-file: /你的路径/.cloudflared/你的Tunnel_ID.json

ingress:
  - hostname: netease-mcp.你的域名.com
    service: http://localhost:8006
  - service: http_status:404
```

### 5. 添加 DNS 记录

```bash
cloudflared tunnel route dns netease-mcp netease-mcp.你的域名.com
```

### 6. 启动 Tunnel

```bash
cloudflared tunnel run netease-mcp
```

### 7. 验证

```bash
curl -sS https://netease-mcp.你的域名.com/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  | grep -o '"name"' | wc -l
# 期望输出：29
```

> **注意**：Cloudflare Tunnel 自带鉴权层（Access），也可以用 `MCP_AUTH_TOKEN` 做 Bearer 鉴权。如果你的 AI 客户端支持自定义 Header，两层都加上更安全。

### 8. 开机自启（可选）

```bash
# Mac：用 launchd
cloudflared service install

# Linux：用 systemd
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

---

## 方案二：FRP + Nginx（原版方案）

详见原版教程 [VPS-HTTP.md](./VPS-HTTP.md) 和教程 PDF，这里不重复。

---

## 实时消息监听

原版需要 AI 手动调用 `get_room_messages` 才能读到房间消息。本仓库新增 `listener.py`，后台每隔几秒自动检查新消息。

### 原理

`listener.py` 是一个独立的 Python 脚本，跑在 Docker 容器旁边（或同一台机器上）。它每隔 N 秒调用一次 MCP 的 `get_room_messages`，检测到新消息后通过 webhook 或写入文件通知你的 AI。

### 使用

```bash
# 安装依赖
pip3 install requests

# 配置
export MCP_URL="http://127.0.0.1:8006/mcp"
export POLL_INTERVAL=5        # 轮询间隔（秒）
export WEBHOOK_URL=""          # 可选：收到新消息时 POST 到这个地址
export LOG_FILE="messages.log" # 可选：新消息写入日志文件

# 启动
python3 listener.py
```

### 配合 AI 使用

1. **文件模式**：`listener.py` 把新消息写入 `messages.log`，AI 定期读取这个文件
2. **Webhook 模式**：`listener.py` 检测到新消息后 POST 到你指定的地址，AI 被动接收
3. **直接集成**：把轮询逻辑写进 AI 的主动消息规则里（如 Aru 的 proactive message）

---

## 在 Aru 中接入

| 配置项 | 填写内容 |
|--------|----------|
| 名称 | 网易云一起听 |
| URL | `https://netease-mcp.你的域名.com/mcp` |
| 传输类型 | streamable-http |
| 鉴权方式 | configured_headers（可选） |
| Header 名 | Authorization |
| Header 值 | Bearer 你的MCP_AUTH_TOKEN |

接入后把 [prompts/system_prompt.md](./prompts/system_prompt.md) 里的提示词复制到协作者系统提示词里，让 AI 知道自己能读写房间消息。

---

## 踩坑补充

以下是我们在原版踩坑表之外额外踩到的：

| # | 现象 | 原因 | 解法 |
|---|------|------|------|
| 1 | Cloudflare Tunnel 连上了但 MCP 返回 502 | Docker 容器只绑了 127.0.0.1，cloudflared 从外部访问不到 | `docker-compose.yml` 端口改成 `127.0.0.1:8006:8000`，cloudflared 跑在同一台机器上就没问题 |
| 2 | Cookie 有效但一直报鉴权失败 | `.env` 里 Cookie 值含 `%` 或 `&` 没加双引号 | 整个值用双引号包起来 |
| 3 | VPS 在国外，连网易云 API 超时 | 网易云服务器在国内，国外 VPS 延迟高 | 服务部署在国内机器上，或用 Cloudflare Tunnel 从本地电脑直连 |
| 4 | `listener.py` 轮询太频繁被限流 | 网易云 API 有调用频率限制 | 轮询间隔至少 5 秒，建议 10 秒 |

---

## 致谢

- [zbqbbm](https://github.com/zbqbbm) — 原始底座项目
- [BB0813](https://github.com/BB0813/netease-listen-together-mcp) — Linux 适配与双向通信
- [顾川 & 派派](https://github.com/BB0813) — 原始教程

## License

MIT
