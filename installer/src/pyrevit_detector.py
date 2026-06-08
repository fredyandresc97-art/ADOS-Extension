# -*- coding: utf-8 -*-
import os
import winreg
import shutil
from pathlib import Path


def find_pyrevit() -> dict | None:
    """Busca la instalacion de pyRevit en el sistema. Retorna dict con info o None."""
    # 1. Buscar en el registro de Windows
    for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
        result = _search_registry(hive)
        if result:
            return result

    # 2. Buscar en rutas conocidas
    known_paths = [
        Path(os.environ.get("APPDATA", "")) / "pyRevit-Master" / "bin" / "pyrevit.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "pyRevit" / "bin" / "pyrevit.exe",
        Path(os.environ.get("APPDATA", "")) / "pyRevit" / "bin" / "pyrevit.exe",
    ]
    for cli in known_paths:
        if cli.exists():
            return {"cli_path": cli, "version": "detectado", "install_dir": cli.parent.parent}

    # 3. Buscar en PATH del sistema
    cli_in_path = shutil.which("pyrevit")
    if cli_in_path:
        cli = Path(cli_in_path)
        return {"cli_path": cli, "version": "detectado", "install_dir": cli.parent.parent}

    return None


def _search_registry(hive) -> dict | None:
    try:
        uninstall_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        key = winreg.OpenKey(hive, uninstall_key)
        count = winreg.QueryInfoKey(key)[0]
        for i in range(count):
            try:
                sub_name = winreg.EnumKey(key, i)
                sub_key = winreg.OpenKey(key, sub_name)
                try:
                    name, _ = winreg.QueryValueEx(sub_key, "DisplayName")
                    if "pyRevit" in str(name):
                        try:
                            loc, _ = winreg.QueryValueEx(sub_key, "InstallLocation")
                            cli = Path(loc) / "bin" / "pyrevit.exe"
                            if cli.exists():
                                return {
                                    "cli_path": cli,
                                    "version": str(name),
                                    "install_dir": Path(loc),
                                }
                        except FileNotFoundError:
                            pass
                except FileNotFoundError:
                    pass
                finally:
                    winreg.CloseKey(sub_key)
            except OSError:
                pass
        winreg.CloseKey(key)
    except OSError:
        pass
    return None


def get_default_extensions_dir() -> Path:
    """Retorna el directorio de extensiones predeterminado de pyRevit."""
    return Path(os.environ.get("APPDATA", "")) / "pyRevit" / "Extensions"


def is_ados_installed(extensions_dir: Path) -> bool:
    """Verifica si ADOS.extension ya existe en el directorio dado."""
    return (extensions_dir / "ADOS.extension").exists()
