import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

import yt_dlp


BASE_DIR = Path(os.path.dirname(sys.executable)) if getattr(sys, "frozen", False) else Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def escribir_log(nombre, datos):
    ruta = LOG_DIR / nombre
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(json.dumps(datos, ensure_ascii=False) + "\n")


def get_creationflags():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_process(comando):
    return subprocess.run(
        comando,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=get_creationflags()
    )


def get_ffmpeg_path():
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        local_ffmpeg = os.path.join(exe_dir, "ffmpeg.exe")
        if os.path.exists(local_ffmpeg):
            return exe_dir

    ffmpeg_exe = shutil.which("ffmpeg")
    if ffmpeg_exe:
        return os.path.dirname(ffmpeg_exe)

    return None


def get_ffmpeg_exe(ffmpeg_path):
    if ffmpeg_path:
        return os.path.join(ffmpeg_path, "ffmpeg.exe")
    return "ffmpeg"


def get_ffprobe_exe(ffmpeg_path):
    if ffmpeg_path:
        return os.path.join(ffmpeg_path, "ffprobe.exe")
    return "ffprobe"


def asegurar_nombre_unico(path_str):
    path = Path(path_str)
    if not path.exists():
        return str(path)

    base = path.with_suffix("")
    ext = path.suffix
    i = 1
    while True:
        candidato = Path(f"{base}_{i}{ext}")
        if not candidato.exists():
            return str(candidato)
        i += 1


def validar_archivo_video(path_archivo, ffmpeg_path):
    ffprobe_exe = get_ffprobe_exe(ffmpeg_path)

    comando = [
        ffprobe_exe,
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        path_archivo
    ]

    resultado = run_process(comando)

    if resultado.returncode != 0:
        raise Exception(f"ffprobe falló:\n{resultado.stderr}")

    try:
        data = json.loads(resultado.stdout)
    except Exception:
        raise Exception("No se pudo parsear la salida de ffprobe")

    streams = data.get("streams", [])
    formato = data.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if not video_stream:
        raise Exception("El archivo final no contiene stream de video")

    if not audio_stream:
        raise Exception("El archivo final no contiene stream de audio")

    return {
        "path": path_archivo,
        "format_name": formato.get("format_name"),
        "duration": formato.get("duration"),
        "size": formato.get("size"),
        "video_codec": video_stream.get("codec_name"),
        "audio_codec": audio_stream.get("codec_name"),
        "pix_fmt": video_stream.get("pix_fmt"),
        "profile": video_stream.get("profile"),
        "level": video_stream.get("level"),
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
    }


def es_video_compatible_windows(metadata, perfil_video):
    if not metadata:
        return False

    if metadata.get("video_codec") != "h264":
        return False

    if metadata.get("audio_codec") != "aac":
        return False

    if metadata.get("pix_fmt") != "yuv420p":
        return False

    profile = str(metadata.get("profile", "")).lower()
    level = metadata.get("level")

    if perfil_video == "compatibilidad":
        perfiles_validos = {"main", "baseline", "constrained baseline"}
        if profile not in perfiles_validos:
            return False

        if level is not None and int(level) > 31:
            return False

    return True


def convertir_a_mp4_universal(input_path, output_path, ffmpeg_path, perfil_video, status_callback=None):
    ffmpeg_exe = get_ffmpeg_exe(ffmpeg_path)

    if perfil_video == "alta_calidad":
        profile = "high"
        level = "4.1"
        preset = "slow"
        crf = "20"
    else:
        profile = "main"
        level = "3.1"
        preset = "medium"
        crf = "23"

    if status_callback:
        status_callback("Procesando video...")

    comando = [
        ffmpeg_exe,
        "-y",
        "-i", input_path,
        "-map", "0:v:0",
        "-map", "0:a:0",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", crf,
        "-profile:v", profile,
        "-level", level,
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-movflags", "+faststart",
        output_path,
    ]

    resultado = run_process(comando)

    escribir_log("conversion.log", {
        "timestamp": datetime.now().isoformat(),
        "fase": "ffmpeg_convert",
        "perfil_video": perfil_video,
        "input": input_path,
        "output": output_path,
        "returncode": resultado.returncode,
        "stderr": resultado.stderr[-4000:],
    })

    if resultado.returncode != 0:
        raise Exception(f"Error al convertir video con ffmpeg:\n{resultado.stderr}")

    if not os.path.exists(output_path):
        raise Exception("FFmpeg no generó el archivo MP4 final")

    if os.path.getsize(output_path) == 0:
        raise Exception("El archivo MP4 final quedó vacío")


def obtener_ruta_real_descargada(info):
    requested = info.get("requested_downloads") or []
    for item in requested:
        filepath = item.get("filepath")
        if filepath and os.path.exists(filepath):
            return filepath

    filename = info.get("_filename")
    if filename and os.path.exists(filename):
        return filename

    return None


def generar_nombre_salida(archivo_descargado, ruta_salida, perfil_video):
    titulo_base = Path(archivo_descargado).stem
    sufijo = "_final_hq.mp4" if perfil_video == "alta_calidad" else "_final_compat.mp4"
    return asegurar_nombre_unico(os.path.join(ruta_salida, f"{titulo_base}{sufijo}"))


def descargar_audio(lista_urls, ruta_salida, ffmpeg_path, progress_callback=None, status_callback=None):
    if not ffmpeg_path:
        raise Exception("FFmpeg no encontrado. Instálalo o colócalo junto al .exe")

    ydl_opts = {
        "outtmpl": os.path.join(ruta_salida, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "ffmpeg_location": ffmpeg_path,
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "progress_hooks": [],
    }

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            descargado = d.get("downloaded_bytes", 0)
            if total and progress_callback:
                progress_callback((descargado / total) * 100)

        elif d["status"] == "finished":
            if progress_callback:
                progress_callback(100)

    ydl_opts["progress_hooks"].append(hook)

    if status_callback:
        status_callback("Descargando audio...")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(lista_urls)


def descargar_video(lista_urls, ruta_salida, ffmpeg_path, progress_callback=None, perfil_video="compatibilidad", status_callback=None):
    if not ffmpeg_path:
        raise Exception("FFmpeg no encontrado. Instálalo o colócalo junto al .exe")

    archivos_finales = []
    total_urls = len(lista_urls)

    for idx, url in enumerate(lista_urls, start=1):

        try:
            if progress_callback:
                progress_callback(0)

            if status_callback:
                status_callback(f"[{idx}/{total_urls}] Descargando video...")

            ydl_opts = {
                "outtmpl": os.path.join(ruta_salida, "%(title)s.%(ext)s"),
                "noplaylist": True,
                "quiet": True,
                "ffmpeg_location": ffmpeg_path,
                "merge_output_format": "mp4",
                "format": (
                    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                    "best[ext=mp4]/"
                    "bestvideo+bestaudio/best"
                ),
                "progress_hooks": [],
            }

            def hook(d):
                if d["status"] == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate")
                    descargado = d.get("downloaded_bytes", 0)
                    if total and progress_callback:
                        progress_callback((descargado / total) * 100)

                elif d["status"] == "finished":
                    if progress_callback:
                        progress_callback(100)

            ydl_opts["progress_hooks"].append(hook)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            archivo_descargado = obtener_ruta_real_descargada(info)

            escribir_log("descargas.log", {
                "timestamp": datetime.now().isoformat(),
                "fase": "download",
                "index": idx,
                "total": total_urls,
                "url": url,
                "titulo": info.get("title"),
                "archivo_descargado": archivo_descargado,
                "ext": info.get("ext"),
                "perfil_video": perfil_video,
            })

            if not archivo_descargado:
                raise Exception("No se pudo localizar el archivo descargado real")

            if status_callback:
                status_callback(f"[{idx}/{total_urls}] Analizando compatibilidad...")

            try:
                metadata_original = validar_archivo_video(archivo_descargado, ffmpeg_path)
            except Exception as e:
                metadata_original = None
                escribir_log("errores.log", {
                    "timestamp": datetime.now().isoformat(),
                    "fase": "metadata_original",
                    "error": str(e),
                    "archivo": archivo_descargado
                })

            salida_final = generar_nombre_salida(archivo_descargado, ruta_salida, perfil_video)

            # 🚀 MODO INTELIGENTE (skip conversion)
            if es_video_compatible_windows(metadata_original, perfil_video):

                if status_callback:
                    status_callback(f"[{idx}/{total_urls}] Archivo ya compatible (sin conversión)...")

                shutil.copy2(archivo_descargado, salida_final)

                escribir_log("conversion.log", {
                    "timestamp": datetime.now().isoformat(),
                    "fase": "skip_conversion",
                    "index": idx,
                    "input": archivo_descargado,
                    "output": salida_final,
                })

            else:
                if status_callback:
                    status_callback(f"[{idx}/{total_urls}] Procesando video...")

                convertir_a_mp4_universal(
                    input_path=archivo_descargado,
                    output_path=salida_final,
                    ffmpeg_path=ffmpeg_path,
                    perfil_video=perfil_video,
                    status_callback=status_callback
                )

            if status_callback:
                status_callback(f"[{idx}/{total_urls}] Validando archivo final...")

            metadata_final = validar_archivo_video(salida_final, ffmpeg_path)

            escribir_log("validacion.log", {
                "timestamp": datetime.now().isoformat(),
                "fase": "validate_output",
                "index": idx,
                **metadata_final
            })

            archivos_finales.append(salida_final)

            if status_callback:
                status_callback(f"[{idx}/{total_urls}] Finalizado")

            try:
                if os.path.exists(archivo_descargado):
                    os.remove(archivo_descargado)
            except Exception as e:
                escribir_log("errores.log", {
                    "timestamp": datetime.now().isoformat(),
                    "fase": "cleanup_original",
                    "error": str(e)
                })

        except Exception as e:
            escribir_log("errores.log", {
                "timestamp": datetime.now().isoformat(),
                "fase": "descarga_individual",
                "index": idx,
                "url": url,
                "error": str(e)
            })

            # 👉 NO rompemos el flujo completo
            continue

    return archivos_finales


def descargar_youtube(urls, modo, ruta_salida, perfil_video="compatibilidad", progress_callback=None, status_callback=None):
    ffmpeg_path = get_ffmpeg_path()

    lista_urls = [u.strip() for u in urls.splitlines() if u.strip()]
    if not lista_urls:
        raise Exception("No se proporcionaron URLs válidas")

    os.makedirs(ruta_salida, exist_ok=True)

    if modo == "audio":
        descargar_audio(
            lista_urls,
            ruta_salida,
            ffmpeg_path,
            progress_callback=progress_callback,
            status_callback=status_callback
        )
        return []

    return descargar_video(
        lista_urls,
        ruta_salida,
        ffmpeg_path,
        progress_callback=progress_callback,
        perfil_video=perfil_video,
        status_callback=status_callback
    )