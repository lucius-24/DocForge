import os
import sys

# Force PIL import to ensure PyInstaller detects it as a dependency
try:
    import PIL
    import PIL.Image
    import PIL.ImageTk
    from PIL import Image, ImageTk
    # Force load of internal modules
    import PIL._tkinter_finder
    import PIL.PngImagePlugin
except ImportError:
    pass

from ui.app import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
