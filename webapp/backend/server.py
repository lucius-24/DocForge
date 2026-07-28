import json
import os
import re
import subprocess
import threading
import time
from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.converter import check_pandoc_installed, convert_markdown, find_typst_executable, get_first_heading
from core.logger import get_logs, logger
from webapp.backend.job_store import JobStore


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRONTEND_DIR = os.path.join(ROOT_DIR, "webapp", "frontend")
TEMPLATES_DIR = os.path.join(ROOT_DIR, "templates")
UPLOAD_DIR = os.path.join(ROOT_DIR, "webapp", "uploads", "templates")
RUNTIME_DIR = os.path.join(ROOT_DIR, "webapp", "runtime", "jobs")
PREVIEW_TEMPLATE = os.path.join(ROOT_DIR, "preview_render_template.html")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RUNTIME_DIR, exist_ok=True)

jobs = JobStore(RUNTIME_DIR)
convert_sema = threading.Semaphore(2)

MAX_TEMPLATE_UPLOAD_BYTES = int(os.getenv("AIDOC_MAX_TEMPLATE_UPLOAD_BYTES", str(10 * 1024 * 1024)))
MAX_MARKDOWN_BYTES = int(os.getenv("AIDOC_MAX_MARKDOWN_BYTES", str(2 * 1024 * 1024)))
SUCCESS_TTL_SECONDS = int(os.getenv("AIDOC_SUCCESS_TTL_SECONDS", str(24 * 60 * 60)))
FAILED_TTL_SECONDS = int(os.getenv("AIDOC_FAILED_TTL_SECONDS", str(6 * 60 * 60)))
CLEANUP_INTERVAL_SECONDS = int(os.getenv("AIDOC_CLEANUP_INTERVAL_SECONDS", str(15 * 60)))
MAX_JOB_DIRS = int(os.getenv("AIDOC_MAX_JOB_DIRS", "500"))
MAX_JOB_TOTAL_BYTES = int(os.getenv("AIDOC_MAX_JOB_TOTAL_BYTES", str(2 * 1024 * 1024 * 1024)))


def _byte_size_mb(b: int) -> str:
    return f"{max(0, int(b)) / (1024 * 1024):.1f}MB"


def _ensure_markdown_size(markdown: str):
    size = len((markdown or "").encode("utf-8"))
    if size > MAX_MARKDOWN_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Markdown 内容过大（{_byte_size_mb(size)}），最大允许 {_byte_size_mb(MAX_MARKDOWN_BYTES)}",
        )


class PreviewRequest(BaseModel):
    markdown: str
    theme: Optional[str] = None


class ConvertRequest(BaseModel):
    markdown: str
    template: str = "academic"  # academic|internet|official|upload:<filename>
    formats: List[str] = ["docx"]
    filename: Optional[str] = None
    toc_depth: int = 3
    number_sections: bool = False
    pdf_pagebreak_after_toc: bool = True
    timeout_seconds: int = 300


app = FastAPI(title="DocForge Local Web", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _pandoc_exe() -> Optional[str]:
    try:
        import shutil
        exe = shutil.which("pandoc")
        if exe:
            return exe
    except Exception:
        pass
    try:
        import pypandoc
        return pypandoc.get_pandoc_path()
    except Exception:
        return None


def _render_preview_html(md: str, theme: Optional[str] = None) -> str:
    def _fix_double_escaped_tex(s: str) -> str:
        import re

        lines = s.splitlines()
        out = []
        in_fence = False
        for line in lines:
            if line.strip().startswith("```"):
                in_fence = not in_fence
                out.append(line)
                continue
            if in_fence:
                out.append(line)
                continue
            line = line.replace("\\\\(", "\\(").replace("\\\\)", "\\)")
            line = line.replace("\\\\[", "\\[").replace("\\\\]", "\\]")
            line = re.sub(r"\\\\([A-Za-z])", r"\\\1", line)
            line = re.sub(r"\\\\\{", r"\\{", line)

            line = re.sub(r"\\{1,2}rightarrow\b", "→", line)
            line = re.sub(r"\\{1,2}Rightarrow\b", "⇒", line)
            line = re.sub(r"\\{1,2}times\b", "×", line)

            stripped = line.strip()
            if (
                "$" not in stripped
                and "\\(" not in stripped
                and "\\[" not in stripped
                and (stripped.startswith("\\\\") or stripped.startswith("\\"))
                and not re.search(r"[\u4e00-\u9fff]", stripped)
                and re.search(r"(=|\\{1,2}equiv|\\{1,2}pmod|\\{1,2}varphi|\\{1,2}phi|\\{1,2}frac|\\{1,2}sum|\\{1,2}int)", stripped)
            ):
                candidate = stripped
                candidate = re.sub(r"\\\\\s*$", "", candidate).strip()
                candidate = re.sub(r"^\\{2}", r"\\", candidate)
                candidate = re.sub(r"\\\\([A-Za-z])", r"\\\1", candidate)
                candidate = candidate.replace("\\\\", "\\")
                line = f"\\[ {candidate} \\]"
            out.append(line)
        return "\n".join(out)

    pandoc = _pandoc_exe()
    if not pandoc:
        raise RuntimeError("未找到 Pandoc。无法生成预览。")
    cmd = [
        pandoc,
        "-f",
        "markdown+tex_math_dollars+tex_math_single_backslash+tex_math_double_backslash",
        "-t",
        "html",
        "-s",
        "--mathml",
        "--highlight-style=tango",
    ]
    if theme and str(theme).lower() == "light":
        cmd.extend(["-V", "df_light=1"])
    if os.path.exists(PREVIEW_TEMPLATE):
        cmd.append(f"--template={PREVIEW_TEMPLATE}")

    proc = subprocess.run(
        cmd,
        input=_fix_double_escaped_tex(md).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(err or "Pandoc 预览失败")
    html = proc.stdout.decode("utf-8", errors="ignore")

    if theme and str(theme).lower() == "light":
        def _ensure_html_class(doc: str, cls: str) -> str:
            m = re.search(r"<html\b([^>]*)>", doc, flags=re.IGNORECASE)
            if not m:
                return doc
            attrs = m.group(1) or ""
            m2 = re.search(r'\bclass\s*=\s*"([^"]*)"', attrs, flags=re.IGNORECASE)
            if m2:
                cur = m2.group(1)
                if cls in cur.split():
                    return doc
                new_attrs = attrs.replace(m2.group(0), f'class="{(cur + " " + cls).strip()}"')
                return doc[: m.start(1)] + new_attrs + doc[m.end(1) :]
            return doc[: m.end(0) - 1] + f' class="{cls}">' + doc[m.end(0) :]

        html = _ensure_html_class(html, "df-light")

    return html


def _resolve_template_path(template_key: str) -> Optional[str]:
    if template_key.startswith("upload:"):
        fn = template_key.split("upload:", 1)[1]
        path = os.path.join(UPLOAD_DIR, fn)
        return path if os.path.exists(path) else None

    mapping = {
        "academic": os.path.join(TEMPLATES_DIR, "academic.docx"),
        "internet": os.path.join(TEMPLATES_DIR, "internet.docx"),
        "official": os.path.join(TEMPLATES_DIR, "official.docx"),
    }
    path = mapping.get(template_key)
    return path if path and os.path.exists(path) else None


def _do_convert(job_id: str, req: ConvertRequest):
    job = jobs.get(job_id)
    if not job:
        return
    if getattr(job, "cancel_requested", False):
        jobs.update(job_id, status="failed", error="已取消")
        return
    jobs.update(job_id, status="running", error=None)

    acquired = convert_sema.acquire(timeout=600)
    if not acquired:
        jobs.update(job_id, status="failed", error="转换队列繁忙，请稍后重试。")
        return

    try:
        job_dir = jobs.job_dir(job_id)
        template_path = _resolve_template_path(req.template)
        outputs = {}

        base_name = (req.filename or "").strip()
        if not base_name:
            base_name = get_first_heading(req.markdown) or "output"
        base_name = "".join([c for c in base_name if c.isalnum() or c in (" ", "-", "_") or ("\u4e00" <= c <= "\u9fff")]).strip()
        if not base_name:
            base_name = "output"
        for fmt in req.formats:
            if getattr(jobs.get(job_id), "cancel_requested", False):
                jobs.update(job_id, status="failed", error="已取消")
                return
            fmt = fmt.lower().strip()
            if fmt not in ("docx", "pdf"):
                continue
            out_path = os.path.join(job_dir, f"{base_name}.{fmt}")
            res = convert_markdown(
                req.markdown,
                out_path,
                reference_doc=template_path if fmt == "docx" else None,
                output_format=fmt,
                toc=True,
                toc_depth=req.toc_depth,
                number_sections=req.number_sections,
                pdf_pagebreak_after_toc=req.pdf_pagebreak_after_toc,
                timeout_seconds=req.timeout_seconds,
            )
            
            # 兼容处理返回值：它可能是一个元组 (bool, str) 也可能由于某些未捕获的异常只返回了一个 None 或 bool
            if isinstance(res, tuple) and len(res) >= 2:
                ok, msg = res[0], res[1]
            elif isinstance(res, tuple) and len(res) == 1:
                ok, msg = res[0], "Unknown error"
            elif res is None:
                # Log this specific None case for debugging
                logger.error(f"convert_markdown returned None for job {job_id} format {fmt}")
                ok, msg = False, "Conversion returned None"
            else:
                ok, msg = bool(res), str(res)
                
            if not ok:
                if isinstance(msg, tuple):
                    msg = msg[0] if len(msg) > 0 else "Unknown error"
                jobs.update(job_id, status="failed", error=str(msg))
                return
            outputs[fmt] = out_path

        jobs.update(job_id, status="succeeded", outputs=outputs)
    except Exception as e:
        logger.exception(f"Job {job_id} failed: {e}")
        jobs.update(job_id, status="failed", error=str(e))
    finally:
        convert_sema.release()


@app.get("/api/health")
def health():
    pandoc_ok = check_pandoc_installed()
    typst = find_typst_executable()
    return {
        "ok": True,
        "pandoc": {"ok": pandoc_ok},
        "typst": {"path": typst, "ok": bool(typst)},
        "limits": {
            "max_template_upload_bytes": MAX_TEMPLATE_UPLOAD_BYTES,
            "max_markdown_bytes": MAX_MARKDOWN_BYTES,
            "success_ttl_seconds": SUCCESS_TTL_SECONDS,
            "failed_ttl_seconds": FAILED_TTL_SECONDS,
            "cleanup_interval_seconds": CLEANUP_INTERVAL_SECONDS,
            "max_job_dirs": MAX_JOB_DIRS,
            "max_job_total_bytes": MAX_JOB_TOTAL_BYTES,
        },
    }


@app.get("/api/templates")
def list_templates():
    manifest_path = os.path.join(UPLOAD_DIR, "_manifest.json")
    manifest = {}
    try:
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f) or {}
    except Exception:
        manifest = {}

    built_in = [
        {"key": "official", "name": "公文风"},
        {"key": "internet", "name": "互联网风"},
        {"key": "academic", "name": "学术风"},
    ]
    uploads = []
    import re
    for fn in sorted(os.listdir(UPLOAD_DIR)):
        if fn.lower().endswith(".docx"):
            display = manifest.get(fn)
            if not display:
                m = re.match(r"^(.*)_([0-9a-f]{8})\.docx$", fn, flags=re.IGNORECASE)
                if m:
                    display = m.group(1)
                else:
                    display = os.path.splitext(fn)[0]
            display = os.path.splitext(str(display))[0]
            uploads.append({"key": f"upload:{fn}", "name": f"自定义：{display}"})
    return {"built_in": built_in, "uploads": uploads}


@app.post("/api/templates")
async def upload_template(file: UploadFile = File(...), name: str = Form("")):
    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="仅支持 .docx 模板")

    display_name = (name or "").strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="必须填写模板名称")
    display_name = os.path.splitext(display_name)[0].strip()
    display_name = "".join(
        [c for c in display_name if c.isalnum() or c in (" ", "-", "_") or ("\u4e00" <= c <= "\u9fff")]
    ).strip()
    if not display_name:
        display_name = "template"

    file_base = display_name.replace(" ", "_")

    import uuid
    stored = f"{file_base}_{uuid.uuid4().hex[:8]}.docx"
    out_path = os.path.join(UPLOAD_DIR, stored)
    total = 0
    try:
        with open(out_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_TEMPLATE_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"模板文件过大（{_byte_size_mb(total)}），最大允许 {_byte_size_mb(MAX_TEMPLATE_UPLOAD_BYTES)}",
                    )
                f.write(chunk)
    except HTTPException:
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass
        raise

    manifest_path = os.path.join(UPLOAD_DIR, "_manifest.json")
    manifest = {}
    try:
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f) or {}
    except Exception:
        manifest = {}
    manifest[stored] = display_name
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return {"ok": True, "key": f"upload:{stored}", "name": display_name}


@app.post("/api/preview")
def preview(req: PreviewRequest):
    try:
        _ensure_markdown_size(req.markdown)
        html = _render_preview_html(req.markdown, theme=req.theme)
        return HTMLResponse(content=html)
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/convert")
def convert(req: ConvertRequest, background: BackgroundTasks):
    _ensure_markdown_size(req.markdown)
    job = jobs.create()
    background.add_task(_do_convert, job.id, req)
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "id": job.id,
        "status": job.status,
        "error": job.error,
        "outputs": list(job.outputs.keys()),
    }


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status in ("succeeded", "failed"):
        return {"ok": True, "status": job.status}
    jobs.update(job_id, cancel_requested=True)
    return {"ok": True, "status": "cancel_requested"}


def _cleanup_loop():
    while True:
        try:
            jobs.cleanup_with_policy(
                success_ttl_seconds=SUCCESS_TTL_SECONDS,
                failed_ttl_seconds=FAILED_TTL_SECONDS,
                max_job_dirs=MAX_JOB_DIRS,
                max_total_bytes=MAX_JOB_TOTAL_BYTES,
            )
        except Exception:
            pass
        time.sleep(max(60, CLEANUP_INTERVAL_SECONDS))


@app.on_event("startup")
def _startup():
    t = threading.Thread(target=_cleanup_loop, daemon=True)
    t.start()


@app.get("/api/jobs/{job_id}/download/{fmt}")
def download(job_id: str, fmt: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status != "succeeded":
        raise HTTPException(status_code=400, detail="任务未完成")
    path = job.outputs.get(fmt)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=os.path.basename(path))


@app.get("/api/logs")
def logs_api():
    return {"logs": get_logs()}


@app.post("/api/cleanup")
def cleanup():
    result = jobs.cleanup_with_policy(
        success_ttl_seconds=SUCCESS_TTL_SECONDS,
        failed_ttl_seconds=FAILED_TTL_SECONDS,
        max_job_dirs=MAX_JOB_DIRS,
        max_total_bytes=MAX_JOB_TOTAL_BYTES,
    )
    return result

def _svg_file(filename: str) -> FileResponse:
    path = os.path.join(ROOT_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"{filename} not found")
    return FileResponse(path, filename=filename, media_type="image/svg+xml")


@app.get("/favicon.svg")
def favicon_svg():
    return _svg_file("favicon.svg")


@app.get("/logo.svg")
def logo_svg():
    return _svg_file("logo.svg")


@app.get("/favicon.ico", response_class=RedirectResponse)
def favicon():
    return RedirectResponse(url="/favicon.svg", status_code=307)


@app.get("/logo.png", response_class=RedirectResponse)
def logo_png():
    return RedirectResponse(url="/logo.svg", status_code=307)

# Web版不再需要本地GUI的图标资源，因此这里不再挂载 assets 目录
# assets_dir = os.path.join(ROOT_DIR, "assets")
# if os.path.isdir(assets_dir):
#     app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
