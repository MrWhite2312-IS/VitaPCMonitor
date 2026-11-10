#!/usr/bin/env python3
"""Escucha el puerto de VitaMon y muestra lo que llega. Sirve para probar sin la Vita."""

import argparse
import socket
import time

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=10555)
args = ap.parse_args()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("", args.port))
print(f"Escuchando UDP :{args.port} (Ctrl+C para salir)")
try:
    while True:
        data, addr = sock.recvfrom(2048)
        print(f"{time.strftime('%H:%M:%S')} {addr[0]} {data.decode('ascii', 'replace')}")
except KeyboardInterrupt:
    pass
finally:
    sock.close()
