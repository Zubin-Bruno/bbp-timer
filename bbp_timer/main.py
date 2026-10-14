import ctypes

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # texto nítido en pantallas con escalado
except Exception:
    pass

from app import App

if __name__ == "__main__":
    App().run()
