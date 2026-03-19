import tkinter as tk
from tkinter import messagebox, filedialog
from tkinter import ttk
import sys
import threading
import json
from pathlib import Path
import os
import subprocess


def get_runtime_path():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


BASE_DIR = get_runtime_path()
CONFIG_PATH = BASE_DIR / "config.json"


def validar_licencia():
    try:
        import hashlib

        licencia_path = BASE_DIR / "licencia.key"

        with open(licencia_path, "r", encoding="utf-8") as f:
            clave = f.read().strip()

        hash_valido = "db4660392386784dc52de1ec8e4c0d89"
        return hashlib.md5(clave.encode()).hexdigest() == hash_valido
    except Exception:
        return False


def cargar_config():
    try:
        if CONFIG_PATH.exists():
            contenido = CONFIG_PATH.read_text(encoding="utf-8").strip()
            if contenido:
                return json.loads(contenido)
    except Exception:
        pass

    return {
        "ruta_descarga": str(Path.home() / "Downloads"),
        "perfil_video": "compatibilidad"
    }


def guardar_config(config_data):
    CONFIG_PATH.write_text(
        json.dumps(config_data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


config = cargar_config()


# =========================
# ESTILOS / CONSTANTES
# =========================
BG = "#020617"
CARD = "#0f172a"
CARD_SOFT = "#111c32"
CARD_SOFT_2 = "#0b1325"
TEXT = "#e5e7eb"
SUBTEXT = "#94a3b8"
MUTED = "#64748b"
ACCENT = "#22c55e"
ACCENT_HOVER = "#16a34a"
BORDER = "#1f2937"
BUTTON_DARK = "#334155"
BUTTON_DARK_HOVER = "#475569"
TEXTAREA_BG = "#030b1a"
INFO = "#38bdf8"
WARN = "#f59e0b"
ERROR = "#ef4444"


# =========================
# APP
# =========================
app = tk.Tk()
app._toast_actual = None
app._preview_job = None
app._responsive_mode = None
app._main_window_id = None

if not validar_licencia():
    messagebox.showerror(
        "Licencia requerida",
        "Esta es una versión PRO.\nContacta a MhegasDev para obtener acceso."
    )
    app.destroy()
    sys.exit()

app.title("MhegaDownloader PRO")
app.geometry("850x500")
app.minsize(760, app.winfo_reqheight())
app.configure(bg=BG)

app.resizable(True, False)

# =========================
# HELPERS UI
# =========================
def crear_card(parent, padx=16, pady=10):
    frame = tk.Frame(
        parent,
        bg=CARD,
        highlightbackground=BORDER,
        highlightthickness=1,
        bd=0
    )
    frame.pack(fill="x", padx=padx, pady=pady)
    return frame


def crear_panel_soft(parent):
    return tk.Frame(
        parent,
        bg=CARD_SOFT,
        highlightbackground=BORDER,
        highlightthickness=1,
        bd=0
    )


def crear_radio(parent, text, variable, value, command=None):
    return tk.Radiobutton(
        parent,
        text=text,
        variable=variable,
        value=value,
        command=command,
        bg=CARD_SOFT,
        fg=TEXT,
        activebackground=CARD_SOFT,
        activeforeground="white",
        selectcolor="#020617",
        font=("Segoe UI", 10),
        bd=0,
        highlightthickness=0,
        anchor="w",
        justify="left",
        relief="flat",
        padx=4,
        pady=3
    )


def crear_boton_hover(btn, bg_normal, bg_hover, fg="white"):
    def on_enter(_):
        if str(btn["state"]) != "disabled":
            btn.config(bg=bg_hover)

    def on_leave(_):
        if str(btn["state"]) != "disabled":
            btn.config(bg=bg_normal)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    btn.config(fg=fg)


def crear_badge(parent, titulo, valor, color=INFO):
    box = tk.Frame(
        parent,
        bg=CARD_SOFT_2,
        highlightbackground=BORDER,
        highlightthickness=1
    )

    tk.Label(
        box,
        text=titulo,
        bg=CARD_SOFT_2,
        fg=SUBTEXT,
        font=("Segoe UI", 8)
    ).pack(anchor="w", padx=10, pady=(8, 2))

    lbl = tk.Label(
        box,
        text=valor,
        bg=CARD_SOFT_2,
        fg=color,
        font=("Segoe UI", 11, "bold")
    )
    lbl.pack(anchor="w", padx=10, pady=(0, 8))

    return box, lbl


def truncar_texto(texto, limite=80):
    texto = texto or ""
    return texto if len(texto) <= limite else texto[:limite - 3] + "..."


# =========================
# FUNCIONES DE NEGOCIO/UI
# =========================
def seleccionar_carpeta():
    ruta = filedialog.askdirectory()
    if ruta:
        config["ruta_descarga"] = ruta
        guardar_config(config)
        actualizar_ruta_ui()
        mostrar_toast("Carpeta de destino actualizada", "ok")


def on_cambiar_perfil_video():
    config["perfil_video"] = perfil_video_var.get()
    guardar_config(config)
    actualizar_badges_superiores()


def actualizar_estado(mensaje, tipo="info"):
    colores = {
        "ok": ACCENT,
        "error": ERROR,
        "warn": WARN,
        "info": INFO
    }

    iconos = {
        "ok": "✅",
        "error": "❌",
        "warn": "⚠️",
        "info": "🔄"
    }

    status_label.config(
        text=f"{iconos.get(tipo, '🔄')} {mensaje}",
        fg=colores.get(tipo, INFO)
    )
    app.update_idletasks()


def mostrar_toast(mensaje, tipo="ok"):
    colores = {
        "ok": ACCENT,
        "error": ERROR,
        "info": INFO,
        "warn": WARN
    }

    if hasattr(app, "_toast_actual") and app._toast_actual is not None:
        try:
            app._toast_actual.destroy()
        except Exception:
            pass

    toast = tk.Label(
        app,
        text=mensaje,
        bg="#081120",
        fg=colores.get(tipo, "white"),
        font=("Segoe UI", 9, "bold"),
        bd=1,
        relief="solid",
        padx=14,
        pady=8
    )
    toast.place(relx=0.5, rely=0.965, anchor="s")
    app._toast_actual = toast

    def destruir_toast():
        try:
            toast.destroy()
        except Exception:
            pass
        app._toast_actual = None

    app.after(3000, destruir_toast)


def abrir_carpeta():
    ruta = config["ruta_descarga"]

    try:
        if sys.platform == "win32":
            os.startfile(ruta)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", ruta])
        else:
            subprocess.Popen(["xdg-open", ruta])
    except Exception as e:
        mostrar_toast(f"No se pudo abrir la carpeta: {e}", "error")


def obtener_urls_validas():
    contenido = text.get("1.0", tk.END).strip()
    if not contenido:
        return []

    urls = []
    for linea in contenido.splitlines():
        linea = linea.strip()
        if linea:
            urls.append(linea)
    return urls


def obtener_primera_url():
    urls = obtener_urls_validas()
    return urls[0] if urls else None


def detectar_cambio_texto(event=None):
    actualizar_contador_urls()

    if hasattr(app, "_preview_job") and app._preview_job is not None:
        try:
            app.after_cancel(app._preview_job)
        except Exception:
            pass

    app._preview_job = app.after(700, ejecutar_preview_auto)


def ejecutar_preview_auto():
    url = obtener_primera_url()

    if not url:
        preview_title_value.config(text="Sin vista previa")
        preview_meta_value.config(text="Esperando el primer enlace...")
        preview_url_value.config(text="Sin URL detectada")
        preview_extra_value.config(text="Canal: —  •  Duración: —  •  Tipo: —")
        badge_preview_value.config(text="Sin datos")
        return

    preview_title_value.config(text="Cargando preview...")
    preview_meta_value.config(text="Consultando información del video...")
    preview_url_value.config(text=truncar_texto(url, 70))
    preview_extra_value.config(text="Canal: consultando...  •  Duración: ...  •  Tipo: ...")
    badge_preview_value.config(text="Consultando")

    def tarea():
        try:
            import yt_dlp
            import socket

            socket.setdefaulttimeout(10)

            ydl = yt_dlp.YoutubeDL({
                "quiet": True,
                "no_warnings": True,
                "skip_download": True
            })

            info = ydl.extract_info(url, download=False)

            titulo = info.get("title", "Sin título")
            duracion = info.get("duration", 0)
            canal = info.get("uploader") or "Canal desconocido"
            extractor = info.get("extractor_key") or info.get("extractor") or "Fuente desconocida"
            vista = info.get("view_count")
            ext = info.get("ext") or "N/D"

            mins = duracion // 60
            segs = duracion % 60
            duracion_txt = f"{mins}:{segs:02d}" if duracion else "N/D"

            if vista is None:
                vista_txt = "Sin vistas"
            elif vista >= 1_000_000:
                vista_txt = f"{vista / 1_000_000:.1f}M vistas"
            elif vista >= 1_000:
                vista_txt = f"{vista / 1_000:.1f}K vistas"
            else:
                vista_txt = f"{vista} vistas"

            titulo_corto = truncar_texto(titulo, 95)
            canal_corto = truncar_texto(canal, 40)
            extractor_corto = truncar_texto(extractor, 22)

            app.after(
                0,
                lambda: aplicar_preview(
                    titulo=titulo_corto,
                    meta=f"{vista_txt} • Fuente: {extractor_corto}",
                    extra=f"Canal: {canal_corto}  •  Duración: {duracion_txt}  •  Tipo: {ext.upper()}",
                    badge_text="Listo"
                )
            )

        except Exception:
            app.after(0, aplicar_preview_fallback)

    threading.Thread(target=tarea, daemon=True).start()


def aplicar_preview(titulo, meta, extra="", badge_text="Listo"):
    preview_title_value.config(text=titulo)
    preview_meta_value.config(text=meta)
    preview_url_value.config(text=truncar_texto(obtener_primera_url() or "", 70))
    preview_extra_value.config(text=extra if extra else "Preview listo")
    badge_preview_value.config(text=badge_text)


def aplicar_preview_fallback():
    preview_title_value.config(text="Preview no disponible")
    preview_meta_value.config(text="Puedes continuar con la descarga")
    preview_url_value.config(text="No fue posible consultar el video")
    preview_extra_value.config(text="El enlace podría requerir validación adicional")
    badge_preview_value.config(text="No disponible")


def ejecutar_descarga(urls, modo, perfil_video):
    try:
        from downloader_core import descargar_youtube

        archivos_generados = descargar_youtube(
            urls=urls,
            modo=modo,
            ruta_salida=config["ruta_descarga"],
            perfil_video=perfil_video,
            progress_callback=lambda p: app.after(0, actualizar_progreso, p),
            status_callback=lambda s: app.after(0, actualizar_estado, s, "info")
        )

        app.after(0, finalizar_descarga, modo, archivos_generados)

    except Exception as e:
        app.after(0, error_descarga, str(e))


def descargar():
    ruta_destino = Path(config["ruta_descarga"])

    if not ruta_destino.exists():
        mostrar_toast("La carpeta destino no existe", "error")
        btn_descargar.config(text="⬇ Descargar", state="normal")
        return

    urls = text.get("1.0", tk.END).strip()
    modo = modo_var.get()
    perfil_video = perfil_video_var.get()

    if not urls:
        mostrar_toast("Ingresa al menos una URL", "error")
        return

    progress_bar["value"] = 0
    progress_text.config(text="Preparando proceso...")
    actualizar_estado("Preparando descarga...", "info")
    btn_descargar.config(text="Procesando...", state="disabled")
    btn_carpeta.config(state="disabled")
    btn_abrir_carpeta.config(state="disabled")

    hilo = threading.Thread(
        target=ejecutar_descarga,
        args=(urls, modo, perfil_video),
        daemon=True
    )
    hilo.start()


def actualizar_progreso(porcentaje):
    porcentaje = max(0, min(100, porcentaje))
    progress_bar["value"] = porcentaje

    if porcentaje < 15:
        texto = f"{int(porcentaje)}% • Inicializando descarga"
    elif porcentaje < 45:
        texto = f"{int(porcentaje)}% • Descargando contenido"
    elif porcentaje < 75:
        texto = f"{int(porcentaje)}% • Procesando archivo"
    elif porcentaje < 100:
        texto = f"{int(porcentaje)}% • Finalizando"
    else:
        texto = "100% • Completado con éxito"

    progress_text.config(text=texto)
    app.update_idletasks()


def finalizar_descarga(modo, archivos_generados=None):
    progress_bar["value"] = 100
    progress_text.config(text="100% • Completado con éxito")
    actualizar_estado("Descarga completada", "ok")

    btn_descargar.config(text="⬇ Descargar", state="normal")
    btn_carpeta.config(state="normal")
    btn_abrir_carpeta.config(state="normal")

    if archivos_generados:
        total_archivos = len(archivos_generados)

        if total_archivos == 1:
            mostrar_toast(f"1 archivo generado en modo {modo.upper()}", "ok")
        else:
            mostrar_toast(f"{total_archivos} archivos generados en modo {modo.upper()}", "ok")
    else:
        mostrar_toast("Descarga completada", "ok")

    app.update_idletasks()


def error_descarga(mensaje):
    btn_descargar.config(text="⬇ Descargar", state="normal")
    btn_carpeta.config(state="normal")
    btn_abrir_carpeta.config(state="normal")

    progress_text.config(text="Proceso interrumpido")
    actualizar_estado("Error en descarga", "error")
    mostrar_toast(mensaje, "error")

    app.update_idletasks()


def actualizar_contador_urls():
    # Ya no hay badge, pero mantenemos lógica por si se reutiliza
    return len(obtener_urls_validas())


def actualizar_ruta_ui():
    # UI simplificada: no se muestra en pantalla
    pass

def actualizar_badges_superiores():
    # Ya no existen badges, pero mantenemos consistencia lógica
    pass

# =========================
# HEADER COMPACTO
# =========================
header = tk.Frame(app, bg=BG)
header.pack(fill="x", padx=16, pady=(10, 6))

tk.Label(
    header,
    text="MhegaDownloader PRO",
    font=("Segoe UI", 18, "bold"),
    bg=BG,
    fg="white"
).pack(anchor="w")

# =========================
# MAIN AREA (SIN SCROLL)
# =========================
main = tk.Frame(app, bg=BG)
main.pack(fill="x", expand=True, padx=16, pady=6)

main.grid_columnconfigure(0, weight=4)
main.grid_columnconfigure(1, weight=1)
main.grid_rowconfigure(0, weight=1)

# =========================
# TEXTAREA
# =========================
left_panel = tk.Frame(main, bg=CARD)
left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

left_panel.grid_rowconfigure(0, weight=0)
left_panel.grid_rowconfigure(1, weight=1)

left_panel.grid_columnconfigure(0, weight=1)

tk.Label(
    left_panel,
    text="URLs",
    bg=CARD,
    fg=TEXT,
    font=("Segoe UI", 10, "bold")
).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))

text_container = tk.Frame(left_panel, bg=CARD)
text_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

ALTURA_MAIN = 250

text_container.configure(height=ALTURA_MAIN)
text_container.grid_propagate(False)


text_container.grid_rowconfigure(0, weight=1)
text_container.grid_columnconfigure(0, weight=1)

text = tk.Text(
    text_container,
    bg=TEXTAREA_BG,
    fg="white",
    insertbackground="white",
    font=("Consolas", 10),
    relief="flat",
    padx=10,
    pady=10
)
text.grid(row=0, column=0, sticky="nsew")

scroll = tk.Scrollbar(text_container, command=text.yview)
scroll.grid(row=0, column=1, sticky="ns")
text.config(yscrollcommand=scroll.set)

text.bind("<KeyRelease>", detectar_cambio_texto)

# =========================
# PREVIEW
# =========================
right_panel = tk.Frame(main, bg=CARD)
right_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

right_panel.configure(height=ALTURA_MAIN)
right_panel.grid_propagate(False)

right_panel.grid_rowconfigure(0, weight=1)

tk.Label(
    right_panel,
    text="Preview",
    bg=CARD,
    fg=TEXT,
    font=("Segoe UI", 10, "bold")
).pack(anchor="w", padx=10, pady=(8, 6))

preview_title_value = tk.Label(
    right_panel,
    text="Sin preview",
    bg=CARD,
    fg=TEXT,
    font=("Segoe UI", 10, "bold"),
    wraplength=260,
    justify="left"
)
preview_title_value.pack(fill="x", padx=10)

preview_meta_value = tk.Label(
    right_panel,
    text="Esperando URL...",
    bg=CARD,
    fg=SUBTEXT,
    font=("Segoe UI", 9)
)
preview_meta_value.pack(fill="x", padx=10, pady=(4, 0))

preview_url_value = tk.Label(
    right_panel,
    text="",
    bg=CARD,
    fg="#7dd3fc",
    font=("Segoe UI", 8)
)
preview_url_value.pack(fill="x", padx=10, pady=(4, 0))

preview_extra_value = tk.Label(
    right_panel,
    text="",
    bg=CARD,
    fg=MUTED,
    font=("Segoe UI", 8)
)
preview_extra_value.pack(fill="x", padx=10, pady=(4, 10))

badge_preview_value = tk.Label(
    right_panel,
    text="",
    bg="#0b1325",
    fg=INFO,
    font=("Segoe UI", 8, "bold"),
    padx=8,
    pady=2
)
badge_preview_value.pack(anchor="e", padx=10)

# =========================
# TOOLBAR (CONFIG + CTA)
# =========================
toolbar = tk.Frame(app, bg=CARD)
toolbar.pack(fill="x", padx=16, pady=6)

modo_var = tk.StringVar(value="audio")
perfil_video_var = tk.StringVar(value=config.get("perfil_video", "compatibilidad"))

tk.Label(toolbar, text="Formato:", bg=CARD, fg=SUBTEXT, font=("Segoe UI", 9)).pack(side="left", padx=(6,2))
crear_radio(toolbar, "Audio", modo_var, "audio", actualizar_badges_superiores).pack(side="left", padx=6)
crear_radio(toolbar, "Video", modo_var, "video", actualizar_badges_superiores).pack(side="left", padx=6)

tk.Label(toolbar, text="Calidad:", bg=CARD, fg=SUBTEXT, font=("Segoe UI", 9)).pack(side="left", padx=(12,2))
crear_radio(toolbar, "Compatible", perfil_video_var, "compatibilidad", on_cambiar_perfil_video).pack(side="left", padx=12)
crear_radio(toolbar, "Alta", perfil_video_var, "alta_calidad", on_cambiar_perfil_video).pack(side="left", padx=6)

tk.Label(toolbar, text="Ubicación:", bg=CARD, fg=SUBTEXT, font=("Segoe UI", 9)).pack(side="left", padx=(12,2))

btn_carpeta = tk.Button(
    toolbar,
    text="📁",
    command=seleccionar_carpeta,
    bg=BUTTON_DARK,
    fg="white",
    bd=0,
    padx=10
)
btn_carpeta.pack(side="left", padx=12)

btn_abrir_carpeta = tk.Button(
    toolbar,
    text="📂",
    command=abrir_carpeta,
    bg=BUTTON_DARK,
    fg="white",
    bd=0,
    padx=10
)
btn_abrir_carpeta.pack(side="left", padx=4)

btn_descargar = tk.Button(
    toolbar,
    text="⬇ Descargar",
    command=descargar,
    bg=ACCENT,
    fg="black",
    font=("Segoe UI", 11, "bold"),
    bd=0,
    padx=20,
    pady=6
)
btn_descargar.pack(side="right", padx=10)

# =========================
# STATUS BAR
# =========================
status_bar = tk.Frame(app, bg="#010409")
status_bar.pack(fill="x")

status_label = tk.Label(
    status_bar,
    text="Listo",
    bg="#010409",
    fg=ACCENT,
    font=("Segoe UI", 9)
)
status_label.pack(side="left", padx=8)

progress_bar = ttk.Progressbar(
    status_bar,
    mode="determinate",
    maximum=100,
    length=200
)
progress_bar.pack(side="right", padx=8, pady=2)

progress_text = tk.Label(
    status_bar,
    text="0%",
    bg="#010409",
    fg=SUBTEXT,
    font=("Segoe UI", 9)
)
progress_text.pack(side="right", padx=4)

# =========================
# FOOTER
# =========================
footer = tk.Label(
    app,
    text="MhegasDev © 2026",
    bg=BG,
    fg="#334155",
    font=("Segoe UI", 8)
)
footer.pack(pady=(2, 4))


# =========================
# RESPONSIVE SIMPLE (PRO)
# =========================
def aplicar_layout_responsive(event=None):
    width = app.winfo_width()

    # Ajuste dinámico de preview (texto)
    wrap = max(220, int(width * 0.25))

    preview_title_value.config(wraplength=wrap)
    preview_meta_value.config(wraplength=wrap)
    preview_url_value.config(wraplength=wrap)
    preview_extra_value.config(wraplength=wrap)

    # Ajuste textarea (proporción)
    if width < 800:
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=1)
    else:
        main.grid_columnconfigure(0, weight=3)  # URLs domina
        main.grid_columnconfigure(1, weight=2)  # preview secundario

# =========================
# INIT UI STATE
# =========================
actualizar_contador_urls()
actualizar_ruta_ui()
actualizar_badges_superiores()
aplicar_layout_responsive(app.winfo_width())

# 👇 AQUÍ VA EXACTAMENTE
app.update_idletasks()
app.geometry(f"{app.winfo_width()}x{app.winfo_reqheight()}")

if __name__ == "__main__":
    app.mainloop()