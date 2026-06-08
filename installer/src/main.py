# -*- coding: utf-8 -*-
from pathlib import Path
import customtkinter as ctk

from ui_components import (
    WelcomeFrame,
    InstallOptionsFrame,
    ProgressFrame,
    SuccessFrame,
    ErrorFrame,
)
from utils import resource_path


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

WINDOW_WIDTH = 560
WINDOW_HEIGHT = 620


class InstallerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ADOS Tools — Instalador")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.resizable(False, False)

        # Icono de la ventana
        icon = resource_path("assets/icon.ico")
        if icon.exists():
            self.iconbitmap(str(icon))

        self._current_frame = None
        self._show_welcome()

    def _clear(self):
        if self._current_frame:
            self._current_frame.destroy()

    def _show_welcome(self):
        self._clear()
        self._current_frame = WelcomeFrame(
            self,
            on_continue=self._show_options,
            fg_color="transparent",
        )
        self._current_frame.pack(fill="both", expand=True)

    def _show_options(self):
        self._clear()
        self._current_frame = InstallOptionsFrame(
            self,
            on_install=self._show_progress,
            fg_color="transparent",
        )
        self._current_frame.pack(fill="both", expand=True)

    def _show_progress(self, mode: str, local_path: str | None, dest_dir: Path):
        self._clear()
        self._current_frame = ProgressFrame(
            self,
            mode=mode,
            local_path=local_path,
            dest_dir=dest_dir,
            on_success=self._show_success,
            on_error=self._show_error,
            fg_color="transparent",
        )
        self._current_frame.pack(fill="both", expand=True)

    def _show_success(self):
        self._clear()
        self._current_frame = SuccessFrame(
            self,
            on_close=self.destroy,
            fg_color="transparent",
        )
        self._current_frame.pack(fill="both", expand=True)

    def _show_error(self, error_msg: str):
        self._clear()
        self._current_frame = ErrorFrame(
            self,
            error_msg=error_msg,
            on_retry=self._show_options,
            on_close=self.destroy,
            fg_color="transparent",
        )
        self._current_frame.pack(fill="both", expand=True)


def main():
    app = InstallerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
