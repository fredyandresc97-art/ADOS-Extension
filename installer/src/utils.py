# -*- coding: utf-8 -*-
import sys
from pathlib import Path


def resource_path(relative: str) -> Path:
    """Resuelve rutas de assets en desarrollo y dentro del .exe de PyInstaller."""
    base = getattr(sys, "_MEIPASS", Path(__file__).parent.parent)
    return Path(base) / relative
