# DocForge

DocForge 是一个 Markdown 转 Word/PDF 的本地与云端双形态工具：
- 桌面版（CustomTkinter）
- Web 版（FastAPI + 单页前端）

主要能力：
- Markdown 一键导出 `docx` / `pdf`
- 内置模板（公文风、互联网风、学术风）+ 自定义模板上传
- Web 预览（支持 Mermaid、数学公式）
- 后台任务队列、下载、清理与日志查看

---

## 1. 目录结构与代码功能

- [main.py](main.py)：桌面 GUI 入口
- [run_web.py](run_web.py)：Web 服务启动入口（本地）
- [core/converter.py](core/converter.py)：核心转换逻辑（Pandoc/Typst、Markdown 清洗、DOCX 后处理）
- [core/logger.py](core/logger.py)：日志初始化与读取
- [webapp/backend/server.py](webapp/backend/server.py)：Web API（预览、转换、模板上传、任务管理）
- [webapp/backend/job_store.py](webapp/backend/job_store.py)：任务状态与清理策略
- [webapp/frontend/index.html](webapp/frontend/index.html)：Web 前端页面
- [templates/](templates/)：内置 Word 模板
- [preview_render_template.html](preview_render_template.html)：Pandoc 预览模板（Web）

---

## 2. 运行方式

### 2.1 桌面版

安装依赖：

```bash
pip install -r requirements.txt
```

启动：

```bash
python main.py
```

### 2.2 Web 版（源码启动）

安装依赖：

```bash
pip install -r requirements.web.txt
```

启动（会自动打开浏览器）：

```bash
python run_web.py
```

或直接启动 Uvicorn：

```bash
uvicorn webapp.backend.server:app --host 0.0.0.0 --port 8008
```

---

## 3. Docker 部署

### 3.1 本地 Docker Compose

使用 [docker-compose.yml](docker-compose.yml)：

```bash
docker compose up -d --build
```

默认暴露端口 `8008`，并挂载：
- `./logs:/app/logs`
- `./webapp/runtime:/app/webapp/runtime`
- `./webapp/uploads:/app/webapp/uploads`

### 3.2 云端 Compose

使用 [docker-compose.cloud.yml](docker-compose.cloud.yml)。
如果容器无法联网下载 Typst，可将宿主机 `typst` 映射进容器。

---

## 4. 配置项（环境变量）

后端默认值已在 [server.py](webapp/backend/server.py#L34-L40) 落地：

- `AIDOC_WEB_HOST`：监听地址（默认 `127.0.0.1`，Docker 常用 `0.0.0.0`）
- `AIDOC_WEB_PORT`：监听端口（默认 `8008`）
- `AIDOC_LOG_DIR`：日志目录（可选）

### 上传与请求限制
- `AIDOC_MAX_TEMPLATE_UPLOAD_BYTES`：模板上传上限（默认 `10485760`，10MB）
- `AIDOC_MAX_MARKDOWN_BYTES`：Markdown 请求上限（默认 `2097152`，2MB）

### 任务清理策略
- `AIDOC_SUCCESS_TTL_SECONDS`：成功任务保留时间（默认 `86400`，24h）
- `AIDOC_FAILED_TTL_SECONDS`：失败任务保留时间（默认 `21600`，6h）
- `AIDOC_CLEANUP_INTERVAL_SECONDS`：清理周期（默认 `900`，15min）
- `AIDOC_MAX_JOB_DIRS`：任务目录最大数量（默认 `500`）
- `AIDOC_MAX_JOB_TOTAL_BYTES`：任务目录总大小上限（默认 `2147483648`，2GB）

---

## 5. API 概览

接口定义在 [server.py](webapp/backend/server.py)：

- `GET /api/health`：健康检查 + 当前限制参数
- `GET /api/templates`：模板列表
- `POST /api/templates`：上传模板（`.docx`，10MB 限制）
- `POST /api/preview`：Markdown 预览（2MB 限制）
- `POST /api/convert`：创建转换任务（2MB 限制）
- `GET /api/jobs/{job_id}`：任务状态
- `POST /api/jobs/{job_id}/cancel`：取消任务
- `GET /api/jobs/{job_id}/download/{fmt}`：下载产物
- `GET /api/logs`：读取日志
- `POST /api/cleanup`：手动触发清理

---

## 6. 日志、缓存与运行数据路径

### 日志路径

由 [core/logger.py](core/logger.py#L7-L35) 按优先级选择：
1. `AIDOC_LOG_DIR`
2. `<项目根>/logs`
3. Windows：`%LOCALAPPDATA%/DocForge/logs`
4. Linux/macOS：`~/.docforge/logs`

日志文件：`app.log`

### 运行数据

- 任务目录：`webapp/runtime/jobs/<job_id>/`
- 上传模板：`webapp/uploads/templates/`
- 模板显示名映射：`webapp/uploads/templates/_manifest.json`

### 配置缓存（桌面版）

- `~/.aidoc-styler/config.json`（见 [core/config.py](core/config.py#L5-L22)）

### Python 缓存

- `__pycache__/`、`*.pyc` 为解释器缓存，可安全删除

---

## 7. 清理策略说明（当前实现）

策略在 [job_store.py](webapp/backend/job_store.py#L66-L171)：

- 先按状态 TTL 清理：
  - `succeeded` 超过 24h 清理
  - `failed` 超过 6h 清理
- 再按容量限制清理（从最旧开始）：
  - 超过 500 个目录
  - 或总大小超过 2GB
- `queued/running` 任务不会被误删
- 对 orphan 目录也会纳入限制清理

---

## 8. 常见问题（部署与运行）

### 8.1 PDF 字体告警

如果出现 `unknown font family`，通常是容器内缺字体。  
Dockerfile 已安装 `fonts-noto-cjk` 与 `fonts-dejavu-core`，可继续按业务补充字体包。

### 8.2 图片找不到导致 PDF 失败

`converter.py` 已对本地不存在图片做降级（转普通链接，避免中断整份文档）。

### 8.3 Mermaid 云端不显示

前端已做多 CDN 回退与错误提示。若云端出网受限，建议在网络层放行对应 CDN 或改成本地静态资源。

---

## 9. 开发与打包

- 桌面版打包说明见 [BUILD.md](BUILD.md)
- Web 依赖见 [requirements.web.txt](requirements.web.txt)
- 桌面依赖见 [requirements.txt](requirements.txt)

---

## 10. 推荐运维检查项

- 定时查看 `GET /api/health`，确认限制参数与预期一致
- 监控 `webapp/runtime/jobs` 目录大小
- 监控 `logs/app.log` 增长速度
- 大流量场景建议在网关层追加请求体大小限制（与应用层双保险）
