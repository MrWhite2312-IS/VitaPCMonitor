#!/usr/bin/env python3
"""VitaMon: recolecta métricas del PC y las emite por UDP (protocolo VMON1) para la PS Vita."""

import argparse
import json
import re
import socket
import subprocess
import sys
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
    def __init__(self, lhm_url):
        self.lhm_url = lhm_url
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
        if g is None:
            self.gpu_next_try = now + RETRY_SECS
        return g

    def _cpu_temp(self, now):
        if sys.platform != "win32":
            return read_psutil_temp()
        if now < self.lhm_next_try:
            return None
        t = read_lhm(self.lhm_url)
        if t is None:
            self.lhm_next_try = now + RETRY_SECS
            if not self.lhm_warned:
                print(f"[aviso] LibreHardwareMonitor no responde en {self.lhm_url}: ctemp=-1 "
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


def main():
    ap = argparse.ArgumentParser(description="Servidor VitaMon (PC -> PS Vita por UDP)")
    ap.add_argument("--port", type=int, default=10555)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--target", help="IP de la Vita (unicast) si el router bloquea broadcast")
    ap.add_argument("--lhm-url", default="http://localhost:8085/data.json")
    ap.add_argument("--verbose", action="store_true", help="imprime cada línea enviada")
    args = ap.parse_args()

    dest = (args.target or "255.255.255.255", args.port)
    col = Collector(args.lhm_url)

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

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        next_t = time.monotonic()
        while True:
            next_t += args.interval
            time.sleep(max(0.0, next_t - time.monotonic()))
            try:
                line = build_line(col.sample())
            except Exception as e:  # nunca caerse por una lectura rara
                print(f"[error] muestreo: {e}")
                continue
            try:
                sock.sendto(line.encode("ascii", "replace"), dest)
            except OSError as e:
                print(f"[error] envío a {dest[0]}:{dest[1]}: {e}")
                continue
            if args.verbose:
                print(line)
    except KeyboardInterrupt:
        print("\nSaliendo.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
