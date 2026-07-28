# DocForge 运维手册（README-OPS）

本手册面向生产运维，聚焦部署后稳定运行，不涉及开发细节。

---

## 1. 生产环境最小化环境变量模板

以下为建议的最小模板（可直接用于 Docker Compose `environment`）：

```env
# 服务监听
AIDOC_WEB_HOST=0.0.0.0
AIDOC_WEB_PORT=8008

# 日志目录（容器内）
AIDOC_LOG_DIR=/app/logs

# 上传与请求限制
AIDOC_MAX_TEMPLATE_UPLOAD_BYTES=10485760
AIDOC_MAX_MARKDOWN_BYTES=2097152

# 历史任务清理策略
AIDOC_SUCCESS_TTL_SECONDS=86400
AIDOC_FAILED_TTL_SECONDS=21600
AIDOC_CLEANUP_INTERVAL_SECONDS=900
AIDOC_MAX_JOB_DIRS=500
AIDOC_MAX_JOB_TOTAL_BYTES=2147483648
```

说明：
- 模板上传上限：10MB
- Markdown 请求上限：2MB
- 成功任务保留：24h
- 失败任务保留：6h
- 清理周期：15min
- 任务目录上限：500
- 任务目录总大小上限：2GB

---

## 2. Nginx 反向代理示例

以下示例用于 `api.example.com` 反代到 DocForge（`127.0.0.1:8008`）。

```nginx
server {
    listen 80;
    server_name api.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate     /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    client_max_body_size 12m;

    location / {
        proxy_pass http://127.0.0.1:8008;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 30s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
```

运维建议：
- `client_max_body_size` 应大于应用层限制（如 12m），由应用层返回更友好的 413 错误。
- 若前端 Mermaid 依赖外网 CDN，需确保服务器可访问相关域名。

---

## 3. 备份与恢复流程

### 3.1 需要备份的目录

重点备份以下目录：
- `webapp/uploads/`（用户上传模板与 manifest）
- `webapp/runtime/`（任务产物与中间文件）
- `logs/`（运行日志，用于追溯）

可不备份：
- `__pycache__/`
- 临时构建目录（如 `build/`、`dist/`）

### 3.2 备份步骤（示例）

在项目根目录执行：

```bash
tar -czf backup-$(date +%F-%H%M).tar.gz \
  webapp/uploads \
  webapp/runtime \
  logs
```

若使用 Docker，建议先短暂停服或至少停止写入再备份：

```bash
docker compose stop
tar -czf backup-$(date +%F-%H%M).tar.gz webapp/uploads webapp/runtime logs
docker compose start
```

### 3.3 恢复步骤（示例）

```bash
docker compose down
tar -xzf backup-YYYY-MM-DD-HHMM.tar.gz -C /path/to/AIDOC
docker compose up -d
```

恢复后核验：
- `GET /api/health` 返回 `ok=true`
- `GET /api/templates` 可看到上传模板
- 能正常发起一次 docx 与 pdf 转换

---

## 4. 故障排查 Checklist（30 秒定位版）

按顺序执行，快速定位：

1) **服务活性**
- 打开 `GET /api/health`
- 若不通：先看进程/容器状态

2) **端口与反代**
- 本机访问 `http://127.0.0.1:8008/api/health`
- 若本机通、域名不通：优先查 Nginx/安全组/防火墙

3) **日志**
- 查看 `logs/app.log`
- 重点关键词：`Pandoc Error`、`typst`、`timeout`、`413`

4) **Pandoc/Typst 可用性**
- `/api/health` 内检查 `pandoc.ok` 和 `typst.ok`
- `typst` 不可用时，PDF 会失败，docx 通常可用

5) **请求大小超限**
- 出现 413：检查 Markdown 是否 >2MB 或模板是否 >10MB
- 适当调整对应环境变量并重启服务

6) **字体问题（PDF）**
- 报 `unknown font family`：容器缺字库
- 安装/挂载 CJK 字体，重启后再试

7) **图片路径问题（PDF）**
- 报 `file not found`：Markdown 引用本地图片但容器内不存在
- 使用可访问 URL 或将图片放入容器可见路径

8) **磁盘与清理**
- 检查 `webapp/runtime/jobs` 是否超大
- 调用 `POST /api/cleanup` 或等待自动清理周期

9) **Mermaid 不显示（预览）**
- 预览区域若提示 CDN 加载失败，说明云端出网策略限制
- 放行 CDN 域名或改为本地静态 Mermaid 资源

10) **仍未恢复**
- 打包最近 `logs/app.log` + `/api/health` 返回 + 最近一次失败请求体（脱敏）进行二线排查

---

## 5. 运维建议（简版）

- 监控：
  - 进程/容器存活
  - 磁盘使用率
  - `webapp/runtime/jobs` 目录大小
- 每日：
  - 留存日志快照
  - 抽样验证一次 PDF 导出
- 变更管理：
  - 先灰度再全量
  - 变更后立即验证 `/api/health` 与导出链路
