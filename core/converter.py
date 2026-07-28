import io
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET

import pypandoc
from PIL import Image

logger = logging.getLogger(__name__)


def _subprocess_run_kwargs():
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


def find_typst_executable():
    if os.name == "nt":
        candidates = [
            os.path.join(os.getcwd(), "typst.exe"),
            os.path.join(os.getcwd(), "typst-x86_64-pc-windows-msvc", "typst.exe"),
            os.path.join(os.path.dirname(sys.executable), "typst.exe"),
            os.path.join(os.path.dirname(sys.executable), "typst", "typst.exe"),
            "C:\\Program Files\\Typst\\typst.exe",
            "C:\\typst\\typst.exe",
        ]
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "typst.exe"))
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
        typst_in_path = shutil.which("typst")
        if typst_in_path:
            return typst_in_path
    else:
        for path in ["/usr/local/bin/typst", "/usr/bin/typst", "/opt/typst/typst"]:
            if os.path.isfile(path):
                return path
        return shutil.which("typst")
    return None


def _clean_markdown(text: str) -> str:
    """
    Clean invisible characters and normalize newlines before feeding into Pandoc.
    """
    if not text:
        return text
        
    # 修复包含反引号、多余空格或引号的错误图片链接，例如：![](`https://...`)
    text = re.sub(r'!\[([^\]]*)\]\(\s*[`\'"]?\s*(https?://[^\s`\'")]+)\s*[`\'"]?\s*\)', r'![\1](\2)', text)

    # 自动修正 GitHub Blob 图片链接为 Raw 链接
    # 匹配 https://github.com/user/repo/blob/branch/path/to/image.png
    # 替换为 https://github.com/user/repo/raw/branch/path/to/image.png
    text = re.sub(r'(https?://github\.com/[^/]+/[^/]+)/blob/', r'\1/raw/', text)

    # 移除或降级非图片扩展名的图片链接 (如 .html, .shtml, .php)
    def _demote_html_image(match):
        alt = match.group(1)
        url = match.group(2)
        if re.search(r'\.(s?html?|php|jsp|asp)($|\?)', url, re.IGNORECASE):
            return f"[{alt}]({url})"
        url = url.strip().strip('\'"').strip()
        if re.match(r'^(https?:)?//', url, re.IGNORECASE) or url.startswith('data:'):
            return f"![{alt}]({url})"
        if url.startswith("file://"):
            local_path = url[7:]
            if os.path.exists(local_path):
                return f"![{alt}]({url})"
            return f"[{alt or '图片缺失'}]({url})"
        candidate = url.split("?", 1)[0].split("#", 1)[0]
        if os.path.isabs(candidate):
            exists = os.path.exists(candidate)
        else:
            exists = os.path.exists(os.path.join(os.getcwd(), candidate))
        if not exists:
            return f"[{alt or '图片缺失'}]({url})"
        return f"![{alt}]({url})"
    
    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _demote_html_image, text)

    # Remove zero-width characters
    zero_width_pattern = r'[\u200B\u200C\u200D\uFEFF]'
    text = re.sub(zero_width_pattern, '', text)
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Strip trailing spaces on each line to avoid odd wrapping
    text = '\n'.join(line.rstrip() for line in text.split('\n'))
    # Remove horizontal rules (---, ***, ___) to avoid Word drawing lines between sections
    cleaned_lines = []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped in ('---', '***', '___') or (all(ch == '-' for ch in stripped) and len(stripped) >= 3):
            continue
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)
    text = text.replace('⚠️', '⚠')
    return text


def _docx_postprocess(docx_path: str):
    """
    Post-process the generated docx to fix styles and fonts.
    IMPORTANT: Uses regex manipulation instead of ElementTree to preserve
    all document content including TOC fields and complex structures.
    ElementTree's namespace rewriting was destroying document content.
    """
    if not os.path.exists(docx_path):
        return

    temp_dir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(docx_path, 'r') as zin:
            zin.extractall(temp_dir)

        font_replacements = {
            "Normal": "Microsoft YaHei",
            "Title": "Microsoft YaHei",
            "Heading1": "Microsoft YaHei",
            "Heading2": "Microsoft YaHei",
            "Heading3": "Microsoft YaHei",
            "Heading4": "Microsoft YaHei",
            "Heading5": "Microsoft YaHei",
            "Heading6": "Microsoft YaHei",
            "TOC1": "Microsoft YaHei",
            "TOC2": "Microsoft YaHei",
            "TOC3": "Microsoft YaHei",
            "Code": "Consolas",
            "CodeBlock": "Consolas",
            "SourceCode": "Consolas",
        }

        # 1. Modify styles.xml with regex
        styles_path = os.path.join(temp_dir, 'word', 'styles.xml')
        if os.path.exists(styles_path):
            with open(styles_path, 'r', encoding='utf-8') as f:
                styles_content = f.read()

            styles_content = re.sub(r'w:(ascii|eastAsia|hAnsi|cs)Theme="[^"]*"', '', styles_content)
            styles_content = re.sub(r'w:cstheme="[^"]*"', '', styles_content)

            for style_id, font_name in font_replacements.items():
                pattern = rf'(<w:style\b[^>]*\bw:styleId="{style_id}"[^>]*>)(.*?)(</w:style>)'
                def replace_style_font(m, fn=font_name):
                    open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)
                    if '<w:rFonts' in inner:
                        inner = re.sub(
                            r'<w:rFonts[^/]*/?>',
                            f'<w:rFonts w:ascii="{fn}" w:hAnsi="{fn}" w:eastAsia="{fn}" w:cs="{fn}"/>',
                            inner
                        )
                    else:
                        inner = re.sub(
                            r'(<w:pPr\b[^>]*>)',
                            r'\1<w:rFonts w:ascii="' + fn + r'" w:hAnsi="' + fn + r'" w:eastAsia="' + fn + r'" w:cs="' + fn + r'"/>',
                            inner
                        )
                    return open_tag + inner + close_tag

                styles_content = re.sub(pattern, replace_style_font, styles_content, flags=re.DOTALL)

            with open(styles_path, 'w', encoding='utf-8') as f:
                f.write(styles_content)

        # 2. Modify document.xml with regex (preserve ALL content including TOC)
        doc_path = os.path.join(temp_dir, 'word', 'document.xml')
        if os.path.exists(doc_path):
            with open(doc_path, 'r', encoding='utf-8') as f:
                doc_content = f.read()

            # Remove w:pBdr (paragraph borders / horizontal lines) while preserving all else
            doc_content = re.sub(r'<w:pBdr>.*?</w:pBdr>', '', doc_content, flags=re.DOTALL)

            # Add light gray shading to CodeBlock paragraphs
            def add_shading_to_codeblock(m):
                ppr = m.group(1)
                if '<w:shd' in ppr:
                    ppr = re.sub(r'<w:shd[^/]*/>', '<w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/>', ppr)
                else:
                    ppr = re.sub(r'(<w:pPr\b[^>]*)(>)', r'\1><w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/>', ppr)
                return m.group(0).replace(m.group(1), ppr)

            doc_content = re.sub(
                r'<w:p>(<w:pPr>.*?)<w:pStyle w:val="CodeBlock"/>.*?</w:p>',
                add_shading_to_codeblock,
                doc_content,
                flags=re.DOTALL
            )

            with open(doc_path, 'w', encoding='utf-8') as f:
                f.write(doc_content)

        # 3. Modify settings.xml to request field update on open (MS Word / WPS compatibility)
        settings_path = os.path.join(temp_dir, 'word', 'settings.xml')
        if os.path.exists(settings_path):
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings_content = f.read()

            # Add updateFields to force all applications to update TOC on open
            # Only add if not already present
            if 'updateFields' not in settings_content:
                # Insert after <w:settings ...> opening tag
                settings_content = re.sub(
                    r'(<w:settings\b[^>]*>)',
                    r'\1<w:updateFields w:val="true"/>',
                    settings_content
                )

            with open(settings_path, 'w', encoding='utf-8') as f:
                f.write(settings_content)

        # 4. Repack
        tmp_path = docx_path + ".tmp"
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for dirpath, _, filenames in os.walk(temp_dir):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    arcname = os.path.relpath(filepath, temp_dir)
                    zout.write(filepath, arcname)

        for _ in range(8):
            try:
                os.replace(tmp_path, docx_path)
                break
            except Exception:
                time.sleep(0.2)

    except Exception as e:
        logger.error(f"Docx post-process failed: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def convert_markdown(
    md_content,
    output_path,
    reference_doc=None,
    output_format='docx',
    toc: bool = True,
    toc_depth: int = 3,
    number_sections: bool = False,
    pdf_pagebreak_after_toc: bool = True,
    timeout_seconds: int = 300,
):
    logger.info(f"Starting conversion: format={output_format}, output={output_path}")

    pandoc_exe = None
    frozen_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else None
    candidates = []
    if frozen_dir:
        candidates.append(os.path.join(frozen_dir, "pandoc.exe"))
        candidates.append(os.path.join(frozen_dir, "pandoc", "pandoc.exe"))
    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "pandoc.exe"))
    candidates.append(os.path.join(os.getcwd(), "pandoc.exe"))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            pandoc_exe = candidate
            break
    if not pandoc_exe:
        pandoc_exe = shutil.which("pandoc")
    if not pandoc_exe:
        try:
            pandoc_exe = pypandoc.get_pandoc_path()
        except Exception:
            pandoc_exe = None

    if not pandoc_exe:
        logger.error("Pandoc not found")
        return False, "未找到 Pandoc。请安装 Pandoc 并确保已加入 PATH。"

    input_format = 'markdown+task_lists+pipe_tables+tex_math_dollars+fenced_code_blocks+backtick_code_blocks+auto_identifiers'
    cmd = [pandoc_exe, '-f', input_format, '-t', output_format, '-o', output_path]
    cmd.extend(['--highlight-style=tango'])
    if toc:
        cmd.append('--toc')
        cmd.append(f'--toc-depth={max(1, min(int(toc_depth or 3), 6))}')
    if number_sections:
        cmd.append('--number-sections')

    if output_format == 'docx':
        cmd.append('--shift-heading-level-by=0')
        cmd.append('--mathml')
        if reference_doc and os.path.exists(reference_doc):
            cmd.append(f'--reference-doc={reference_doc}')
    elif output_format == 'pdf':
        pdf_engine = shutil.which("xelatex")
        if "AIDOC_WEB_HOST" in os.environ:
            typst_exe = find_typst_executable()
            if typst_exe:
                pdf_engine = None

        if os.name == "nt":
            mainfont = "Microsoft YaHei"
            sansfont = "Microsoft YaHei"
            monofont = "Consolas"
            cjkfont = "Microsoft YaHei"
            typst_main = '"Microsoft YaHei"'
            typst_mono = '"Consolas"'
        else:
            mainfont = "Noto Sans CJK SC"
            sansfont = "Noto Sans CJK SC"
            monofont = "DejaVu Sans Mono"
            cjkfont = "Noto Sans CJK SC"
            typst_main = '("Noto Sans CJK SC", "Noto Sans CJK", "Noto Sans SC", "DejaVu Sans", "Liberation Sans", "Arial")'
            typst_mono = '"DejaVu Sans Mono"'

        if pdf_engine:
            cmd.append(f'--pdf-engine={pdf_engine}')
            cmd.extend(['-V', f'mainfont={mainfont}'])
            cmd.extend(['-V', f'sansfont={sansfont}'])
            cmd.extend(['-V', f'monofont={monofont}'])
            cmd.extend(['-V', f'CJKmainfont={cjkfont}'])
        else:
            typst_exe = find_typst_executable()
            if not typst_exe:
                logger.error("Neither xelatex nor typst found")
                return False, "未找到 PDF 引擎。请安装 MikTeX/TeX Live (xelatex) 或 Typst CLI。"
            cmd.append(f'--pdf-engine={typst_exe}')
            cmd.extend(['-V', f'mainfont={mainfont}'])
            cmd.extend(['-V', f'sansfont={sansfont}'])
            cmd.extend(['-V', f'monofont={monofont}'])
            if os.name == 'nt':
                drive = os.path.splitdrive(os.getcwd())[0]
                cmd.append(f'--pdf-engine-opt=--root={drive}\\' if drive else '--pdf-engine-opt=--root=..\\..\\..\\..\\..\\')
            else:
                cmd.append('--pdf-engine-opt=--root=/')

    run_env = os.environ.copy()

    preamble_file = None
    if output_format == 'pdf' and pdf_engine:
        try:
            tmpdir = None
            if os.name == 'nt':
                tmpdir = tempfile.TemporaryDirectory(dir=os.getcwd(), prefix=".aidoc_tmp_")
                preamble_fd, preamble_path = tempfile.mkstemp(suffix=".tex", dir=tmpdir.name)
                preamble_file = os.fdopen(preamble_fd, "w", encoding="utf-8")
            else:
                preamble_path = None
                preamble_file = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".tex", delete=False)
                preamble_path = preamble_file.name
            preamble_file.write(r"\usepackage{tcolorbox}" + "\n")
            preamble_file.write(r"\usepackage{amssymb}" + "\n")
            preamble_file.write(r"\newtcolorbox{mycode}{colback=gray!10!white,colframe=gray!20!white,arc=4pt}" + "\n")
            preamble_file.flush()
            preamble_file.close()
            preamble_file = None
            cmd.append(f'--include-before-body={preamble_path}')
            run_env["TEMP"] = tmpdir.name if tmpdir else tempfile.gettempdir()
            run_env["TMP"] = run_env["TEMP"]
            run_env["TMPDIR"] = run_env["TEMP"]
        except Exception as e:
            logger.warning(f"Failed to create preamble: {e}")
            if preamble_file and not preamble_file.closed:
                preamble_file.close()
            if tmpdir:
                try:
                    tmpdir.cleanup()
                except:
                    pass
            preamble_file = None
    elif output_format == 'pdf' and not pdf_engine:
        typst_preamble_lines = []
        if pdf_pagebreak_after_toc:
            typst_preamble_lines.append("#show outline: it => { it; pagebreak() }")
        typst_preamble_lines.append(f"#set text(font: {typst_main})")
        typst_preamble_lines.append(f"#show raw: set text(font: {typst_mono})")
        typst_preamble_lines.append("#show raw.where(block: true): it => block(")
        typst_preamble_lines.append('  fill: rgb("#f5f5f5"),')
        typst_preamble_lines.append("  inset: 10pt,")
        typst_preamble_lines.append("  radius: 4pt,")
        typst_preamble_lines.append("  width: 100%,")
        typst_preamble_lines.append("  it")
        typst_preamble_lines.append(")")
        typst_preamble = "\n".join(typst_preamble_lines) + "\n"
        try:
            tmpdir = None
            if os.name == 'nt':
                tmpdir = tempfile.TemporaryDirectory(dir=os.getcwd(), prefix=".aidoc_tmp_")
                preamble_fd, preamble_path = tempfile.mkstemp(suffix=".typ", dir=tmpdir.name)
                preamble_file = os.fdopen(preamble_fd, "w", encoding="utf-8")
            else:
                preamble_path = None
                preamble_file = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".typ", delete=False)
                preamble_path = preamble_file.name
            preamble_file.write(typst_preamble)
            preamble_file.flush()
            preamble_file.close()
            preamble_file = None
            cmd.append(f'--include-before-body={preamble_path}')
            run_env["TEMP"] = tmpdir.name if tmpdir else tempfile.gettempdir()
            run_env["TMP"] = run_env["TEMP"]
            run_env["TMPDIR"] = run_env["TEMP"]
        except Exception as e:
            logger.warning(f"Failed to create typst preamble: {e}")
            if preamble_file and not preamble_file.closed:
                preamble_file.close()
            if tmpdir:
                try:
                    tmpdir.cleanup()
                except:
                    pass
            preamble_file = None

    try:
        logger.info(f"Running command: {' '.join(cmd)}")
        process = subprocess.run(
            cmd,
            input=_clean_markdown(md_content).encode('utf-8'),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=max(5, int(timeout_seconds or 300)),
            env=run_env,
            **_subprocess_run_kwargs()
        )

        if process.returncode == 0:
            if output_format == "docx":
                try:
                    _docx_postprocess(output_path)
                except Exception as e:
                    logger.error(f"DOCX postprocess failed: {e}")
            logger.info("Conversion successful")
            return True, "Conversion successful"
        else:
            stderr_bytes = process.stderr
            try:
                error_msg = stderr_bytes.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    error_msg = stderr_bytes.decode('mbcs')
                except:
                    error_msg = stderr_bytes.decode('utf-8', errors='replace')
            logger.error(f"Pandoc Error: {error_msg}")
            if output_format == 'pdf' and any(x in error_msg for x in ['pdflatex not found', 'xelatex not found', 'typst']):
                return False, "PDF generation requires a PDF engine (Typst or TeX Live/MiKTeX). Please install it or use Word export."
            return False, f"Pandoc Error: {error_msg}"
    except subprocess.TimeoutExpired:
        logger.error("Pandoc timeout")
        return False, "转换超时"
    except Exception as e:
        logger.error(f"Conversion failed: {e}")
        return False, f"转换失败: {str(e)}"
    return False, "Unknown error"


def get_first_heading(md_content):
    """
    Extract the first level 1 heading to use as filename.
    """
    for line in md_content.splitlines():
        if line.strip().startswith('# '):
            return line.strip()[2:].strip()
    return None


def check_pandoc_installed() -> bool:
    try:
        subprocess.run(['pandoc', '--version'], capture_output=True, check=True, **_subprocess_run_kwargs())
        return True
    except Exception:
        return False
