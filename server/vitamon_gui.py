#!/usr/bin/env python3
"""VitaMon con ventana: lo mismo que vitamon_server.py pero sin consola.

Es lo que se empaqueta como VitaMon.exe (ver build_exe.bat).
Opciones: --start (empieza a enviar al abrir), --minimized (abre minimizado, o en la bandeja
si esa opción está activa).
"""

import ipaddress
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import gpu
import vitamon_server as vs
from i18n import LANGS, Translator

try:  # bandeja del sistema (opcional: sin pystray la app funciona igual, sin esa opción)
    import pystray
    from PIL import Image
    TRAY_ERROR = None
except Exception as e:  # ImportError, o un backend que falla al cargar
    pystray = None
    TRAY_ERROR = e

APP_NAME = "VitaMon"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEFAULTS = {"lang": None, "target": "", "port": 10555, "auto_send": True, "tray": True}


# ---------- Rutas y configuración ----------

def resource(name):
    """Archivo empaquetado junto al programa (PyInstaller lo extrae en sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def config_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME, "config.json")


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return cfg


def log_error(msg):
    """El .exe no tiene consola: los errores van a %APPDATA%\\VitaMon\\error.log."""
    import datetime
    try:
        os.makedirs(os.path.dirname(config_path()), exist_ok=True)
        with open(os.path.join(os.path.dirname(config_path()), "error.log"), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except OSError:
        pass


def save_config(cfg):
    try:
        os.makedirs(os.path.dirname(config_path()), exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


# ---------- Inicio con Windows (HKCU\...\Run, no necesita admin) ----------

def login_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --start --minimized'
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    return f'"{exe}" "{os.path.abspath(__file__)}" --start --minimized'


def get_run_at_login():
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_run_at_login(enabled):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, login_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


def already_running():
    """Evita dos VitaMon a la vez (mandarían cada dato dos veces)."""
    if sys.platform != "win32":
        return False
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    already_running.handle = k32.CreateMutexW(None, False, "Local\\VitaMonServer")
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


# ---------- Ventana ----------

def fmt_pct(v):
    return "--" if v is None or v < 0 else f"{v:.0f}%"


def fmt_temp(v):
    return "--°C" if v is None or v < 0 else f"{v:.0f}°C"


class App:
    def __init__(self, root, cfg, start_now, minimized):
        self.root = root
        self.cfg = cfg
        self.t = Translator(cfg.get("lang"))
        self.events = queue.Queue()
        self.sender = None
        self.stop_evt = None
        self.thread = None
        self.gpu_src = None  # fuente de la GPU: None = aún no se sabe, False = ninguna
        self.lhm_ok = None
        self.labels = []  # (widget, clave) para retraducir al cambiar de idioma
        self.tray = None  # pystray.Icon mientras la opción de bandeja esté activa

        root.minsize(520, 0)
        self.icon_path = None
        for icon in (resource("icon0.png"), resource(os.path.join("..", "vita", "sce_sys", "icon0.png"))):
            try:
                root.iconphoto(True, tk.PhotoImage(file=icon))
                self.icon_path = icon
                break
            except tk.TclError:
                pass
        self._build()
        self._retranslate()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Unmap>", self._on_unmap)
        root.after(150, self._poll)
        self._check_sources_async()
        if self.tray_enabled:
            self._tray_start()

        if start_now or cfg.get("auto_send"):
            root.after(300, self.start)
        if minimized:
            if self.tray_enabled:
                root.withdraw()  # directo a la bandeja, sin botón en la barra de tareas
            else:
                root.iconify()

    # --- construcción ---

    def _label(self, parent, key, **kw):
        w = ttk.Label(parent, **kw)
        self.labels.append((w, key))
        return w

    def _build(self):
        pad = {"padx": 10, "pady": 4}
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="both", expand=True)
        top.columnconfigure(1, weight=1)

        # idioma
        self._label(top, "language").grid(row=0, column=0, sticky="w", **pad)
        self.lang_var = tk.StringVar(value=LANGS[self.t.lang])
        lang_box = ttk.Combobox(top, textvariable=self.lang_var, values=list(LANGS.values()),
                                state="readonly", width=14)
        lang_box.grid(row=0, column=1, sticky="e", **pad)
        lang_box.bind("<<ComboboxSelected>>", self.on_lang)

        # conexión
        self._label(top, "target").grid(row=1, column=0, sticky="w", **pad)
        self.target_var = tk.StringVar(value=self.cfg.get("target") or "")
        self.target_entry = ttk.Entry(top, textvariable=self.target_var)
        self.target_entry.grid(row=1, column=1, sticky="ew", **pad)
        self.hint = self._label(top, "target_hint", foreground="#666", wraplength=480, justify="left")
        self.hint.grid(row=2, column=0, columnspan=2, sticky="w", padx=10)

        self._label(top, "port").grid(row=3, column=0, sticky="w", **pad)
        self.port_var = tk.StringVar(value=str(self.cfg.get("port") or 10555))
        self.port_entry = ttk.Entry(top, textvariable=self.port_var, width=8)
        self.port_entry.grid(row=3, column=1, sticky="w", **pad)

        # opciones
        self.auto_var = tk.BooleanVar(value=bool(self.cfg.get("auto_send")))
        auto = ttk.Checkbutton(top, variable=self.auto_var, command=self._save)
        auto.grid(row=4, column=0, columnspan=2, sticky="w", **pad)
        self.labels.append((auto, "auto_send"))
        self.login_var = tk.BooleanVar(value=get_run_at_login())
        login = ttk.Checkbutton(top, variable=self.login_var, command=self.on_login)
        login.grid(row=5, column=0, columnspan=2, sticky="w", **pad)
        if sys.platform != "win32":
            login.state(["disabled"])
        self.labels.append((login, "run_at_login"))
        self.tray_var = tk.BooleanVar(value=bool(self.cfg.get("tray")) and pystray is not None)
        tray = ttk.Checkbutton(top, variable=self.tray_var, command=self.on_tray_option)
        tray.grid(row=6, column=0, columnspan=2, sticky="w", **pad)
        if pystray is None:
            tray.state(["disabled"])
        self.labels.append((tray, "tray_option"))

        # botón
        self.btn = ttk.Button(top, command=self.toggle)
        self.btn.grid(row=7, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        # estado
        st = ttk.LabelFrame(top, padding=8)
        st.grid(row=8, column=0, columnspan=2, sticky="ew", **pad)
        self.labels.append((st, "status"))
        self.status = tk.Label(st, anchor="w", font=("Segoe UI", 10, "bold"))
        self.status.pack(fill="x")
        self.now = ttk.Label(st, anchor="w", font=("Consolas", 10))
        self.now.pack(fill="x", pady=(4, 0))
        self.packets = ttk.Label(st, anchor="w", foreground="#666")
        self.packets.pack(fill="x")

        # fuentes
        src = ttk.LabelFrame(top, padding=8)
        src.grid(row=9, column=0, columnspan=2, sticky="ew", **pad)
        src.columnconfigure(0, weight=1)
        self.labels.append((src, "sources"))
        self._label(src, "src_gpu").grid(row=0, column=0, sticky="w")
        self.gpu_lbl = tk.Label(src)
        self.gpu_lbl.grid(row=0, column=1, sticky="e")
        self._label(src, "src_lhm").grid(row=1, column=0, sticky="w")
        self.lhm_lbl = tk.Label(src)
        self.lhm_lbl.grid(row=1, column=1, sticky="e")
        self.src_help = ttk.Label(src, foreground="#a15c00", wraplength=470, justify="left")
        self.src_help.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # registro
        lg = ttk.LabelFrame(top, padding=6)
        lg.grid(row=10, column=0, columnspan=2, sticky="nsew", **pad)
        top.rowconfigure(10, weight=1)
        self.labels.append((lg, "log"))
        self.log_box = tk.Text(lg, height=6, width=60, state="disabled", font=("Consolas", 9), wrap="word")
        self.log_box.pack(fill="both", expand=True)

    # --- textos ---

    def _retranslate(self):
        t = self.t
        self.root.title(t("title"))
        for w, key in self.labels:
            w.configure(text=t(key))
        self.btn.configure(text=t("stop") if self.running else t("start"))
        self._refresh_status()
        self._refresh_sources()
        if self.tray:
            self.tray.update_menu()

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def _dest_text(self):
        return self.sender.dest[0] if self.sender and self.cfg.get("target") else self.t("broadcast")

    def _refresh_status(self):
        if self.running:
            self.status.configure(text="● " + self.t("running", dest=self._dest_text()), fg="#1e8e3e")
        else:
            self.status.configure(text="● " + self.t("stopped"), fg="#888")
        n = self.sender.sent if self.sender else 0
        self.packets.configure(text=self.t("packets", n=n))
        if self.tray:  # texto al pasar el ratón por el icono (máx. 127 caracteres en Windows)
            tip = f"{APP_NAME}: " + self.status.cget("text").lstrip("● ")
            if self.tray.title != tip[:127]:
                self.tray.title = tip[:127]

    # --- bandeja del sistema ---

    @property
    def tray_enabled(self):
        return pystray is not None and bool(self.tray_var.get())

    def _tray_start(self):
        if self.tray or pystray is None:
            return
        try:
            image = Image.open(self.icon_path) if self.icon_path else Image.new("RGB", (64, 64), "#3cc86e")
        except OSError:
            image = Image.new("RGB", (64, 64), "#3cc86e")
        # los clics llegan en el hilo de pystray: se pasan a la ventana por la cola de eventos
        post = lambda action: (lambda icon, item: self.events.put(("tray", action)))
        menu = pystray.Menu(
            pystray.MenuItem(lambda item: self.t("tray_show"), post("show"), default=True),
            pystray.MenuItem(lambda item: self.t("stop") if self.running else self.t("start"), post("toggle")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: self.t("tray_quit"), post("quit")),
        )
        try:
            self.tray = pystray.Icon(APP_NAME, image, APP_NAME, menu)
            self.tray.run_detached()
        except Exception as e:
            log_error(f"no se pudo crear el icono de la bandeja: {e!r}")
            self.tray = None
            return
        self._refresh_status()

    def _tray_stop(self):
        if self.tray:
            self.tray.stop()
            self.tray = None

    def _on_unmap(self, event):
        # al minimizar con la opción activa: ocultar la ventana y dejar solo el icono
        if event.widget is self.root and self.tray_enabled and self.root.state() == "iconic":
            self._tray_start()
            self.root.after(0, self.root.withdraw)

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def on_tray_option(self):
        self.cfg["tray"] = bool(self.tray_var.get())
        self._save()
        if self.tray_enabled:
            self._tray_start()
        else:
            self._tray_stop()

    def _refresh_sources(self):
        def show(lbl, ok):
            if ok is None:
                lbl.configure(text="…", fg="#888")
            else:
                lbl.configure(text=self.t("ok") if ok else self.t("missing"), fg="#1e8e3e" if ok else "#c5221f")
        # GPU: muestra de dónde salen los datos (nvidia-smi / LibreHardwareMonitor / Windows)
        if self.gpu_src is None:
            self.gpu_lbl.configure(text="…", fg="#888")
        elif not self.gpu_src:
            self.gpu_lbl.configure(text=self.t("missing"), fg="#c5221f")
        else:
            self.gpu_lbl.configure(text=self.gpu_src, fg="#a15c00" if self.gpu_src == "Windows" else "#1e8e3e")
        show(self.lhm_lbl, self.lhm_ok)
        tips = []
        if self.gpu_src is False:
            tips.append(self.t("gpu_help"))
        elif self.gpu_src == "Windows":
            tips.append(self.t("gpu_windows_help"))
        if self.lhm_ok is False and sys.platform == "win32":
            tips.append(self.t("lhm_help"))
        self.src_help.configure(text="\n".join(tips))
        if tips:
            self.src_help.grid()
        else:
            self.src_help.grid_remove()

    def log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > 200:
            self.log_box.delete("1.0", f"{lines - 200}.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # --- acciones ---

    def _save(self):
        self.cfg["auto_send"] = bool(self.auto_var.get())
        self.cfg["lang"] = self.t.lang
        save_config(self.cfg)

    def on_lang(self, _evt=None):
        name = self.lang_var.get()
        self.t.lang = next(code for code, n in LANGS.items() if n == name)
        self._save()
        self._retranslate()

    def on_login(self):
        try:
            set_run_at_login(self.login_var.get())
        except OSError as e:
            self.login_var.set(get_run_at_login())
            messagebox.showerror(APP_NAME, self.t("err_login", err=e))

    def _check_sources_async(self):
        def work():
            tree = vs.read_lhm_tree("http://localhost:8085/data.json") if sys.platform == "win32" else None
            if vs.read_gpu_nvidia() is not None:
                src = "nvidia-smi"
            elif tree and gpu.lhm_gpus(tree):
                src = "LibreHardwareMonitor"
            elif sys.platform == "win32" and gpu.WindowsGpu().ok:
                src = "Windows"
            else:
                src = False
            lhm = vs.find_lhm_cpu_temp(tree) is not None if tree else \
                (vs.read_psutil_temp() is not None if sys.platform != "win32" else False)
            self.events.put(("sources", src, lhm))
        threading.Thread(target=work, daemon=True).start()

    def toggle(self):
        self.stop() if self.running else self.start()

    def start(self):
        if self.running:
            return
        target = self.target_var.get().strip()
        try:
            port = int(self.port_var.get())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror(APP_NAME, self.t("err_port"))
            return
        if target:
            try:
                ipaddress.IPv4Address(target)
            except ValueError:
                messagebox.showerror(APP_NAME, self.t("err_ip"))
                return
        self.cfg.update(target=target, port=port)
        self._save()

        ev = self.events
        self.sender = vs.Sender(
            port=port, target=target or None,
            on_line=lambda sample, line: ev.put(("line", sample)),
            on_error=lambda kind, exc: ev.put(("error", kind, exc)),
            warn=lambda msg: None,  # la ventana muestra su propio aviso traducido
        )
        self.stop_evt = threading.Event()
        self.thread = threading.Thread(target=self.sender.run, args=(self.stop_evt,), daemon=True)
        self.thread.start()
        for w in (self.target_entry, self.port_entry):
            w.state(["disabled"])
        self.log(self.t("log_started", dest=self.sender.dest[0], port=port))
        self._retranslate()

    def stop(self):
        if not self.running:
            return
        self.stop_evt.set()
        self.thread.join(timeout=3)
        for w in (self.target_entry, self.port_entry):
            w.state(["!disabled"])
        self.now.configure(text="")
        self.log(self.t("log_stopped"))
        self._retranslate()

    def _poll(self):
        last_err = None
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "line":
                    s = ev[1]
                    self.now.configure(text=(
                        f"{self.t('now')}:  CPU {fmt_pct(s['cpu'])} {fmt_temp(s['ctemp'])}   "
                        f"GPU {fmt_pct(s['gpu'])} {fmt_temp(s['gtemp'])}   RAM {fmt_pct(s['ram'])}"))
                    src, lhm = s.get("gsrc") or False, s["ctemp"] >= 0
                    if (src, lhm) != (self.gpu_src, self.lhm_ok):
                        self.gpu_src, self.lhm_ok = src, lhm
                        self._refresh_sources()
                elif ev[0] == "error":
                    _, kind, exc = ev
                    msg = self.t("err_send", dest=self.sender.dest[0], err=exc) if kind == "send" \
                        else self.t("err_sample", err=exc)
                    if msg != last_err:  # no llenar el registro con el mismo error cada segundo
                        self.log(msg)
                        last_err = msg
                elif ev[0] == "sources":
                    self.gpu_src, self.lhm_ok = ev[1], ev[2]
                    self._refresh_sources()
                elif ev[0] == "tray":
                    if ev[1] == "show":
                        self.show_window()
                    elif ev[1] == "toggle":
                        self.toggle()
                    elif ev[1] == "quit":
                        self.on_close()
                        return
        except queue.Empty:
            pass
        if self.running:
            self._refresh_status()
        self.root.after(250, self._poll)

    def on_close(self):
        self._save()
        if self.running:
            self.stop_evt.set()
        self._tray_stop()
        self.root.destroy()


def main():
    args = set(sys.argv[1:])
    cfg = load_config()
    if already_running():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(APP_NAME, Translator(cfg.get("lang"))("already_running"))
        return
    if sys.platform == "win32":
        try:  # texto nítido en pantallas con escala
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    import traceback
    if TRAY_ERROR is not None:
        log_error(f"bandeja no disponible: {TRAY_ERROR!r}")
    root = tk.Tk()
    root.report_callback_exception = lambda *exc: log_error("".join(traceback.format_exception(*exc)))
    try:
        App(root, cfg, start_now="--start" in args, minimized="--minimized" in args)
    except Exception:
        log_error(traceback.format_exc())
        raise
    root.mainloop()


if __name__ == "__main__":
    main()
