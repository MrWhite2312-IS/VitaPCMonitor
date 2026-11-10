#!/usr/bin/env python3
"""Pasa una línea real del servidor por el parser C de la Vita (compilado con gcc en el host)."""

import os
import subprocess
import sys
import tempfile

import vitamon_server as vs

HERE = os.path.dirname(os.path.abspath(__file__))
VITA = os.path.join(HERE, "..", "vita")

# El árbol de LHM: el sensor preferido gana aunque venga después, y la coma decimal se acepta.
lhm = {"Text": "Sensor", "Children": [{"Text": "DESKTOP", "Children": [
    {"Text": "AMD Ryzen 5 5600G", "Children": [
        {"Text": "Load", "Children": [{"Text": "CPU Total", "Value": "20,0 %"}]},
        {"Text": "Temperatures", "Children": [
            {"Text": "Core #1", "Value": "40,0 °C"},
            {"Text": "Core (Tctl/Tdie)", "Value": "54,5 °C"},
        ]},
    ]},
]}]}
assert vs.find_lhm_cpu_temp(lhm) == 54.5
assert vs.find_lhm_cpu_temp({"Text": "x", "Children": []}) is None

line = vs.build_line(vs.Collector("http://127.0.0.1:1/none").sample())
assert len(line) < 1024, len(line)
print(line)

with tempfile.TemporaryDirectory() as tmp:
    exe = os.path.join(tmp, "test_protocol")
    subprocess.run(["gcc", "-std=c11", "-I", os.path.join(VITA, "src"),
                    os.path.join(VITA, "src", "protocol.c"),
                    os.path.join(VITA, "tests", "test_protocol.c"), "-o", exe, "-lm"], check=True)
    r = subprocess.run([exe, line])
sys.exit(r.returncode)
