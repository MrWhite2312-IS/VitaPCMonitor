#!/usr/bin/env python3
"""VitaMon: recolecta métricas del PC y las emite por UDP (protocolo VMON1) para la PS Vita."""

import argparse
import json
import re
import select
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import psutil

import fps
import gpu

NA = -1
NVIDIA_CMD = [
    "nvidia-smi",
    "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,clocks.gr",
    "--format=csv,noheader,nounits",
]
RETRY_SECS = 30
LHM_SENSORS = ["Core (Tctl/Tdie)", "Tctl/Tdie", "CPU Package", "Package"]


# ---------- GPU NVIDIA (AMD e Intel: ver gpu.py) ----------

def read_gpu_nvidia():
    """Devuelve dict gpu/gtemp/vramu/vramt/gclk, o None si nvidia-smi no está o falla."""
    try:
        out = subprocess.run(
            NVIDIA_CMD, capture_output=True, text=True, timeout=2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    parts = [p.strip() for p in out.stdout.strip().splitlines()[0].split(",")]
    if len(parts) < 5:
        return None

    def num(s):
        try:
            return float(s)
        except ValueError:  # "[N/A]"
            return NA

    util, temp, mem_used, mem_total, clk = (num(p) for p in parts[:5])
    mib_to_gb = lambda v: v / 1024 if v >= 0 else NA
    return {"gpu": util, "gtemp": temp, "vramu": mib_to_gb(mem_used),
            "vramt": mib_to_gb(mem_total), "gclk": clk}


# ---------- Temperatura de CPU ----------

def parse_temp_value(value):
    """'54,0 °C' / '54.0 °C' -> 54.0; None si no hay número."""
    m = re.search(r"-?\d+(?:[.,]\d+)?", value or "")
    return float(m.group().replace(",", ".")) if m else None


def find_lhm_cpu_temp(node):
    """Recorre el árbol de LHM: nodo de CPU -> 'Temperatures' -> sensor preferido."""
    text = node.get("Text", "")
    children = node.get("Children", [])
    if "Ryzen" in text or "CPU" in text:
        for child in children:
            if child.get("Text") == "Temperatures":
                sensors = {s.get("Text"): s.get("Value") for s in child.get("Children", [])}
                for name in LHM_SENSORS:
                    if name in sensors:
                        temp = parse_temp_value(sensors[name])
                        if temp is not None:
                            return temp
    for child in children:
        temp = find_lhm_cpu_temp(child)
        if temp is not None:
            return temp
    return None


def read_lhm_tree(url):
    """Árbol JSON completo del web server de LibreHardwareMonitor, o None."""
    try:
        with urllib.request.urlopen(url, timeout=1) as resp:
            return json.load(resp)
    except (OSError, ValueError):
        return None


def read_lhm(url):
    """Temperatura de CPU desde el web server de LibreHardwareMonitor, o None."""
    tree = read_lhm_tree(url)
    return find_lhm_cpu_temp(tree) if tree is not None else None


def read_psutil_temp():
    """Linux/macOS (pruebas): psutil.sensors_temperatures si existe."""
    if not hasattr(psutil, "sensors_temperatures"):
        return None
    try:
        temps = psutil.sensors_temperatures()
    except Exception:
        return None
    for chip in ("k10temp", "coretemp", "zenpower", "cpu_thermal"):
        for entry in temps.get(chip, []):
            if entry.label in ("Tctl", "Tdie", "Package id 0", "") and entry.current:
                return entry.current
    return None


# ---------- Nombres de CPU y GPU (se leen una vez al arrancar) ----------

def _run(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def short_name(name):
    """'AMD Ryzen 5 5600G with Radeon Graphics' -> 'Ryzen 5 5600G'; apto para el protocolo."""
    n = re.sub(r"\((R|TM|tm|r)\)|®|™", "", name or "")
    n = re.sub(r"\s+@.*$", "", n)                                  # "@ 3.60GHz"
    n = re.sub(r"\b\d+-Core Processor\b|\bProcessor\b|\bCPU\b", "", n)
    n = re.sub(r"\bwith Radeon.*$", "", n)
    n = re.sub(r"^\d+th Gen\s+", "", n.strip())                    # "12th Gen Intel Core i5-..."
    n = re.sub(r"^(AMD|Intel|NVIDIA)\s+", "", n)
    n = re.sub(r"^(GeForce|Core|Radeon)\s+(?=\S)", "", n)          # "GeForce RTX 3050" -> "RTX 3050"
    n = re.sub(r"[;=]", " ", n)
    return re.sub(r"\s+", " ", n).strip()[:40]


def read_cpu_name():
    raw = ""
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                raw = winreg.QueryValueEx(k, "ProcessorNameString")[0]
        except OSError:
            pass
    elif sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as f:
                raw = next((l.split(":", 1)[1] for l in f if l.startswith("model name")), "")
        except OSError:
            pass
    elif sys.platform == "darwin":
        raw = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    return short_name(raw)


def read_gpu_name():
    raw = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]).strip().splitlines()
    if raw:
        return short_name(raw[0])
    if sys.platform == "win32":
        # AMD / Intel: la tarjeta con más VRAM dedicada (la misma que eligen los lectores de gpu.py)
        adapters = gpu.dxgi_adapters()
        if adapters:
            return short_name(max(adapters, key=lambda a: a[2])[0])
        out = _run(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_VideoController).Name"]).strip().splitlines()
        out = [l.strip() for l in out if l.strip()]
        if out:
            return short_name(out[0])
    return ""


# ---------- Recolector ----------

class Collector:
    def __init__(self, lhm_url, warn=print):
        self.lhm_url = lhm_url
        self.warn = warn
        self.gpu_ok = False
        self.gpu_source = None  # "nvidia-smi", "LibreHardwareMonitor", "Windows" o None
        self.fps_source = None  # "RivaTuner", "LibreHardwareMonitor" o None
        self.lhm_ok = False
        self.nvidia = read_gpu_nvidia() is not None
        self.win_gpu = None  # gpu.WindowsGpu, solo si no hay nvidia-smi
        self.host = re.sub(r"[;=\s]", "-", socket.gethostname())[:60]
        self.cpu_name = read_cpu_name()
        self.gpu_name = read_gpu_name()
        self.gpu_next_try = 0.0
        self.lhm_next_try = 0.0
        self.lhm_warned = False
        psutil.cpu_percent(percpu=True)  # la primera llamada siempre da 0
        self.last_t = time.monotonic()
        self.last_net = psutil.net_io_counters()
        self.last_disk = self._disk_busy_ms()

    @staticmethod
    def _disk_busy_ms():
        try:
            d = psutil.disk_io_counters()
        except Exception:
            return None
        if d is None:
            return None
        # busy_time solo existe en Linux/BSD; en Windows se aproxima con read_time + write_time
        return getattr(d, "busy_time", None) or (d.read_time + d.write_time)

    def _gpu(self, now, tree):
        """Datos de GPU, de la mejor fuente disponible:
        1. nvidia-smi (NVIDIA)  2. LibreHardwareMonitor (cualquier marca, con temperatura)
        3. contadores de Windows (cualquier marca, sin temperatura ni reloj)."""
        if self.nvidia and now >= self.gpu_next_try:
            g = read_gpu_nvidia()
            if g is not None:
                self.gpu_ok, self.gpu_source = True, "nvidia-smi"
                return g
            self.gpu_next_try = now + RETRY_SECS
        lhm = gpu.pick_gpu(gpu.lhm_gpus(tree)) if tree else None
        win = None
        if sys.platform == "win32":
            if self.win_gpu is None:
                self.win_gpu = gpu.WindowsGpu()
            win = self.win_gpu.sample()
        if lhm and win:  # LHM manda; Windows rellena lo que falte (p. ej. VRAM en algunas Intel)
            lhm = {k: (v if v >= 0 else win.get(k, NA)) if isinstance(v, (int, float)) else v
                   for k, v in lhm.items()}
        g = lhm or win
        self.gpu_ok = g is not None
        self.gpu_source = "LibreHardwareMonitor" if lhm else "Windows" if win else None
        return g

    def _lhm_tree(self, now):
        """Árbol de LHM (una lectura por muestra para CPU y GPU); None si no responde."""
        if sys.platform != "win32" or now < self.lhm_next_try:
            return None
        tree = read_lhm_tree(self.lhm_url)
        if tree is None:
            self.lhm_ok = False
            self.lhm_next_try = now + RETRY_SECS
            if not self.lhm_warned:
                self.warn(f"[aviso] LibreHardwareMonitor no responde en {self.lhm_url}: ctemp=-1 "
                          "(ábrelo como admin y activa Options > Remote Web Server > Run)")
                self.lhm_warned = True
        return tree

    def _cpu_temp(self, tree):
        if sys.platform != "win32":
            return read_psutil_temp()
        t = find_lhm_cpu_temp(tree) if tree is not None else None
        self.lhm_ok = t is not None
        return t

    def sample(self):
        now = time.monotonic()
        dt = max(now - self.last_t, 1e-3)
        self.last_t = now

        cores = psutil.cpu_percent(percpu=True)
        vm = psutil.virtual_memory()

        net = psutil.net_io_counters()
        up = (net.bytes_sent - self.last_net.bytes_sent) / 1024 / dt
        down = (net.bytes_recv - self.last_net.bytes_recv) / 1024 / dt
        self.last_net = net

        busy = self._disk_busy_ms()
        disk = NA
        if busy is not None and self.last_disk is not None:
            disk = min(100.0, max(0.0, (busy - self.last_disk) / (dt * 1000) * 100))
        self.last_disk = busy

        tree = self._lhm_tree(now)
        ctemp = self._cpu_temp(tree)
        g = self._gpu(now, tree) or {}
        # FPS: RivaTuner (cualquier juego y GPU) y, si no, LibreHardwareMonitor (algunas AMD)
        frames = fps.read_fps()
        self.fps_source = "RivaTuner" if frames is not None else None
        if frames is None and g.get("fps", NA) >= 0:
            frames, self.fps_source = g["fps"], "LibreHardwareMonitor"

        return {
            "host": self.host,
            "cpun": self.cpu_name,
            "gpun": self.gpu_name,
            "cpu": sum(cores) / len(cores) if cores else NA,
            "cores": cores,
            "ctemp": ctemp if ctemp is not None else NA,
            "ram": vm.percent,
            "ramu": (vm.total - vm.available) / 2**30,
            "ramt": vm.total / 2**30,
            "gpu": g.get("gpu", NA),
            "gtemp": g.get("gtemp", NA),
            "vramu": g.get("vramu", NA),
            "vramt": g.get("vramt", NA),
            "gclk": g.get("gclk", NA),
            "fps": frames if frames is not None else NA,
            "gsrc": self.gpu_source,  # solo para la ventana; no va en la línea del protocolo
            "fsrc": self.fps_source,  # ídem
            "up": max(up, 0.0),
            "down": max(down, 0.0),
            "disk": disk,
            "ts": int(time.time()),
        }


def fmt(v):
    return "-1" if v is None or v < 0 else f"{v:.1f}"


def build_line(s):
    cores = ",".join(str(round(c)) for c in s["cores"])
    parts = [f"host={s['host']}", f"cpun={s.get('cpun', '')}", f"gpun={s.get('gpun', '')}",
             f"cpu={fmt(s['cpu'])}", f"cores={cores}"]
    for k in ("ctemp", "ram", "ramu", "ramt", "gpu", "gtemp", "vramu", "vramt", "gclk", "up", "down", "disk"):
        parts.append(f"{k}={fmt(s[k])}")
    parts.append(f"fps={fmt(s.get('fps', NA))}")
    parts.append(f"ts={s['ts']}")
    return "VMON1;" + ";".join(parts)


def parse_ack(data, ip):
    """Respuesta de la Vita -> {'ip', 'ver', 'batt' (-1 si no hay), 'chg' (bool), 't'}; None si no lo es."""
    try:
        text = data.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    if not text.startswith("VMONACK1;"):
        return None
    fields = dict(p.split("=", 1) for p in text[9:].split(";") if "=" in p)
    try:
        batt = int(fields.get("batt", -1))
    except ValueError:
        batt = -1
    return {"ip": ip, "ver": fields.get("ver", "")[:16], "batt": batt,
            "chg": fields.get("chg") == "1", "t": time.monotonic()}


class Sender:
    """Bucle de envío. Lo usan la consola (main) y la ventana (vitamon_gui.py) desde un hilo."""

    def __init__(self, port=10555, interval=1.0, target=None, lhm_url="http://localhost:8085/data.json",
                 on_line=None, on_error=None, warn=print, on_ack=None):
        self.dest = (target or "255.255.255.255", port)
        self.interval = interval
        self.collector = Collector(lhm_url, warn=warn)
        self.on_line = on_line or (lambda sample, line: None)
        self.on_error = on_error or (lambda kind, exc: print(f"[error] {kind}: {exc}"))
        self.on_ack = on_ack or (lambda vita: None)
        self.sent = 0
        self.vita = None  # última respuesta de la Vita: dict con ip, ver, batt, chg, t (monotonic)

    def _read_acks(self, sock):
        """Lee las respuestas pendientes de la Vita ("VMONACK1;ver=...;batt=...;chg=...")."""
        while True:
            try:
                data, addr = sock.recvfrom(512)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:  # p. ej. WSAECONNRESET por un ICMP "puerto inalcanzable"
                return
            vita = parse_ack(data, addr[0])
            if vita:
                self.vita = vita
                self.on_ack(vita)

    def run(self, stop=None):
        """Envía hasta que stop (threading.Event) se active; sin stop, hasta Ctrl+C.
        Entre envíos escucha en el mismo socket las respuestas de la Vita (conexión en dos sentidos)."""
        stop = stop or threading.Event()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if hasattr(socket, "SIO_UDP_CONNRESET"):  # Windows: que un ICMP no rompa recvfrom
            try:
                sock.ioctl(socket.SIO_UDP_CONNRESET, False)
            except (OSError, ValueError):
                pass
        sock.setblocking(False)
        try:
            next_t = time.monotonic()
            while not stop.is_set():
                next_t += self.interval
                # esperar al próximo envío atendiendo las respuestas que lleguen
                while not stop.is_set():
                    left = next_t - time.monotonic()
                    if left <= 0:
                        break
                    try:
                        ready, _, _ = select.select([sock], [], [], min(left, 0.25))
                    except (OSError, ValueError):
                        ready = []
                        stop.wait(min(left, 0.25))
                    if ready:
                        self._read_acks(sock)
                if stop.is_set():
                    break
                try:
                    sample = self.collector.sample()
                    line = build_line(sample)
                except Exception as e:  # nunca caerse por una lectura rara
                    self.on_error("sample", e)
                    continue
                try:
                    sock.sendto(line.encode("ascii", "replace"), self.dest)
                except OSError as e:
                    self.on_error("send", e)
                    continue
                self.sent += 1
                self.on_line(sample, line)
        finally:
            sock.close()


def main():
    ap = argparse.ArgumentParser(description="Servidor VitaMon (PC -> PS Vita por UDP)")
    ap.add_argument("--port", type=int, default=10555)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--target", help="IP de la Vita (unicast) si el router bloquea broadcast")
    ap.add_argument("--lhm-url", default="http://localhost:8085/data.json")
    ap.add_argument("--verbose", action="store_true", help="imprime cada línea enviada")
    args = ap.parse_args()

    def on_error(kind, exc):
        if kind == "send":
            print(f"[error] envío a {sender.dest[0]}:{sender.dest[1]}: {exc}")
        else:
            print(f"[error] muestreo: {exc}")

    seen = set()

    def on_ack(vita):  # se avisa una vez por cada Vita que responde
        if vita["ip"] not in seen:
            seen.add(vita["ip"])
            batt = f", batería {vita['batt']}%" if vita["batt"] >= 0 else ""
            print(f"[ok] la Vita {vita['ip']} está recibiendo (VitaMon {vita['ver'] or '?'}{batt})")

    sender = Sender(args.port, args.interval, args.target, args.lhm_url,
                    on_line=(lambda sample, line: print(line)) if args.verbose else None,
                    on_error=on_error, on_ack=on_ack)

    print("VitaMon server")
    print(f"  puerto:      {args.port}")
    print(f"  modo:        {'unicast -> ' + args.target if args.target else 'broadcast'}")
    print("  psutil:      OK")
    print(f"  GPU:         {sender.collector.gpu_name or '?'}")
    print(f"  nvidia-smi:  {'OK' if sender.collector.nvidia else 'no (AMD/Intel: LibreHardwareMonitor o contadores de Windows)'}")
    if sys.platform == "win32":
        print(f"  LHM:         {'OK' if read_lhm(args.lhm_url) is not None else 'no'}")
    else:
        print(f"  temp CPU:    {'OK (psutil)' if read_psutil_temp() is not None else 'no'}")
    print("Ctrl+C para salir.")

    try:
        sender.run()
    except KeyboardInterrupt:
        print("\nSaliendo.")


if __name__ == "__main__":
    main()
