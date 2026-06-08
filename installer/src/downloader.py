# -*- coding: utf-8 -*-
import threading
import requests

# Actualiza esta URL con el link directo al ZIP en GitHub Releases
# Ejemplo: https://github.com/TU_USUARIO/ADOS-Extension/releases/latest/download/ADOS.extension.zip
GITHUB_ZIP_URL = "https://github.com/TU_USUARIO/ADOS-Extension/releases/latest/download/ADOS.extension.zip"

TIMEOUT_SECONDS = 30
CHUNK_SIZE = 8192  # 8 KB por chunk


def download_with_progress(
    url: str,
    progress_cb=None,
    cancel_event: threading.Event = None,
) -> bytes:
    """
    Descarga un archivo desde una URL en modo streaming.
    Llama a progress_cb(porcentaje, mensaje) por cada chunk descargado.
    Lanza ConnectionError si no hay internet, o requests.HTTPError si el servidor responde con error.
    """
    try:
        response = requests.get(url, stream=True, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            "No se pudo conectar a internet.\n"
            "Verifica tu conexion e intenta de nuevo."
        )
    except requests.exceptions.Timeout:
        raise TimeoutError(
            f"La conexion agoto el tiempo de espera ({TIMEOUT_SECONDS}s).\n"
            "Intenta de nuevo o usa instalacion desde archivo local."
        )
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"Error del servidor: {e}")

    total_size = int(response.headers.get("Content-Length", 0))
    downloaded = 0
    chunks = []

    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Descarga cancelada por el usuario.")

        if chunk:
            chunks.append(chunk)
            downloaded += len(chunk)

            if progress_cb:
                if total_size > 0:
                    pct = int(downloaded / total_size * 100)
                    kb_done = downloaded // 1024
                    kb_total = total_size // 1024
                    msg = f"Descargando... {kb_done} KB / {kb_total} KB"
                else:
                    pct = 0
                    msg = f"Descargando... {downloaded // 1024} KB"
                progress_cb(pct, msg)

    return b"".join(chunks)
