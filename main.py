"""
CloudStream Desktop — entry point.
Run with: python main.py
"""
import sys
import os

# Add project root to path so all modules resolve correctly
_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

# libmpv-2.dll lives next to main.py on Windows
os.environ["PATH"] = _ROOT + os.pathsep + os.environ.get("PATH", "")

import customtkinter as ctk
from data.preferences import Preferences
from core.i18n import set_language


def main():
    # Dil ve tema tercihlerini yükle
    lang = Preferences.get_str("language", "tr")
    set_language(lang)

    theme = Preferences.get_str("theme", "dark")
    ctk.set_appearance_mode(theme)
    ctk.set_default_color_theme("blue")

    from ui.app import CloudStreamApp
    app = CloudStreamApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
