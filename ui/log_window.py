import customtkinter as ctk
from core.logger import get_logs

class LogWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("运行日志")
        self.geometry("700x500")
        
        # Make sure it stays on top of parent
        self.attributes("-topmost", True) # Use topmost instead of transient to avoid titlebar style issues
        self.lift()
        
        # Apply dark mode fix explicitly if needed (though CTkToplevel usually inherits)
        # Windows 11 titlebar color sometimes needs explicit DWM API calls, but CTK usually handles it.
        # Transient windows sometimes inherit "toolwindow" style which might be light.
        
        # Center relative to parent
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        try:
            x = parent.winfo_x() + (parent.winfo_width() // 2) - (width // 2)
            y = parent.winfo_y() + (parent.winfo_height() // 2) - (height // 2)
            self.geometry(f"+{x}+{y}")
        except:
            pass
        
        # Textbox
        self.textbox = ctk.CTkTextbox(self, font=("Consolas", 12))
        self.textbox.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Close button
        self.btn_close = ctk.CTkButton(self, text="关闭", command=self.destroy)
        self.btn_close.pack(pady=(0, 10))
        
        # Initial load
        self.refresh_logs()
        
        # Auto refresh
        self.after(1000, self.auto_refresh)

    def refresh_logs(self):
        logs = get_logs()
        # Only update if changed (simple check by length might be enough for appending)
        current_text = self.textbox.get("0.0", "end")
        if len(logs) != len(current_text) - 1: # -1 for newline
            self.textbox.configure(state="normal")
            self.textbox.delete("0.0", "end")
            self.textbox.insert("0.0", logs)
            self.textbox.see("end")
            self.textbox.configure(state="disabled")
        
    def auto_refresh(self):
        if self.winfo_exists():
            self.refresh_logs()
            self.after(2000, self.auto_refresh)
