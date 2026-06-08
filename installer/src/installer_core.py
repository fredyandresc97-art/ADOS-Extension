# -*- coding: utf-8 -*-
import shutil
import zipfile
import threading
from pathlib import Path


def install_from_zip(
    zip_path: str | Path,
    dest_dir: Path,
    progress_cb=None,
    cancel_event: threading.Event = None,
) -> None:
    """Extrae ADOS.extension de un ZIP al directorio destino."""
    zip_path = Path(zip_path)
    dest_extension = dest_dir / "ADOS.extension"

    with zipfile.ZipFile(zip_path, "r") as zf:
        members = [m for m in zf.infolist() if not m.filename.endswith("/")]
        total = len(members)

        for idx, member in enumerate(members):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Instalacion cancelada por el usuario.")

            zf.extract(member, dest_dir)

            if progress_cb:
                pct = int((idx + 1) / total * 100)
                progress_cb(pct, f"Extrayendo archivos... {idx + 1}/{total}")

    # Si el ZIP contiene la carpeta raiz con otro nombre, renombrar
    _ensure_extension_name(dest_dir, dest_extension)


def install_from_folder(
    source_dir: Path,
    dest_dir: Path,
    progress_cb=None,
    cancel_event: threading.Event = None,
) -> None:
    """Copia recursivamente ADOS.extension al directorio destino."""
    source_dir = Path(source_dir)
    dest_extension = dest_dir / "ADOS.extension"

    all_files = list(source_dir.rglob("*"))
    files_only = [f for f in all_files if f.is_file()]
    total = len(files_only)

    if dest_extension.exists():
        shutil.rmtree(dest_extension)

    for idx, src_file in enumerate(files_only):
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Instalacion cancelada por el usuario.")

        rel = src_file.relative_to(source_dir.parent)
        dst_file = dest_dir / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)

        if progress_cb:
            pct = int((idx + 1) / total * 100)
            progress_cb(pct, f"Copiando archivos... {idx + 1}/{total}")


def install_from_bytes(
    zip_bytes: bytes,
    dest_dir: Path,
    progress_cb=None,
    cancel_event: threading.Event = None,
) -> None:
    """Instala desde bytes de un ZIP (descargado en memoria)."""
    import io

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_extension = dest_dir / "ADOS.extension"

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        members = [m for m in zf.infolist() if not m.filename.endswith("/")]
        total = len(members)

        if dest_extension.exists():
            shutil.rmtree(dest_extension)

        for idx, member in enumerate(members):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Instalacion cancelada por el usuario.")

            zf.extract(member, dest_dir)

            if progress_cb:
                pct = int((idx + 1) / total * 100)
                progress_cb(pct, f"Extrayendo archivos... {idx + 1}/{total}")

    _ensure_extension_name(dest_dir, dest_extension)


def _ensure_extension_name(dest_dir: Path, expected: Path) -> None:
    """Si el ZIP extrajo con un nombre diferente, lo renombra a ADOS.extension."""
    if expected.exists():
        return
    for candidate in dest_dir.iterdir():
        if candidate.is_dir() and "ADOS" in candidate.name.upper():
            candidate.rename(expected)
            return
