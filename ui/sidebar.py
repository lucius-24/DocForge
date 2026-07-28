import customtkinter as ctk
import os
from PIL import Image
from ui.custom_dropdown import CustomDropdown

class Sidebar(ctk.CTkFrame):
    def __init__(self, master, font_family, callbacks):
        super().__init__(master, width=220, corner_radius=0)
        self.callbacks = callbacks
        self.font_family = font_family
        
        # Load Icons
        self.icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons")
        self.icons = {}
        try:
            # Use White icons for Dark Sidebar
            self.icons['upload'] = ctk.CTkImage(light_image=Image.open(os.path.join(self.icon_path, "upload_white.png")), size=(18, 18))
            self.icons['folder'] = ctk.CTkImage(light_image=Image.open(os.path.join(self.icon_path, "folder_white.png")), size=(18, 18))
            self.icons['preview'] = ctk.CTkImage(light_image=Image.open(os.path.join(self.icon_path, "preview_cyan.png")), size=(18, 18))
            self.icons['settings'] = ctk.CTkImage(light_image=Image.open(os.path.join(self.icon_path, "settings_gray.png")), size=(18, 18))
            self.icons['delete'] = ctk.CTkImage(light_image=Image.open(os.path.join(self.icon_path, "clear_white.png")), size=(16, 16))
        except Exception as e:
            print(f"Warning: Failed to load icons: {e}")

        self.grid_rowconfigure(8, weight=1) # Spacer row

        # Logo
        self.logo_label = ctk.CTkLabel(self, text="DocForge", font=ctk.CTkFont(family=self.font_family, size=22, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(40, 30))

        # Template Section
        self.template_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.template_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        
        self.template_label = ctk.CTkLabel(self.template_frame, text="样式模板", anchor="w", font=ctk.CTkFont(family=self.font_family, size=13, weight="bold"), text_color="gray70")
        self.template_label.pack(fill="x", padx=15, pady=(5, 2))

        # Dropdown and Delete Button Container
        self.dropdown_container = ctk.CTkFrame(self.template_frame, fg_color="transparent")
        self.dropdown_container.pack(fill="x", padx=10, pady=5)

        self.template_option_menu = CustomDropdown(self.dropdown_container, values=["公文风", "互联网风", "学术风", "自定义"],
                                                    command=callbacks['change_template'], 
                                                    height=35,
                                                    font=ctk.CTkFont(family=self.font_family, size=13, weight="bold"),
                                                    button_color="#2b2b2b",
                                                    hover_color="#333333",
                                                    dropdown_fg_color="#202020",
                                                    dropdown_hover_color="#3B8ED0",
                                                    text_color="#DCE4EE")
        self.template_option_menu.pack(side="left", fill="x", expand=True)
        
        self.delete_template_btn = ctk.CTkButton(self.dropdown_container, text="", 
                                                 image=self.icons.get('delete'),
                                                 command=callbacks.get('delete_template', None),
                                                 width=35, height=35,
                                                 fg_color="#2b2b2b", border_width=0, 
                                                 hover_color="#C62828")
        self.delete_template_btn.pack(side="right", padx=(5, 0))
        
        self.upload_template_btn = ctk.CTkButton(self.template_frame, text="上传自定义模板", 
                                                 image=self.icons.get('upload'),
                                                 command=callbacks['upload_template'], 
                                                 height=35,
                                                 font=ctk.CTkFont(family=self.font_family, size=12, weight="bold"), 
                                                 fg_color="#2b2b2b", border_width=0, 
                                                 hover_color="#333333",
                                                 text_color="#DCE4EE")
        self.upload_template_btn.pack(fill="x", padx=10, pady=(2, 10))

        # File Section
        self.file_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.file_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        self.file_label = ctk.CTkLabel(self.file_frame, text="文件操作", anchor="w", font=ctk.CTkFont(family=self.font_family, size=13, weight="bold"), text_color="gray70")
        self.file_label.pack(fill="x", padx=15, pady=(5, 2))

        self.open_md_btn = ctk.CTkButton(self.file_frame, text="打开 .md 文件", 
                                         image=self.icons.get('folder'),
                                         command=callbacks['open_file'], 
                                         height=35,
                                         font=ctk.CTkFont(family=self.font_family, size=12, weight="bold"))
        self.open_md_btn.pack(fill="x", padx=10, pady=5)

        self.preview_browser_btn = ctk.CTkButton(self.file_frame, text="浏览器预览", 
                                                 image=self.icons.get('preview'),
                                                 command=callbacks['preview_browser'], 
                                                 height=35,
                                                 font=ctk.CTkFont(family=self.font_family, size=12, weight="bold"), 
                                                 fg_color="#2b2b2b", border_width=0, 
                                                 hover_color="#333333",
                                                 text_color="#3B8ED0")
        self.preview_browser_btn.pack(fill="x", padx=10, pady=(2, 10))

        # Settings (Bottom)
        self.btn_settings = ctk.CTkButton(self, text="设置", 
                                          image=self.icons.get('settings'),
                                          command=callbacks['open_settings'], 
                                          height=35,
                                          font=ctk.CTkFont(family=self.font_family, size=12, weight="bold"), 
                                          fg_color="transparent", border_width=0, 
                                          text_color="gray60", hover_color="#2b2b2b")
        self.btn_settings.grid(row=9, column=0, padx=20, pady=(10, 20), sticky="s")

    def get_template_choice(self):
        return self.template_option_menu.get()
    
    def set_template_choice(self, value):
        self.template_option_menu.set(value)

    def update_template_list(self, values):
        self.template_option_menu.configure(values=values)
