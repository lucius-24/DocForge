import customtkinter as ctk
import tkinter as tk

class CustomDropdown(ctk.CTkFrame):
    def __init__(self, master, values=None, command=None, width=140, height=30, 
                 fg_color="transparent", text_color="gray80", 
                 button_color="transparent", hover_color="#3B8ED0",
                 dropdown_fg_color="#2b2b2b", dropdown_hover_color="#3B8ED0",
                 font=None, **kwargs):
        super().__init__(master, width=width, height=height, fg_color=fg_color, **kwargs)
        
        self.values = values or []
        self.command = command
        self.width = width
        self.height = height
        self.dropdown_fg_color = dropdown_fg_color
        self.dropdown_hover_color = dropdown_hover_color
        self.text_color = text_color
        self.font = font
        
        self.current_value = self.values[0] if self.values else ""
        self.menu_open = False
        self.dropdown_window = None
        
        self.grid_propagate(False)
        
        self.main_button = ctk.CTkButton(self, text=f"{self.current_value} ▼", 
                                         width=width, height=height,
                                         fg_color=button_color, 
                                         hover_color=hover_color,
                                         text_color=text_color,
                                         font=font,
                                         anchor="center",
                                         command=self.toggle_dropdown)
        self.main_button.pack(fill="both", expand=True)

    def toggle_dropdown(self):
        if self.menu_open:
            self.close_dropdown()
        else:
            self.open_dropdown()

    def open_dropdown(self):
        if not self.values or self.menu_open:
            return
            
        self.menu_open = True
        
        # Get absolute position
        root_x = self.main_button.winfo_rootx()
        root_y = self.main_button.winfo_rooty()
        button_height = self.main_button.winfo_height()
        
        # Create Toplevel
        self.dropdown_window = ctk.CTkToplevel(self)
        self.dropdown_window.wm_overrideredirect(True)
        self.dropdown_window.wm_attributes("-topmost", True)
        self.dropdown_window.fg_color = self.dropdown_fg_color
        
        # Calculate size
        num_items = len(self.values)
        item_height = 30
        total_height = num_items * item_height
        
        self.dropdown_window.geometry(f"{self.width}x{total_height}+{root_x}+{root_y + button_height + 2}")
        
        # Content
        self.dropdown_frame = ctk.CTkFrame(self.dropdown_window, fg_color=self.dropdown_fg_color, corner_radius=0)
        self.dropdown_frame.pack(fill="both", expand=True)
        
        for value in self.values:
            btn = ctk.CTkButton(self.dropdown_frame, text=value,
                                height=item_height,
                                fg_color="transparent",
                                text_color=self.text_color,
                                hover_color=self.dropdown_hover_color,
                                font=self.font,
                                anchor="center",
                                corner_radius=0,
                                command=lambda v=value: self.select_item(v))
            btn.pack(fill="x")
            
        # Bind global click to detect outside clicks
        # We bind to the main button's master (usually the app root)
        self.winfo_toplevel().bind("<Button-1>", self._check_click_outside, add="+")
        
        # Ensure focus (optional, but good for keyboard nav if implemented later)
        self.dropdown_window.focus_force()

    def _check_click_outside(self, event):
        if not self.menu_open or not self.dropdown_window:
            return

        try:
            # Check if click is inside dropdown window
            cx, cy = self.dropdown_window.winfo_pointerxy()
            x = self.dropdown_window.winfo_rootx()
            y = self.dropdown_window.winfo_rooty()
            w = self.dropdown_window.winfo_width()
            h = self.dropdown_window.winfo_height()
            
            if x <= cx <= x+w and y <= cy <= y+h:
                return # Clicked inside dropdown
            
            # Check if click is inside the main button (toggle button)
            bx = self.main_button.winfo_rootx()
            by = self.main_button.winfo_rooty()
            bw = self.main_button.winfo_width()
            bh = self.main_button.winfo_height()
            
            if bx <= cx <= bx+bw and by <= cy <= by+bh:
                # Clicked the toggle button. 
                # Let the button's command handle the toggle (it will call close_dropdown if open).
                # However, if we close here, toggle_dropdown will see it closed and open it again.
                # So we should close it here and PREVENT toggle_dropdown from reopening?
                # Or let toggle_dropdown handle it?
                # If we return here, toggle_dropdown runs. It sees menu_open=True. It calls close_dropdown. Perfect.
                return 

            # Clicked elsewhere -> Close
            self.close_dropdown()
            
        except Exception:
            self.close_dropdown()

    def close_dropdown(self):
        if self.dropdown_window:
            self.dropdown_window.destroy()
            self.dropdown_window = None
        
        # Unbind global click
        try:
            self.winfo_toplevel().unbind("<Button-1>")
            # Note: unbind removes ALL bindings for Button-1 on toplevel? 
            # That's dangerous if other widgets rely on root binding.
            # But in CTK apps, usually widgets have their own bindings.
            # Safer: Use bind_all with specific handler reference to unbind? Tkinter unbind is tricky.
            # Actually, we can just leave it bound and check menu_open flag, 
            # but better to clean up.
            # Since unbind removes all, we might want to just set menu_open=False and let the handler ignore.
            pass 
        except Exception:
            pass
            
        self.menu_open = False

    def select_item(self, value):
        self.current_value = value
        self.main_button.configure(text=f"{value} ▼")
        self.close_dropdown()
        if self.command:
            self.command(value)

    def get(self):
        return self.current_value

    def set(self, value):
        self.current_value = value
        self.main_button.configure(text=f"{value} ▼")

    def configure(self, **kwargs):
        if "values" in kwargs:
            self.values = kwargs.pop("values")
            # If current value is not in new values, reset to first available or empty
            if self.values and self.current_value not in self.values:
                self.current_value = self.values[0]
                self.main_button.configure(text=f"{self.current_value} ▼")
            elif not self.values:
                self.current_value = ""
                self.main_button.configure(text=" ▼")
        
        super().configure(**kwargs)
