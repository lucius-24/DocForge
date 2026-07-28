import customtkinter as ctk
import os
import threading
import sys
import tkinter as tk
import ctypes
from tkinter import filedialog, messagebox
from customtkinter import CTkInputDialog
import subprocess
import platform
import logging
import tempfile
import shutil
import re
import ast
from urllib.parse import unquote, urlparse

# Enable High DPI Awareness
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# 引入 tkinterweb 用于预览
try:
    from tkinterweb import HtmlFrame
    WEB_PREVIEW_AVAILABLE = True
except ImportError:
    WEB_PREVIEW_AVAILABLE = False
    print("警告: 未检测到 tkinterweb，预览功能可能受限。请运行 'pip install tkinterweb'")

# Configure logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _app_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _resource_path(*parts):
    return os.path.join(_app_root(), *parts)

def _subprocess_run_kwargs():
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs

def _normalize_preview_markdown(text: str) -> str:
    if not text:
        return text
    lines = text.splitlines()
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

sys.path.append(_app_root())

from core.converter import convert_markdown, get_first_heading, check_pandoc_installed
import pyperclip
from core.config import set_key, get_config
from core.logger import logger
from PIL import Image

# Use custom neon theme
theme_path = _resource_path("themes", "neon_dark.json")
ctk.set_appearance_mode("Dark")
if os.path.exists(theme_path):
    ctk.set_default_color_theme(theme_path)
else:
    ctk.set_default_color_theme("dark-blue")

from ui.settings_dialog import SettingsDialog
from ui.sidebar import Sidebar

class App(ctk.CTk):
    def _apply_window_icon(self):
        ico_path = _resource_path("assets", "icons", "app_icon.ico")
        png_path = _resource_path("assets", "icons", "play_white.png")
        try:
            if os.path.exists(ico_path):
                self.iconbitmap(ico_path)
        except Exception:
            pass
        try:
            if os.path.exists(png_path):
                self._window_icon = tk.PhotoImage(file=png_path)
                self.iconphoto(True, self._window_icon)
        except Exception:
            pass

    def _pick_ui_font_family(self):
        candidates = [
            "Source Han Sans CN",
            "Source Han Sans SC",
            "Noto Sans CJK SC",
            "思源雅黑",
            "微软雅黑",
            "Microsoft YaHei",
        ]
        try:
            families = set(self.tk.call("font", "families"))
        except Exception:
            families = set()

        for name in candidates:
            if name in families:
                return name
        return "Microsoft YaHei"

    def __init__(self):
        super().__init__()
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AIDOC.AIDOC")
        except Exception:
            pass
        
        # Load Icons
        self.icon_path = _resource_path("assets", "icons")
        self.icons = {}
        try:
            self.icons['play'] = ctk.CTkImage(light_image=Image.open(os.path.join(self.icon_path, "play_white.png")), size=(20, 20))
            self.icons['clear'] = ctk.CTkImage(light_image=Image.open(os.path.join(self.icon_path, "clear_white.png")), size=(16, 16))
        except Exception:
            pass
        
        # --- Config & Init ---
        self.config = get_config()
        self.monitor_clipboard_enabled = self.config.get("monitor_clipboard", True)
        self.custom_templates = self.config.get("custom_templates", {})
        
        # Load typst path from config into environment (for converter)
        try:
            typst_cfg = self.config.get("typst_exe")
            if typst_cfg and os.path.isfile(typst_cfg):
                os.environ["TYPST_EXE"] = typst_cfg
        except Exception:
            pass
        
        self.title("DocForge")
        self.geometry("1100x700")
        self._apply_window_icon()

        # Configure fonts
        self.font_family = self._pick_ui_font_family()
        
        # Grid configuration
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Callbacks for Sidebar
        callbacks = {
            'change_template': self.change_template_event,
            'upload_template': self.upload_template,
            'open_file': self.open_markdown_file,
            'preview_browser': self.preview_in_browser,
            'open_settings': self.open_settings,
            'delete_template': self.delete_template
        }

        # Sidebar (Left)
        self.sidebar_frame = Sidebar(self, self.font_family, callbacks)
        self.sidebar_frame.grid(row=0, column=0, rowspan=4, sticky="nsew")

        self.template_option_menu = self.sidebar_frame.template_option_menu
        self._refresh_template_dropdown()
        
        # Main Area (Right)
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=(10, 20), pady=20)
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        
        # Tabview
        self.tabview = ctk.CTkTabview(self.main_frame, corner_radius=12, fg_color="#2b2b2b", border_width=1, border_color="#333333")
        self.tabview.grid(row=0, column=0, sticky="nsew")
        self.tabview.add("编辑")
        self.tabview.add("预览")
        try:
            self.tabview._segmented_button.configure(font=ctk.CTkFont(family=self.font_family, size=13, weight="bold"))
        except Exception:
            pass

        # 编辑区
        self.textbox = ctk.CTkTextbox(self.tabview.tab("编辑"), font=ctk.CTkFont(family=self.font_family, size=14), wrap="word", fg_color="#1e1e1e", border_color="#333333", border_width=1)
        self.textbox.pack(fill="both", expand=True, padx=10, pady=10)

        # 预览区
        if WEB_PREVIEW_AVAILABLE:
            self.preview_container = ctk.CTkFrame(self.tabview.tab("预览"), fg_color="#1e1e1e")
            self.preview_container.pack(fill="both", expand=True, padx=10, pady=10)
            self.preview_container.grid_rowconfigure(0, weight=1)
            self.preview_container.grid_columnconfigure(0, weight=1)

            self.preview_box = HtmlFrame(
                self.preview_container,
                messages_enabled=False,
                vertical_scrollbar=False,
                horizontal_scrollbar=False
            )
            self.preview_box.grid(row=0, column=0, sticky="nsew")

            self.preview_scrollbar = ctk.CTkScrollbar(
                self.preview_container,
                orientation="vertical",
                command=lambda *args: self.preview_box.html.yview(*args)
            )
            self.preview_scrollbar.grid(row=0, column=1, sticky="ns")
            self.preview_box.html.configure(yscrollcommand=self.preview_scrollbar.set)
            self._bind_preview_mousewheel()
        else:
            self.preview_box = ctk.CTkTextbox(self.tabview.tab("预览"), font=ctk.CTkFont(family=self.font_family, size=14), wrap="word", fg_color="#1e1e1e", border_color="#333333", border_width=1)
            self.preview_box.pack(fill="both", expand=True, padx=10, pady=10)
            self.preview_box.configure(state="disabled")

        self.default_text = "# 在此粘贴 Markdown 内容...\n\n或者点击左侧“打开 .md 文件”。"
        self.textbox.insert("1.0", self.default_text)
        
        # 性能防抖定时器初始化
        self._preview_timer = None
        self.textbox.bind("<KeyRelease>", self.update_preview_event)
        self.update_preview()

        # Action Bar
        self.action_frame = ctk.CTkFrame(self.main_frame, height=70, corner_radius=8, border_width=1, border_color="#2b2b2b", fg_color="#202020")
        self.action_frame.grid(row=1, column=0, sticky="ew", pady=(15, 0))
        self.action_frame.grid_propagate(False)
        
        self.generate_btn = ctk.CTkButton(self.action_frame, text="生成并打开 Word", 
                                          image=self.icons.get('play'),
                                          command=self.generate_document, 
                                          height=40, width=180,
                                          font=ctk.CTkFont(family=self.font_family, size=14, weight="bold"),
                                          fg_color="#3B8ED0", hover_color="#36719F", text_color="#DCE4EE")
        self.generate_btn.pack(side="left", padx=20, pady=15)
        
        self.clear_btn = ctk.CTkButton(self.action_frame, text="清空", 
                                       image=self.icons.get('clear'),
                                       command=self.clear_editor, 
                                       height=40, width=100,
                                       font=ctk.CTkFont(family=self.font_family, size=14, weight="bold"),
                                       fg_color="#D32F2F", hover_color="#B71C1C", text_color="#FFFFFF", border_width=0)
        self.clear_btn.pack(side="left", padx=10, pady=15)
        
        self.pdf_checkbox = ctk.CTkCheckBox(self.action_frame, text="同时原生导出 PDF", 
                                            font=ctk.CTkFont(family=self.font_family, size=13),
                                            fg_color="#3B8ED0", hover_color="#36719F", 
                                            checkmark_color="#DCE4EE", text_color="gray80")
        self.pdf_checkbox.pack(side="left", padx=20, pady=15)

        # Status Bar
        self.status_frame = ctk.CTkFrame(self, height=30, corner_radius=0, fg_color=("gray90", "gray15"))
        self.status_frame.grid(row=3, column=1, sticky="ew")
        
        self.status_label = ctk.CTkLabel(self.status_frame, text=" 就绪", anchor="w", font=ctk.CTkFont(family=self.font_family, size=12))
        self.status_label.pack(side="left", padx=10, pady=2)

        if not check_pandoc_installed():
            self.status_label.configure(text="警告: 未找到 Pandoc! 请安装 Pandoc。", text_color="red")
            messagebox.showwarning("Pandoc 缺失", "转换需要安装 Pandoc。请从 https://pandoc.org/installing.html 安装。")

        self.last_clipboard = ""
        self.monitor_clipboard()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def change_template_event(self, new_template):
        return

    def update_preview_event(self, event=None):
        if self._preview_timer is not None:
            self.after_cancel(self._preview_timer)
        self._preview_timer = self.after(500, self.update_preview)

    def _bind_preview_mousewheel(self):
        if not WEB_PREVIEW_AVAILABLE:
            return
        widgets = [self.preview_container, self.preview_box, self.preview_box.html]
        for widget in widgets:
            try:
                widget.bind('<Enter>', self._on_enter_preview, add="+")
                widget.bind('<Leave>', self._on_leave_preview, add="+")
            except Exception:
                pass

    def _on_enter_preview(self, event):
        self.bind_all("<MouseWheel>", self._on_preview_mousewheel)
        self.bind_all("<Button-4>", self._on_preview_mousewheel)
        self.bind_all("<Button-5>", self._on_preview_mousewheel)

    def _on_leave_preview(self, event):
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")

    def _on_preview_mousewheel(self, event):
        if not WEB_PREVIEW_AVAILABLE:
            return None
        try:
            step = 0
            if hasattr(event, "delta") and event.delta:
                step = -int(event.delta / 120)
                if step == 0:
                    step = -1 if event.delta > 0 else 1
            elif getattr(event, "num", None) == 4:
                step = -1
            elif getattr(event, "num", None) == 5:
                step = 1
            
            if step != 0:
                self.preview_box.html.yview_scroll(step, "units")
                return "break" 
        except Exception:
            pass
        return None

    def update_preview(self):
        try:
            content = self.textbox.get("1.0", "end").strip()
        except Exception:
            content = ""
            
        if not content:
            if WEB_PREVIEW_AVAILABLE:
                self.preview_box.load_html("<html><head><style>html,body{background:#1e1e1e;margin:0;height:100%;}</style></head><body></body></html>")
            return

        if WEB_PREVIEW_AVAILABLE:
            try:
                template_path = _resource_path("preview_render_template_local.html")
                pandoc_exe = shutil.which("pandoc") or "pandoc"
                proc = subprocess.run(
                    [
                        pandoc_exe,
                        "-f",
                        "markdown+tex_math_dollars+tex_math_single_backslash+tex_math_double_backslash+fenced_code_blocks+backtick_code_blocks",
                        "-t",
                        "html",
                        "-s",
                        "--highlight-style=tango",
                        f"--template={template_path}",
                    ],
                    input=_normalize_preview_markdown(content).encode('utf-8'),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    **_subprocess_run_kwargs()
                )
                if proc.returncode == 0:
                    html_content = proc.stdout.decode('utf-8', errors='ignore')
                    self.preview_box.load_html(html_content)
                else:
                    err = proc.stderr.decode('utf-8', errors='ignore')
                    self.preview_box.load_html(f"<html><head><style>html,body{{background:#1e1e1e;color:#ff5555;margin:0;padding:12px;}}</style></head><body>Pandoc 渲染错误:<br><pre>{err}</pre></body></html>")
            except Exception as e:
                self.preview_box.load_html(f"<html><head><style>html,body{{background:#1e1e1e;color:#ff5555;margin:0;padding:12px;}}</style></head><body>执行异常: {e}</body></html>")
        else:
            rendered = None
            try:
                pandoc_exe = shutil.which("pandoc") or "pandoc"
                proc = subprocess.run(
                    [pandoc_exe, '-f', 'markdown', '-t', 'plain'],
                    input=content.encode('utf-8'),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    **_subprocess_run_kwargs()
                )
                if proc.returncode == 0:
                    rendered = proc.stdout.decode('utf-8', errors='ignore')
            except Exception:
                pass
            if not rendered:
                rendered = content
            self.preview_box.configure(state="normal")
            self.preview_box.delete("1.0", "end")
            self.preview_box.insert("1.0", rendered)
            self.preview_box.configure(state="disabled")

    def open_markdown_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Markdown 文件", "*.md"), ("所有文件", "*.*")])
        if filename:
            if not self._load_markdown_file(filename):
                messagebox.showerror("打开失败", "文件无法读取")

    def _refresh_template_dropdown(self):
        built_in = ["公文风", "互联网风", "学术风"]
        custom_names = list(self.custom_templates.keys())
        all_templates = built_in + custom_names
        self.sidebar_frame.update_template_list(all_templates)

    def upload_template(self):
        filename = filedialog.askopenfilename(filetypes=[("Word 文档", "*.docx")])
        if not filename:
            return

        dialog = ctk.CTkInputDialog(text="请输入模板名称:", title="自定义模板")
        name = dialog.get_input()
        
        if not name or not name.strip():
            return
            
        name = name.strip()
        if name in ["公文风", "互联网风", "学术风"]:
            messagebox.showerror("错误", "不能使用内置模板名称")
            return
            
        self.custom_templates[name] = filename
        set_key("custom_templates", self.custom_templates)
        
        self._refresh_template_dropdown()
        self.sidebar_frame.set_template_choice(name)
        messagebox.showinfo("成功", f"模板 '{name}' 已添加")

    def delete_template(self):
        current_choice = self.sidebar_frame.get_template_choice()
        
        if current_choice not in self.custom_templates:
            messagebox.showinfo("提示", "只能删除自定义模板，内置模板无法删除。")
            return

        if not messagebox.askyesno("确认删除", f"确定要删除自定义模板 '{current_choice}' 吗？"):
            return

        del self.custom_templates[current_choice]
        set_key("custom_templates", self.custom_templates)
        
        self._refresh_template_dropdown()
        self.sidebar_frame.set_template_choice("学术风")
        messagebox.showinfo("成功", f"模板 '{current_choice}' 已删除")

    def _load_markdown_file(self, filepath):
        try:
            filepath = filepath.replace("\x00", "").strip()
            suffix = os.path.splitext(filepath)[1].lower()
            if suffix not in (".md", ".markdown", ".mdown"):
                return False
            content = None
            for enc in ("utf-8", "utf-8-sig", "gbk", "cp936"):
                try:
                    with open(filepath, "r", encoding=enc) as f:
                        content = f.read()
                    break
                except Exception:
                    continue
            if content is None:
                return False
                
            self.textbox.delete("1.0", "end")
            self.textbox.insert("1.0", content)
            self.update_preview()
            self.status_label.configure(text=f"已加载文件: {os.path.basename(filepath)}", text_color="green")
            return True
        except Exception as e:
            self.status_label.configure(text=f"读取文件错误: {e}", text_color="red")
            return False

    def clear_editor(self):
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", self.default_text)
        self.last_clipboard = "" 
        self.update_preview()
        self.status_label.configure(text="已清空编辑区")
    
    def _on_close(self):
        self.destroy()

    def monitor_clipboard(self):
        if not self.monitor_clipboard_enabled:
            return

        try:
            content = pyperclip.paste()
            if not content:
                 self.after(2000, self.monitor_clipboard)
                 return

            if content != self.last_clipboard:
                if len(content) > 50000:
                    self.status_label.configure(text="剪贴板内容过大，已忽略自动粘贴", text_color="orange")
                    self.last_clipboard = content
                    self.after(2000, self.monitor_clipboard)
                    return

                content_s = content.strip()
                has_md_heading = bool(re.search(r'^#{1,6}\s+(?!coding|!/usr|import|def|class)', content_s, re.MULTILINE))
                has_md_list = bool(re.search(r'^(\s*[-*+]|\s*\d+\.)\s+', content_s, re.MULTILINE))
                has_md_quote = bool(re.search(r'^\s*>\s+', content_s, re.MULTILINE))
                has_md_code = bool(re.search(r'```', content_s))
                
                is_likely_md = has_md_heading or has_md_list or has_md_quote or has_md_code
                is_script = bool(re.search(r'^\s*(import |def |class |from |print\(|#!/)\b', content_s, re.MULTILINE))
                
                if is_likely_md and not is_script:
                    current_text = self.textbox.get("1.0", "end").strip()
                    is_empty = (not current_text)
                    is_default = (current_text == self.default_text.strip())
                    is_same_as_last = (current_text == self.last_clipboard.strip())
                    
                    if is_empty or is_default:
                        self.textbox.delete("1.0", "end")
                        self.textbox.insert("1.0", content)
                        self.update_preview()
                        self.status_label.configure(text="已自动捕获剪贴板内容", text_color="green")
                        self.last_clipboard = content
                    elif not is_same_as_last:
                         self.status_label.configure(text="检测到新复制的 Markdown，为防覆盖请手动粘贴", text_color="cyan")
                         self.last_clipboard = content
                    else:
                        self.last_clipboard = content
        except Exception:
            pass
        
        self.after(2000, self.monitor_clipboard) 
        
    def open_settings(self):
        SettingsDialog(self)

    def preview_in_browser(self):
        content = self.textbox.get("1.0", "end").strip()
        if not content or content == self.default_text.strip():
            messagebox.showerror("错误", "内容为空!")
            return

        try:
            output_html = os.path.join(tempfile.gettempdir(), "aidoc_preview.html")
            html_template = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Markdown Preview</title>
<style>
body { font-family: "Microsoft YaHei", sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; line-height: 1.6; color:#333; }
code { background-color: #f5f5f5; padding: 2px 4px; border-radius: 4px; font-family: Consolas, monospace;}
pre { background-color: #f5f5f5; padding: 16px; border-radius: 8px; overflow-x: auto; border-left: 4px solid #0066CC;}
img { max-width: 100%; }
blockquote { border-left: 4px solid #0066CC; margin: 0; padding-left: 16px; color: #666; background-color:#fafafa; padding:10px;}
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 8px; }
th { background-color: #f2f2f2; }
a { color: #0066CC; text-decoration: none; }
</style>
</head>
<body>
$body$
</body>
</html>
            """
            
            pandoc_exe = shutil.which("pandoc") or "pandoc"
            template_file = _resource_path("preview_render_template_local.html")
            cmd = [
                pandoc_exe,
                "-f",
                "markdown+tex_math_dollars+tex_math_single_backslash+tex_math_double_backslash+fenced_code_blocks+backtick_code_blocks",
                "-t",
                "html",
                "-s",
                "--mathjax",
                "--highlight-style=tango",
                f"--template={template_file}",
                "-o",
                output_html,
            ]
            
            process = subprocess.run(
                cmd, input=_normalize_preview_markdown(content).encode('utf-8'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, **_subprocess_run_kwargs()
            )
            
            if process.returncode == 0:
                import webbrowser
                webbrowser.open(f'file://{os.path.abspath(output_html)}')
                self.status_label.configure(text="已在浏览器中打开预览", text_color="green")
            else:
                err = process.stderr.decode('utf-8', errors='ignore')
                messagebox.showerror("预览失败", f"Pandoc 错误: {err}")
                
        except Exception as e:
            messagebox.showerror("预览错误", str(e))

    def generate_document(self):
        content = self.textbox.get("1.0", "end").strip()
        if not content or content == self.default_text.strip():
            messagebox.showerror("错误", "内容为空!")
            return

        # ==========================================
        # 极客风格：严格安全的符号预处理，保障跨引擎稳定性
        # ==========================================
        # 未完成：使用标准几何空心方块
        content = re.sub(r'(?m)^(\s*[-*])\s+\[ \]\s+', r'\1 □ ', content)
        # 已完成：使用标准几何实心方块 (代表已勾选)
        content = re.sub(r'(?m)^(\s*[-*])\s+\[[xX]\]\s+', r'\1 ■ ', content)
        # 降维彩色 Emoji 为黑白文本以防止 Word 弹窗
        content = content.replace('⚠️', '⚠') 
        
        template_choice = self.template_option_menu.get()
        if template_choice in self.custom_templates:
            template_path = self.custom_templates[template_choice]
        else:
            mapping = { "公文风": "official", "互联网风": "internet", "学术风": "academic" }
            key = mapping.get(template_choice, "academic")
            template_path = _resource_path("templates", f"{key}.docx")

        if template_path and not os.path.exists(template_path):
             template_path = os.path.abspath(template_path)
             if not os.path.exists(template_path):
                 self.status_label.configure(text=f"未找到模板: {template_path}", text_color="red")
                 return

        title_line = "output_doc"
        for line in content.splitlines():
            if line.startswith("# "):
                title_line = line[2:].strip()
                break
        
        safe_title = "".join([c for c in title_line if c.isalnum() or c in (' ', '-', '_') or '\u4e00' <= c <= '\u9fff']).strip()
        output_docx = f"{safe_title}.docx"
        
        if os.path.exists(output_docx):
            try:
                os.rename(output_docx, output_docx)
            except OSError:
                import time
                timestamp = int(time.time())
                output_docx = f"{safe_title}_{timestamp}.docx"
                self.status_label.configure(text=f"文件被占用，已重命名为: {output_docx}", text_color="orange")

        self.status_label.configure(text="正在转换...", text_color="yellow")
        self.update()
        self.generate_btn.configure(state="disabled", text="生成中...")
        
        threading.Thread(target=self._run_conversion, args=(content, output_docx, template_path, safe_title), daemon=True).start()

    def _run_conversion(self, content, output_docx, template_path, safe_title):
        try:
            success, msg = convert_markdown(content, output_docx, reference_doc=template_path)
            self.after(0, lambda: self._conversion_finished(success, msg, output_docx, content, safe_title))
        except Exception as e:
             self.after(0, lambda: self.status_label.configure(text=f"错误: {str(e)}", text_color="red"))
             self.after(0, lambda: self.generate_btn.configure(state="normal", text="生成并打开 Word"))
             logger.error(e)

    def _conversion_finished(self, success, msg, output_docx, content, safe_title):
        self.generate_btn.configure(state="normal", text="生成并打开 Word")
        
        if success:
            self.status_label.configure(text=f"成功! 已保存至 {output_docx}", text_color="green")
            if platform.system() == 'Windows':
                os.startfile(output_docx)
            elif platform.system() == 'Darwin':
                subprocess.call(('open', output_docx))
            else:
                subprocess.call(('xdg-open', output_docx))
        else:
            self.status_label.configure(text=f"转换失败: {msg}", text_color="red")
            messagebox.showerror("转换错误", msg)

        if self.pdf_checkbox.get():
             output_pdf = output_docx.replace(".docx", ".pdf")
             if os.path.exists(output_pdf):
                try:
                    os.rename(output_pdf, output_pdf)
                except OSError:
                    import time
                    timestamp = int(time.time())
                    output_pdf = f"{safe_title}_{timestamp}.pdf"
             
             self.status_label.configure(text="正在原生引擎导出 PDF...", text_color="yellow")
             # 重新将 content 传入，交由原生引擎独立渲染
             threading.Thread(target=self._run_pdf_conversion, args=(content, output_pdf, output_docx), daemon=True).start()

    def _run_pdf_conversion(self, content, output_pdf, output_docx):
        try:
             # 采用方案 A 原生转换路线，完全隔离环境影响
             success, msg = convert_markdown(content, output_pdf, reference_doc=None, output_format='pdf')
             self.after(0, lambda: self._pdf_finished(success, msg, output_pdf, output_docx, content))
        except Exception as e:
             logger.error(f"PDF 错误: {e}")
             self.after(0, lambda: self.status_label.configure(text=f"PDF 错误: {str(e)}", text_color="red"))

    def _pdf_finished(self, success, msg, output_pdf, output_docx, content):
         if success:
              self.status_label.configure(text=f"双轨渲染完毕! 已保存至 {output_docx} 和 {output_pdf}", text_color="green")
         else:
              self.status_label.configure(text=f"Word 成功, 但 PDF 原生渲染失败: {msg}", text_color="orange")
              # 方案A 的核心：如果 Typst 丢失，通过弹窗引导用户配置环境，而不是依赖本地 Office
              if "typst" in msg.lower():
                  if messagebox.askyesno("Typst 未找到", "PDF 转换失败，未找到 Typst。\\n是否手动指定 typst.exe 的路径？"):
                      typst_path = filedialog.askopenfilename(title="选择 typst.exe", filetypes=[("Executable", "*.exe")])
                      if typst_path:
                          os.environ["TYPST_EXE"] = typst_path
                          try:
                              set_key("typst_exe", typst_path)
                          except Exception:
                              pass
                          self.status_label.configure(text="正在重试 PDF...", text_color="yellow")
                          threading.Thread(target=self._retry_pdf, args=(content, output_pdf), daemon=True).start()

    def _retry_pdf(self, content, output_pdf):
        success_retry, msg_retry = convert_markdown(content, output_pdf, reference_doc=None, output_format='pdf')
        if success_retry:
            self.after(0, lambda: self.status_label.configure(text=f"重试成功! 已保存 PDF", text_color="green"))
        else:
            self.after(0, lambda: messagebox.showerror("重试失败", msg_retry))

if __name__ == "__main__":
    app = App()
    app.mainloop()
