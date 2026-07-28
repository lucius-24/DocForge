import customtkinter as ctk
from tkinter import filedialog
import os
from core.config import get_config, set_key

from ui.log_window import LogWindow

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("设置")
        self.geometry("500x400")
        self.resizable(False, False)
        
        # Center the window relative to parent
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        
        # Calculate center relative to parent window
        try:
            parent_x = parent.winfo_x()
            parent_y = parent.winfo_y()
            parent_width = parent.winfo_width()
            parent_height = parent.winfo_height()
            
            x = parent_x + (parent_width // 2) - (width // 2)
            y = parent_y + (parent_height // 2) - (height // 2)
        except Exception:
            # Fallback to screen center
            x = (self.winfo_screenwidth() // 2) - (width // 2)
            y = (self.winfo_screenheight() // 2) - (height // 2)
            
        self.geometry(f"+{x}+{y}")
        
        self.parent = parent
        self.config = get_config()
        self.font_family = parent.font_family
        
        # Main Frame for content
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=0, pady=0)
        
        self.main_frame.grid_columnconfigure(1, weight=1)
        
        # --- Typst Path ---
        self.lbl_typst = ctk.CTkLabel(self.main_frame, text="Typst 路径:", font=ctk.CTkFont(family=self.font_family, size=13))
        self.lbl_typst.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")
        
        self.entry_typst = ctk.CTkEntry(self.main_frame, placeholder_text="自动检测中...")
        self.entry_typst.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")
        if "typst_exe" in self.config:
            self.entry_typst.insert(0, self.config["typst_exe"])
            
        self.btn_browse_typst = ctk.CTkButton(self.main_frame, text="浏览...", width=80, command=self.browse_typst, font=ctk.CTkFont(family=self.font_family, size=12))
        self.btn_browse_typst.grid(row=1, column=2, padx=(0, 20), pady=(0, 10))
        
        # --- Clipboard Monitor ---
        self.lbl_clipboard = ctk.CTkLabel(self.main_frame, text="功能开关:", font=ctk.CTkFont(family=self.font_family, size=13))
        self.lbl_clipboard.grid(row=2, column=0, padx=20, pady=(10, 5), sticky="w")
        
        self.switch_clipboard = ctk.CTkSwitch(self.main_frame, text="监听剪贴板 (自动粘贴 Markdown)", font=ctk.CTkFont(family=self.font_family, size=13))
        self.switch_clipboard.grid(row=3, column=0, columnspan=3, padx=20, pady=10, sticky="w")
        
        # Load switch state (default True if not set)
        if self.config.get("monitor_clipboard", True):
            self.switch_clipboard.select()
        else:
            self.switch_clipboard.deselect()

        # --- Logs ---
        self.lbl_logs = ctk.CTkLabel(self.main_frame, text="诊断:", font=ctk.CTkFont(family=self.font_family, size=13))
        self.lbl_logs.grid(row=4, column=0, padx=20, pady=(10, 5), sticky="w")
        
        self.btn_logs = ctk.CTkButton(self.main_frame, text="查看运行日志", command=self.open_logs, font=ctk.CTkFont(family=self.font_family, size=13))
        self.btn_logs.grid(row=5, column=0, padx=20, pady=(0, 10), sticky="w")

        # --- Save Button ---
        self.btn_save = ctk.CTkButton(self.main_frame, text="保存设置", command=self.save_settings, 
                                      fg_color="#3B8ED0", hover_color="#36719F", text_color="#DCE4EE",
                                      font=ctk.CTkFont(family=self.font_family, size=13, weight="bold"))
        self.btn_save.grid(row=6, column=0, columnspan=3, padx=20, pady=30, sticky="ew")
        
        # Focus
        self.grab_set()
        
    def open_logs(self):
        log_win = LogWindow(self)
        log_win.lift() # Ensure it's above settings
        log_win.focus_force()
        log_win.grab_set() # Modal behavior for logs too? Optional, but keeps it on top.
            
    def browse_typst(self):
        filename = filedialog.askopenfilename(title="选择 typst.exe", filetypes=[("Executable", "*.exe")])
        if filename:
            self.entry_typst.delete(0, "end")
            self.entry_typst.insert(0, filename)
            
    def save_settings(self):
        # Save Typst
        typst_path = self.entry_typst.get().strip()
        if typst_path:
            set_key("typst_exe", typst_path)
            os.environ["TYPST_EXE"] = typst_path
        
        # Save Clipboard
        monitor = bool(self.switch_clipboard.get())
        set_key("monitor_clipboard", monitor)
        
        # Update parent app state immediately
        if hasattr(self.parent, "monitor_clipboard_enabled"):
            self.parent.monitor_clipboard_enabled = monitor
            if monitor:
                self.parent.monitor_clipboard() # Restart if needed
        
        self.destroy()
