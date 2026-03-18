import tkinter as tk
from tkinter import messagebox, filedialog
import sys
import subprocess
import threading
import json
from pathlib import Path
from tkinter import ttk


def get_runtime_path():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent  # 👈 carpeta del .exe
    return Path(__file__).parent

def get_base_path():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent
# =========================
# CONFIG
# =========================

CONFIG_PATH = Path("config.json")


def validar_licencia():
    try:
        import hashlib

        base_path = get_runtime_path()
        licencia_path = base_path / "licencia.key"

        with open(licencia_path, "r") as f:
            clave = f.read().strip()

        hash_valido = "db4660392386784dc52de1ec8e4c0d89"  # ejemplo

        return hashlib.md5(clave.encode()).hexdigest() == hash_valido

    except:
        return False

def cargar_config():
    try:
        if CONFIG_PATH.exists():
            contenido = CONFIG_PATH.read_text().strip()
            if contenido:
                return json.loads(contenido)
    except:
        pass

    return {"ruta_descarga": str(Path.home())}


def guardar_config(config):
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


config = cargar_config()


# =========================
# FUNCIONES
# =========================

def seleccionar_carpeta():
    ruta = filedialog.askdirectory()
    if ruta:
        config["ruta_descarga"] = ruta
        guardar_config(config)
        label_ruta.config(text=f"Destino: {ruta}")


def ejecutar_descarga(urls, modo):
    try:
        base_path = get_base_path()

        script_path = base_path / "descargar_audio.py"
        urls_path = Path.home() / "mhega_urls_temp.txt"

        proceso = subprocess.Popen(
            [
                sys.executable,
                str(script_path),
                str(urls_path),
                "--modo", modo,
                "--workers", "3"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=config["ruta_descarga"]  # 👈 descarga en carpeta elegida
        )

        ultimo_porcentaje = 0

        for linea in proceso.stdout:
            if "[download]" in linea and "%" in linea:
                try:
                    porcentaje = float(linea.split("%")[0].split()[-1])

                    if porcentaje < ultimo_porcentaje:
                        continue

                    ultimo_porcentaje = porcentaje

                    app.after(0, actualizar_progreso, porcentaje)

                except:
                    pass

        proceso.wait()

        if proceso.returncode != 0:
            app.after(0, error_descarga, "Error durante la descarga")
            return

        app.after(0, finalizar_descarga, modo)

    except Exception as e:
        app.after(0, error_descarga, str(e))


def descargar():

    if not Path(config["ruta_descarga"]).exists():
        messagebox.showerror("Error", "La carpeta destino no existe")
        btn_descargar.config(state="normal")
        return

    urls = text.get("1.0", tk.END).strip()
    modo = modo_var.get()

    if not urls:
        messagebox.showerror("Error", "Ingresa al menos una URL")
        return

    # Reset limpio
    progress_bar["value"] = 0
    status_label.config(text="Iniciando descarga...")
    btn_descargar.config(state="disabled")

    # Guardar URLs
    temp_path = Path.home() / "mhega_urls_temp.txt"

    with open(temp_path, "w") as f:
        f.write(urls)

    hilo = threading.Thread(target=ejecutar_descarga, args=(urls, modo))
    hilo.daemon = True
    hilo.start()


def actualizar_progreso(porcentaje):
    progress_bar["value"] = porcentaje
    status_label.config(text=f"Descargando... {int(porcentaje)}%")


def finalizar_descarga(modo):
    progress_bar["value"] = 100
    status_label.config(text="Descarga completada")

    btn_descargar.config(state="normal")

    messagebox.showinfo("Éxito", f"Descarga completada en modo: {modo.upper()}")


def error_descarga(mensaje):
    btn_descargar.config(state="normal")
    status_label.config(text="Error en descarga")
    messagebox.showerror("Error", mensaje)

# =========================
# UI PREMIUM
# =========================

app = tk.Tk()

if not validar_licencia():
    messagebox.showerror(
        "Licencia requerida",
        "Esta es una versión PRO.\nContacta a MhegasDev para obtener acceso."
    )
    app.destroy()
    sys.exit()

app.title("MhegaDownloader PRO")
app.geometry("480x520")
app.configure(bg="#0f172a")  # fondo oscuro


# ====== ESTILOS ======
BG = "#0f172a"
CARD = "#1e293b"
TEXT = "#e2e8f0"
ACCENT = "#22c55e"


def crear_card(parent):
    frame = tk.Frame(parent, bg=CARD, bd=0)
    frame.pack(padx=15, pady=10, fill="x")
    return frame


# ====== TÍTULO ======
tk.Label(
    app,
    text="MhegaDownloader",
    font=("Segoe UI", 16, "bold"),
    bg=BG,
    fg=TEXT
).pack(pady=10)


# ====== INPUT ======
card_input = crear_card(app)

tk.Label(card_input, text="URLs:", bg=CARD, fg=TEXT).pack(anchor="w", padx=10, pady=5)

text = tk.Text(
    card_input,
    height=5,
    bg="#020617",
    fg="white",
    insertbackground="white",
    bd=0
)
text.pack(padx=10, pady=5, fill="x")


# ====== MODO ======
card_modo = crear_card(app)

modo_var = tk.StringVar(value="audio")

tk.Label(card_modo, text="Tipo de descarga", bg=CARD, fg=TEXT).pack(anchor="w", padx=10)

tk.Radiobutton(
    card_modo,
    text="Audio (MP3)",
    variable=modo_var,
    value="audio",
    bg=CARD,
    fg=TEXT,
    selectcolor="#020617"
).pack(anchor="w", padx=20)

tk.Radiobutton(
    card_modo,
    text="Video (MP4)",
    variable=modo_var,
    value="video",
    bg=CARD,
    fg=TEXT,
    selectcolor="#020617"
).pack(anchor="w", padx=20)


# ====== DESTINO ======
card_destino = crear_card(app)

btn_carpeta = tk.Button(
    card_destino,
    text="Seleccionar carpeta",
    command=seleccionar_carpeta,
    bg="#334155",
    fg="white",
    bd=0
)
btn_carpeta.pack(pady=5)

label_ruta = tk.Label(
    card_destino,
    text=f"Destino: {config['ruta_descarga']}",
    bg=CARD,
    fg="#94a3b8"
)
label_ruta.pack()


# ====== BOTÓN ======
btn_descargar = tk.Button(
    app,
    text="DESCARGAR",
    command=descargar,
    bg=ACCENT,
    fg="black",
    font=("Segoe UI", 12, "bold"),
    bd=0,
    height=2
)
btn_descargar.pack(pady=15, ipadx=10)


# ====== STATUS ======
status_label = tk.Label(app, text="Listo", bg=BG, fg="#94a3b8")
status_label.pack()


# ====== PROGRESS ======
progress_bar = ttk.Progressbar(app, mode="determinate", maximum=100)
progress_bar.pack(fill="x", padx=20, pady=10)

# RUN
app.mainloop()