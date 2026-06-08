# -*- coding: utf-8 -*-
import threading
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk

import pyrevit_detector
import installer_core
import downloader as dl
from utils import resource_path


# ─────────────────────────────────────────────────────────────────────────────
# Pantalla 1: Bienvenida
# ─────────────────────────────────────────────────────────────────────────────
class WelcomeFrame(ctk.CTkFrame):
    def __init__(self, master, on_continue, **kwargs):
        super().__init__(master, **kwargs)
        self._on_continue = on_continue
        self._build()
        self._detect_pyrevit()

    def _build(self):
        ctk.CTkLabel(
            self,
            text="ADOS Extension para Revit",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(30, 4))

        ctk.CTkLabel(
            self,
            text="Herramientas de automatizacion estructural",
            font=ctk.CTkFont(size=13),
            text_color="gray70",
        ).pack(pady=(0, 20))

        # Modulos incluidos
        modules_frame = ctk.CTkFrame(self, corner_radius=10)
        modules_frame.pack(fill="x", padx=40, pady=(0, 20))

        ctk.CTkLabel(
            modules_frame,
            text="Modulos incluidos:",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=16, pady=(12, 4))

        modules = [
            ("⚙  Aceros", "9 botones — Cimientos, Columnas, Vigas, Zapatas, Estribos"),
            ("📄  Documentacion", "4 botones — Acotado, Generacion de planos, Secciones"),
            ("🔧  General", "1 boton — Eliminar habitacion"),
            ("🏠  Modelado", "6 botones — Acabados de muros y suelos"),
        ]
        for title, desc in modules:
            row = ctk.CTkFrame(modules_frame, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(row, text=title, font=ctk.CTkFont(weight="bold"), width=160, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=desc, text_color="gray70", anchor="w").pack(side="left")

        ctk.CTkLabel(modules_frame, text="").pack(pady=4)

        # Estado de pyRevit
        self._status_frame = ctk.CTkFrame(self, corner_radius=10)
        self._status_frame.pack(fill="x", padx=40, pady=(0, 20))

        self._status_label = ctk.CTkLabel(
            self._status_frame,
            text="Verificando pyRevit...",
            font=ctk.CTkFont(size=13),
        )
        self._status_label.pack(pady=12, padx=16)

        self._pyrevit_link_btn = ctk.CTkButton(
            self._status_frame,
            text="Descargar pyRevit",
            command=self._open_pyrevit_download,
            width=160,
            fg_color="#E07B39",
            hover_color="#C06020",
        )

        # Boton continuar
        self._continue_btn = ctk.CTkButton(
            self,
            text="Continuar  →",
            command=self._on_continue,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._continue_btn.pack(pady=(0, 30))

    def _detect_pyrevit(self):
        def run():
            result = pyrevit_detector.find_pyrevit()
            self.after(0, lambda: self._update_status(result))

        threading.Thread(target=run, daemon=True).start()

    def _update_status(self, result):
        if result:
            version = result.get("version", "detectado")
            self._status_label.configure(
                text=f"✔  pyRevit detectado: {version}",
                text_color="#4CAF50",
            )
            self._pyrevit_link_btn.pack_forget()
        else:
            self._status_label.configure(
                text="⚠  pyRevit no encontrado en este equipo.\n"
                     "Puedes instalarlo ahora y luego continuar.",
                text_color="#E07B39",
            )
            self._pyrevit_link_btn.pack(pady=(0, 12))

    def _open_pyrevit_download(self):
        import webbrowser
        webbrowser.open("https://github.com/pyrevitlabs/pyRevit/releases/latest")


# ─────────────────────────────────────────────────────────────────────────────
# Pantalla 2: Opciones de instalacion
# ─────────────────────────────────────────────────────────────────────────────
class InstallOptionsFrame(ctk.CTkFrame):
    def __init__(self, master, on_install, **kwargs):
        super().__init__(master, **kwargs)
        self._on_install = on_install
        self._mode = tk.StringVar(value="bundled")
        self._local_path = tk.StringVar(value="")
        self._dest_dir = pyrevit_detector.get_default_extensions_dir()
        self._build()
        self._check_existing()

    def _build(self):
        ctk.CTkLabel(
            self,
            text="Opciones de instalacion",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(30, 20))

        # Tarjeta 0: Version incluida (bundled)
        card_0 = ctk.CTkFrame(self, corner_radius=10)
        card_0.pack(fill="x", padx=40, pady=(0, 10))

        ctk.CTkRadioButton(
            card_0,
            text="Instalar version incluida  (recomendado)",
            variable=self._mode,
            value="bundled",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_mode_change,
        ).pack(anchor="w", padx=16, pady=(14, 2))

        ctk.CTkLabel(
            card_0,
            text="Usa el archivo incluido en este instalador. No requiere internet.",
            text_color="gray70",
        ).pack(anchor="w", padx=36, pady=(0, 14))

        # Tarjeta A: Internet
        card_a = ctk.CTkFrame(self, corner_radius=10)
        card_a.pack(fill="x", padx=40, pady=(0, 10))

        ctk.CTkRadioButton(
            card_a,
            text="Instalar desde Internet",
            variable=self._mode,
            value="internet",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_mode_change,
        ).pack(anchor="w", padx=16, pady=(14, 2))

        ctk.CTkLabel(
            card_a,
            text="Descarga la ultima version automaticamente desde GitHub.",
            text_color="gray70",
        ).pack(anchor="w", padx=36, pady=(0, 14))

        # Tarjeta B: Archivo local
        card_b = ctk.CTkFrame(self, corner_radius=10)
        card_b.pack(fill="x", padx=40, pady=(0, 10))

        ctk.CTkRadioButton(
            card_b,
            text="Instalar desde Archivo Local",
            variable=self._mode,
            value="local",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_mode_change,
        ).pack(anchor="w", padx=16, pady=(14, 2))

        ctk.CTkLabel(
            card_b,
            text="Usa un archivo ZIP descargado manualmente o desde USB.",
            text_color="gray70",
        ).pack(anchor="w", padx=36, pady=(0, 8))

        local_row = ctk.CTkFrame(card_b, fg_color="transparent")
        local_row.pack(fill="x", padx=36, pady=(0, 14))

        self._local_entry = ctk.CTkEntry(
            local_row,
            textvariable=self._local_path,
            placeholder_text="Ruta al archivo ZIP...",
            state="disabled",
        )
        self._local_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self._browse_btn = ctk.CTkButton(
            local_row,
            text="Examinar...",
            width=100,
            command=self._browse_zip,
            state="disabled",
        )
        self._browse_btn.pack(side="left")

        # Directorio destino
        dest_frame = ctk.CTkFrame(self, corner_radius=10)
        dest_frame.pack(fill="x", padx=40, pady=(0, 10))

        ctk.CTkLabel(
            dest_frame,
            text="Directorio de instalacion:",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=16, pady=(12, 4))

        dest_row = ctk.CTkFrame(dest_frame, fg_color="transparent")
        dest_row.pack(fill="x", padx=16, pady=(0, 12))

        self._dest_entry = ctk.CTkEntry(dest_row, width=380)
        self._dest_entry.insert(0, str(self._dest_dir))
        self._dest_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            dest_row,
            text="Cambiar...",
            width=100,
            command=self._browse_dest,
        ).pack(side="left")

        # Advertencia si ya instalado
        self._warn_label = ctk.CTkLabel(
            self,
            text="",
            text_color="#E07B39",
            font=ctk.CTkFont(size=12),
        )
        self._warn_label.pack(pady=(0, 6))

        # Boton instalar
        self._install_btn = ctk.CTkButton(
            self,
            text="Instalar",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start,
        )
        self._install_btn.pack(pady=(0, 30))

    def _on_mode_change(self):
        mode = self._mode.get()
        state = "normal" if mode == "local" else "disabled"
        self._local_entry.configure(state=state)
        self._browse_btn.configure(state=state)

    def _browse_zip(self):
        path = filedialog.askopenfilename(
            title="Seleccionar archivo ZIP",
            filetypes=[("Archivos ZIP", "*.zip")],
        )
        if path:
            self._local_path.set(path)

    def _browse_dest(self):
        path = filedialog.askdirectory(title="Seleccionar directorio de instalacion")
        if path:
            self._dest_entry.delete(0, "end")
            self._dest_entry.insert(0, path)
            self._check_existing()

    def _check_existing(self):
        from pathlib import Path
        dest = Path(self._dest_entry.get()) if hasattr(self, "_dest_entry") else self._dest_dir
        if pyrevit_detector.is_ados_installed(dest):
            self._warn_label.configure(
                text="⚠  ADOS.extension ya esta instalada. Se sobreescribira al instalar."
            )
        else:
            self._warn_label.configure(text="")

    def _start(self):
        from pathlib import Path
        mode = self._mode.get()
        dest = Path(self._dest_entry.get())

        if mode == "local" and not self._local_path.get():
            self._warn_label.configure(
                text="⚠  Por favor selecciona un archivo ZIP.", text_color="#E07B39"
            )
            return

        local = self._local_path.get() if mode == "local" else None
        self._on_install(mode=mode, local_path=local, dest_dir=dest)


# ─────────────────────────────────────────────────────────────────────────────
# Pantalla 3: Progreso
# ─────────────────────────────────────────────────────────────────────────────
class ProgressFrame(ctk.CTkFrame):
    def __init__(self, master, mode, local_path, dest_dir, on_success, on_error, **kwargs):
        super().__init__(master, **kwargs)
        self._mode = mode
        self._local_path = local_path
        self._dest_dir = dest_dir
        self._on_success = on_success
        self._on_error = on_error
        self._cancel_event = threading.Event()
        self._build()
        self._start_installation()

    def _build(self):
        ctk.CTkLabel(
            self,
            text="Instalando ADOS Extension...",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(40, 20))

        self._progress_bar = ctk.CTkProgressBar(self, width=400)
        self._progress_bar.set(0)
        self._progress_bar.pack(pady=(0, 10))

        self._status_label = ctk.CTkLabel(
            self,
            text="Iniciando...",
            text_color="gray70",
            font=ctk.CTkFont(size=12),
        )
        self._status_label.pack(pady=(0, 30))

        self._cancel_btn = ctk.CTkButton(
            self,
            text="Cancelar",
            width=120,
            fg_color="gray40",
            hover_color="gray30",
            command=self._cancel,
        )
        self._cancel_btn.pack()

    def _update_ui(self, pct: int, msg: str):
        self._progress_bar.set(pct / 100)
        self._status_label.configure(text=msg)

    def _cancel(self):
        self._cancel_event.set()
        self._cancel_btn.configure(state="disabled", text="Cancelando...")

    def _start_installation(self):
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def _run(self):
        def cb(pct, msg):
            self.after(0, lambda: self._update_ui(pct, msg))

        try:
            if self._mode == "bundled":
                bundled_zip = resource_path("assets/ADOS.extension.zip")
                self.after(0, lambda: self._update_ui(5, "Cargando extension incluida..."))
                installer_core.install_from_zip(
                    bundled_zip, self._dest_dir,
                    progress_cb=cb, cancel_event=self._cancel_event
                )
            elif self._mode == "internet":
                self.after(0, lambda: self._update_ui(0, "Conectando con GitHub..."))
                zip_bytes = dl.download_with_progress(
                    dl.GITHUB_ZIP_URL, progress_cb=cb, cancel_event=self._cancel_event
                )
                self.after(0, lambda: self._update_ui(50, "Descarga completa. Extrayendo..."))
                installer_core.install_from_bytes(
                    zip_bytes, self._dest_dir,
                    progress_cb=cb, cancel_event=self._cancel_event
                )
            else:
                from pathlib import Path
                src = Path(self._local_path)
                if src.is_dir():
                    installer_core.install_from_folder(
                        src, self._dest_dir, progress_cb=cb, cancel_event=self._cancel_event
                    )
                else:
                    installer_core.install_from_zip(
                        src, self._dest_dir, progress_cb=cb, cancel_event=self._cancel_event
                    )

            self.after(0, self._on_success)

        except InterruptedError:
            self.after(0, lambda: self._on_error("Instalacion cancelada por el usuario."))
        except Exception as exc:
            self.after(0, lambda: self._on_error(str(exc)))


# ─────────────────────────────────────────────────────────────────────────────
# Pantalla 4A: Exito
# ─────────────────────────────────────────────────────────────────────────────
class SuccessFrame(ctk.CTkFrame):
    def __init__(self, master, on_close, **kwargs):
        super().__init__(master, **kwargs)
        self._build(on_close)

    def _build(self, on_close):
        ctk.CTkLabel(
            self,
            text="✔",
            font=ctk.CTkFont(size=60),
            text_color="#4CAF50",
        ).pack(pady=(50, 10))

        ctk.CTkLabel(
            self,
            text="ADOS Extension instalada correctamente",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(0, 16))

        ctk.CTkLabel(
            self,
            text="Reinicia Autodesk Revit para ver la pestana ADOS\ncon todas las herramientas disponibles.",
            text_color="gray70",
            justify="center",
        ).pack(pady=(0, 40))

        ctk.CTkButton(
            self,
            text="Cerrar",
            height=40,
            width=140,
            command=on_close,
        ).pack(pady=(0, 40))


# ─────────────────────────────────────────────────────────────────────────────
# Pantalla 4B: Error
# ─────────────────────────────────────────────────────────────────────────────
class ErrorFrame(ctk.CTkFrame):
    def __init__(self, master, error_msg, on_retry, on_close, **kwargs):
        super().__init__(master, **kwargs)
        self._build(error_msg, on_retry, on_close)

    def _build(self, error_msg, on_retry, on_close):
        ctk.CTkLabel(
            self,
            text="✗",
            font=ctk.CTkFont(size=60),
            text_color="#F44336",
        ).pack(pady=(50, 10))

        ctk.CTkLabel(
            self,
            text="Error durante la instalacion",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(0, 16))

        detail = ctk.CTkTextbox(self, width=420, height=100, corner_radius=8)
        detail.insert("end", error_msg)
        detail.configure(state="disabled")
        detail.pack(padx=40, pady=(0, 30))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(0, 40))

        ctk.CTkButton(
            btn_row,
            text="Reintentar",
            height=40,
            width=140,
            command=on_retry,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row,
            text="Cerrar",
            height=40,
            width=140,
            fg_color="gray40",
            hover_color="gray30",
            command=on_close,
        ).pack(side="left", padx=8)
