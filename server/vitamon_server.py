#!/usr/bin/env python3
"""VitaMon: recolecta métricas del PC y las emite por UDP (protocolo VMON1) para la PS Vita."""

import argparse
import json
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import psutil

NA = -1
NVIDIA_CMD = [
    "nvidia-smi",
    "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,clocks.gr",
    "--format=csv,noheader,nounits",
]
RETRY_SECS = 30
LHM_SENSORS = ["Core (Tctl/Tdie)", "Tctl/Tdie", "CPU Package", "Package"]


# ---------- GPU (aislado para poder sumar AMD/Intel después) ----------

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


def read_lhm(url):
    """Temperatura de CPU desde el web server de LibreHardwareMonitor, o None."""
    try:
        with urllib.request.urlopen(url, timeout=1) as resp:
            return find_lhm_cpu_temp(json.load(resp))
    except (OSError, ValueError):
        return None


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


# ---------- Recolector ----------

class Collector:
    def __init__(self, lhm_url, warn=print):
        self.lhm_url = lhm_url
        self.warn = warn
        self.gpu_ok = False
        self.lhm_ok = False
        self.host = re.sub(r"[;=\s]", "-", socket.gethostname())[:60]
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

    def _gpu(self, now):
        if now < self.gpu_next_try:
            return None
        g = read_gpu_nvidia()
        self.gpu_ok = g is not None
        if g is None:
            self.gpu_next_try = now + RETRY_SECS
        return g

    def _cpu_temp(self, now):
        if sys.platform != "win32":
            return read_psutil_temp()
        if now < self.lhm_next_try:
            return None
        t = read_lhm(self.lhm_url)
        self.lhm_ok = t is not None
        if t is None:
            self.lhm_next_try = now + RETRY_SECS
            if not self.lhm_warned:
                self.warn(f"[aviso] LibreHardwareMonitor no responde en {self.lhm_url}: ctemp=-1 "
                      "(ábrelo como admin y activa Options > Remote Web Server > Run)")
                self.lhm_warned = True
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

        ctemp = self._cpu_temp(now)
        gpu = self._gpu(now) or {}

        return {
            "host": self.host,
            "cpu": sum(cores) / len(cores) if cores else NA,
            "cores": cores,
            "ctemp": ctemp if ctemp is not None else NA,
            "ram": vm.percent,
            "ramu": (vm.total - vm.available) / 2**30,
            "ramt": vm.total / 2**30,
            "gpu": gpu.get("gpu", NA),
            "gtemp": gpu.get("gtemp", NA),
            "vramu": gpu.get("vramu", NA),
            "vramt": gpu.get("vramt", NA),
            "gclk": gpu.get("gclk", NA),
            "up": max(up, 0.0),
            "down": max(down, 0.0),
            "disk": disk,
            "ts": int(time.time()),
        }


def fmt(v):
    return "-1" if v is None or v < 0 else f"{v:.1f}"


def build_line(s):
    cores = ",".join(str(round(c)) for c in s["cores"])
    parts = [f"host={s['host']}", f"cpu={fmt(s['cpu'])}", f"cores={cores}"]
    for k in ("ctemp", "ram", "ramu", "ramt", "gpu", "gtemp", "vramu", "vramt", "gclk", "up", "down", "disk"):
        parts.append(f"{k}={fmt(s[k])}")
    parts.append(f"ts={s['ts']}")
    return "VMON1;" + ";".join(parts)


class Sender:
    """Bucle de envío. Lo usan la consola (main) y la ventana (vitamon_gui.py) desde un hilo."""

    def __init__(self, port=10555, interval=1.0, target=None, lhm_url="http://localhost:8085/data.json",
                 on_line=None, on_error=None, warn=print):
        self.dest = (target or "255.255.255.255", port)
        self.interval = interval
        self.collector = Collector(lhm_url, warn=warn)
        self.on_line = on_line or (lambda sample, line: None)
        self.on_error = on_error or (lambda kind, exc: print(f"[error] {kind}: {exc}"))
        self.sent = 0

    def run(self, stop=None):
        """Envía hasta que stop (threading.Event) se active; sin stop, hasta Ctrl+C."""
        stop = stop or threading.Event()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            next_t = time.monotonic()
            while not stop.is_set():
                next_t += self.interval
                if stop.wait(max(0.0, next_t - time.monotonic())):
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

    sender = Sender(args.port, args.interval, args.target, args.lhm_url,
                    on_line=(lambda sample, line: print(line)) if args.verbose else None,
                    on_error=on_error)

    print("VitaMon server")
    print(f"  puerto:      {args.port}")
    print(f"  modo:        {'unicast -> ' + args.target if args.target else 'broadcast'}")
    print("  psutil:      OK")
    print(f"  nvidia-smi:  {'OK' if read_gpu_nvidia() else 'no'}")
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
