import os
import re
import json
import time
import threading
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

import yt_dlp


# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
CARPETA_DESCARGAS = BASE_DIR / "descargas"
CARPETA_AUDIO = CARPETA_DESCARGAS / "audio"
CARPETA_VIDEO = CARPETA_DESCARGAS / "video"
ARCHIVO_HISTORIAL = BASE_DIR / "historial.json"

HISTORIAL_LOCK = threading.Lock()
PRINT_LOCK = threading.Lock()


# =========================================================
# MODELOS
# =========================================================

@dataclass
class DownloadConfig:
    modo: str = "audio"              # audio | video
    formato_audio: str = "mp3"       # mp3 | wav | flac | m4a
    calidad_video: str = "best"      # best | 1080 | 720 | 480 | 360
    sobrescribir: bool = False
    reintentos: int = 3
    pausa_reintento: int = 3
    usar_playlist: bool = False      # en esta fase lo dejamos apagado para video
    mostrar_progreso: bool = True


# =========================================================
# UTILIDADES
# =========================================================

def imprimir_seguro(texto: str) -> None:
    with PRINT_LOCK:
        print(texto)


def asegurar_directorios() -> None:
    CARPETA_DESCARGAS.mkdir(parents=True, exist_ok=True)
    CARPETA_AUDIO.mkdir(parents=True, exist_ok=True)
    CARPETA_VIDEO.mkdir(parents=True, exist_ok=True)


def limpiar_nombre_archivo(nombre: str) -> str:
    if not nombre:
        return "sin_titulo"

    nombre = re.sub(r'[\\/*?:"<>|]', "", nombre)
    nombre = re.sub(r"\s+", " ", nombre).strip()
    nombre = nombre.rstrip(".")
    return nombre[:180] if len(nombre) > 180 else nombre


def cargar_historial() -> list:
    if not ARCHIVO_HISTORIAL.exists():
        return []

    try:
        with open(ARCHIVO_HISTORIAL, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def guardar_historial(registro: Dict[str, Any]) -> None:
    with HISTORIAL_LOCK:
        historial = cargar_historial()

        reemplazado = False

        for i, item in enumerate(historial):
            if (
                item.get("url") == registro.get("url")
                and item.get("modo") == registro.get("modo")
                and item.get("formato_audio") == registro.get("formato_audio")
                and item.get("calidad_video") == registro.get("calidad_video")
            ):
                historial[i] = registro
                reemplazado = True
                break

        if not reemplazado:
            historial.append(registro)

        with open(ARCHIVO_HISTORIAL, "w", encoding="utf-8") as f:
            json.dump(historial, f, ensure_ascii=False, indent=2)


def ya_descargado(url: str, modo: str, formato_audio: str, calidad_video: str) -> bool:
    historial = cargar_historial()

    for item in historial:
        if (
            item.get("url") == url
            and item.get("modo") == modo
            and item.get("formato_audio") == formato_audio
            and item.get("calidad_video") == calidad_video
            and item.get("estado") == "completado"
        ):
            return True

    return False


def crear_progress_hook(url: str):
    def hook(d):
        estado = d.get("status")

        if estado == "downloading":
            filename = d.get("filename", "")
            percent = d.get("_percent_str", "").strip()
            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()

            mensaje = (
                f"[DESCARGANDO] {Path(filename).name} | "
                f"{percent or '?'} | {speed or '?'} | ETA {eta or '?'}"
            )
            imprimir_seguro(mensaje)

        elif estado == "finished":
            filename = d.get("filename", "")
            imprimir_seguro(f"[FINALIZADO] Archivo temporal completado: {Path(filename).name}")

    return hook


# =========================================================
# INFORMACIÓN Y DETECCIÓN
# =========================================================

def obtener_info_video(url: str) -> Dict[str, Any]:
    opciones = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": False,
        "noplaylist": False,
    }

    with yt_dlp.YoutubeDL(opciones) as ydl:
        return ydl.extract_info(url, download=False)


def es_playlist(info: Dict[str, Any]) -> bool:
    return info.get("_type") == "playlist"


def obtener_url_real(info: Dict[str, Any], url_original: str) -> str:
    return info.get("webpage_url") or info.get("original_url") or url_original


# =========================================================
# FORMATOS Y OPCIONES YT-DLP
# =========================================================

def construir_selector_video(calidad: str) -> str:
    """
    Construye el selector de formato para video.

    Basado en la sintaxis oficial de yt-dlp para selección de formatos:
    - bestvideo*+bestaudio/best
    - filtros por height<=N
    """
    calidad = (calidad or "best").lower().strip()

    if calidad == "best":
        return "bv*+ba/b"

    mapa_altura = {
        "1080": 1080,
        "720": 720,
        "480": 480,
        "360": 360,
    }

    altura = mapa_altura.get(calidad)
    if not altura:
        raise ValueError(
            "Calidad de video no válida. Usa: best, 1080, 720, 480 o 360"
        )

    return f"bv*[height<={altura}]+ba/b[height<={altura}]"


def construir_template_salida(modo: str) -> str:
    if modo == "audio":
        carpeta = CARPETA_AUDIO
    else:
        carpeta = CARPETA_VIDEO

    return str(carpeta / "%(title).180s [%(id)s].%(ext)s")


def construir_opciones_ydl(config: DownloadConfig, url: str) -> Dict[str, Any]:
    hooks = [crear_progress_hook(url)] if config.mostrar_progreso else []

    opciones = {
        "outtmpl": construir_template_salida(config.modo),
        "restrictfilenames": False,
        "windowsfilenames": True,
        "noplaylist": not config.usar_playlist,
        "ignoreerrors": False,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": hooks,
        "retries": 3,
        "extractor_args": {
            "youtube": {
                "player_client": ["android"]
            }
        }
    }

    if config.modo == "audio":
        opciones.update({
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": config.formato_audio,
                    "preferredquality": "192",
                },
                {
                    "key": "FFmpegMetadata",
                },
            ],
        })
    else:
        opciones.update({
            "format": construir_selector_video(config.calidad_video),
            "merge_output_format": "mp4",
        })

    return opciones


# =========================================================
# DESCARGA
# =========================================================

def registrar_resultado(
    url: str,
    info: Optional[Dict[str, Any]],
    config: DownloadConfig,
    estado: str,
    error: Optional[str] = None
) -> None:
    titulo = None
    video_id = None
    webpage_url = url

    if info:
        titulo = info.get("title")
        video_id = info.get("id")
        webpage_url = obtener_url_real(info, url)

    registro = {
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
        "url": webpage_url,
        "titulo": titulo,
        "video_id": video_id,
        "modo": config.modo,
        "formato_audio": config.formato_audio,
        "calidad_video": config.calidad_video,
        "estado": estado,
        "error": error,
    }

    guardar_historial(registro)


def descargar_url_individual(url: str, config: DownloadConfig) -> bool:
    info = None

    try:
        opciones = construir_opciones_ydl(config, url)

        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=True)

        registrar_resultado(url, info, config, estado="completado")

        imprimir_seguro(f"[OK] Descarga completada: {info.get('title')}")
        return True

    except Exception as e:
        error_msg = str(e)
        registrar_resultado(url, info, config, estado="fallido", error=error_msg)

        imprimir_seguro(f"[ERROR] Fallo en {url}: {error_msg}")
        return False

def ejecutar_con_reintentos(url: str, config: DownloadConfig) -> bool:
    ultimo_error = None

    for intento in range(1, config.reintentos + 1):
        imprimir_seguro(f"[INFO] Intento {intento}/{config.reintentos}: {url}")

        ok = descargar_url_individual(url, config)

        if ok:
            return True

        ultimo_error = f"Fallo en intento {intento}"

        if intento < config.reintentos:
            time.sleep(config.pausa_reintento)

    imprimir_seguro(f"[FALLO] No se pudo descargar: {url}")
    return False


# =========================================================
# UTILIDADES CLI
# =========================================================

def listar_formatos(url: str) -> None:
    opciones = {
        "quiet": False,
        "listformats": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(opciones) as ydl:
        ydl.download([url])


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="YouTube Downloader Pro (CLI) - descarga audio o video desde YouTube"
    )

    parser.add_argument(
        "url",
        nargs="?",
        help="URL del video individual de YouTube"
    )

    parser.add_argument(
        "--modo",
        choices=["audio", "video"],
        help="Tipo de descarga (si no se especifica, se pregunta)"
    )

    parser.add_argument(
        "--audio-format",
        choices=["mp3", "wav", "flac", "m4a"],
        default="mp3",
        help="Formato de salida para audio"
    )

    parser.add_argument(
        "--video-quality",
        choices=["best", "1080", "720", "480", "360"],
        default="best",
        help="Calidad objetivo para video"
    )

    parser.add_argument(
        "--list-formats",
        action="store_true",
        help="Lista formatos disponibles del video y termina"
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Permite descargar aunque ya exista en historial"
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Número de reintentos automáticos"
    )

    parser.add_argument(
        "--retry-wait",
        type=int,
        default=3,
        help="Segundos de espera entre reintentos"
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Número de descargas en paralelo (default: 1)"
    )

    return parser


# =========================================================
# MAIN
# =========================================================

def main():
    asegurar_directorios()

    parser = crear_parser()
    args = parser.parse_args()

    if not args.url:
        parser.error("Debes proporcionar una URL o archivo de URLs.")

    if args.list_formats:
        listar_formatos(args.url)
        return

    config = resolver_configuracion(args)

    entradas = procesar_entrada(args.url)

    procesar_batch(entradas, config, args.workers)


# =========================================================
# SOPORTE PARA ARCHIVOS (FASE 2)
# =========================================================

def es_archivo(ruta: str) -> bool:
    return os.path.isfile(ruta)


def leer_urls_desde_archivo(ruta: str) -> list:
    urls = []

    try:
        with open(ruta, "r", encoding="utf-8") as f:
            for linea in f:
                url = linea.strip()

                if not url:
                    continue

                if url.startswith("#"):
                    continue

                # Normalizar URL
                if not url.startswith("http"):
                    url = "https://" + url

                urls.append(url)

    except Exception as e:
        imprimir_seguro(f"[ERROR] No se pudo leer el archivo: {e}")

    imprimir_seguro(f"[INFO] URLs cargadas: {len(urls)}")

    return urls


def procesar_entrada(entrada: str) -> list:
    """
    Determina si la entrada es:
    - URL individual
    - Archivo con múltiples URLs
    """

    if es_archivo(entrada):
        imprimir_seguro(f"[INFO] Detectado archivo: {entrada}")
        return leer_urls_desde_archivo(entrada)

    return [entrada]


# =========================================================
# MODO INTERACTIVO (FASE 2.1)
# =========================================================

def preguntar_opcion(mensaje: str, opciones: dict) -> str:
    """
    Muestra opciones numeradas y retorna el valor seleccionado
    """
    imprimir_seguro("\n" + mensaje)

    for clave, valor in opciones.items():
        imprimir_seguro(f"{clave}) {valor}")

    while True:
        eleccion = input("> ").strip()

        if eleccion in opciones:
            return opciones[eleccion]

        imprimir_seguro("Opción inválida. Intenta nuevamente.")


def modo_interactivo() -> dict:
    """
    Solicita configuración al usuario
    """
    config = {}

    # Tipo
    tipo = preguntar_opcion(
        "Selecciona tipo de descarga:",
        {
            "1": "audio",
            "2": "video"
        }
    )
    config["modo"] = tipo

    # Audio
    if tipo == "audio":
        formato = preguntar_opcion(
            "Selecciona formato de audio:",
            {
                "1": "mp3",
                "2": "wav",
                "3": "flac",
                "4": "m4a"
            }
        )
        config["formato_audio"] = formato

    # Video
    else:
        calidad = preguntar_opcion(
            "Selecciona calidad de video:",
            {
                "1": "best",
                "2": "1080",
                "3": "720",
                "4": "480",
                "5": "360"
            }
        )
        config["calidad_video"] = calidad

    return config

def resolver_configuracion(args) -> DownloadConfig:
    """
    Decide si usar argumentos CLI o modo interactivo
    """

    # Si el usuario especificó modo → usar CLI
    if args.modo:
        return DownloadConfig(
            modo=args.modo,
            formato_audio=args.audio_format,
            calidad_video=args.video_quality,
            sobrescribir=args.overwrite,
            reintentos=args.retries,
            pausa_reintento=args.retry_wait,
            usar_playlist=False,
            mostrar_progreso=True,
        )

    # Si NO → modo interactivo
    imprimir_seguro("[INFO] Entrando en modo interactivo...")

    data = modo_interactivo()

    return DownloadConfig(
        modo=data.get("modo", "audio"),
        formato_audio=data.get("formato_audio", "mp3"),
        calidad_video=data.get("calidad_video", "best"),
        sobrescribir=args.overwrite,
        reintentos=args.retries,
        pausa_reintento=args.retry_wait,
        usar_playlist=False,
        mostrar_progreso=True,
    )



def procesar_batch(entradas, config, workers=1):

    if workers <= 1:
        for url in entradas:
            ejecutar_con_reintentos(url, config)
        return

    imprimir_seguro(f"[INFO] Ejecutando en paralelo con {workers} workers")

    futures = []

    with ThreadPoolExecutor(max_workers=workers) as executor:

        for url in entradas:
            futures.append(executor.submit(ejecutar_con_reintentos, url, config))

        for future in as_completed(futures):
            try:
                resultado = future.result()
            except Exception as e:
                imprimir_seguro(f"[ERROR THREAD] {e}")

if __name__ == "__main__":
    main()