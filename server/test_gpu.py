#!/usr/bin/env python3
"""Tests del lector de GPU de LibreHardwareMonitor (gpu.py) con árboles de ejemplo.

Los nombres de sensores son los que publica LHM: el caso NVIDIA + Radeon integrada se copió
de un PC real (Ryzen 5 5600G + RTX 3050).
"""

import gpu


def node(text, groups, image=""):
    return {"Text": text, "ImageURL": image, "Children": [
        {"Text": g, "Children": [{"Text": n, "Value": v} for n, v in sensors.items()]}
        for g, sensors in groups.items()]}


def tree(*hardware):
    return {"Text": "Sensor", "Children": [{"Text": "PC", "Children": list(hardware)}]}


CPU = node("AMD Ryzen 5 5600G with Radeon Graphics", {
    "Temperatures": {"Core (Tctl/Tdie)": "43.8 °C"},
    "Load": {"CPU Total": "11.5 %", "CPU Core #1": "25.0 %"},
}, "images_icon/cpu.png")

RTX = node("NVIDIA GeForce RTX 3050", {
    "Clocks": {"GPU Core": "600.0 MHz", "GPU Memory": "810.0 MHz"},
    "Temperatures": {"GPU Core": "42.0 °C", "GPU Hot Spot": "54.6 °C"},
    "Load": {"GPU Core": "31.0 %", "D3D 3D": "9.6 %"},
    "Data": {"GPU Memory Used": "1359.0 MB", "GPU Memory Total": "8192.0 MB"},
}, "images_icon/nvidia.png")

RADEON_IGPU = node("AMD Radeon(TM) Graphics", {
    "Clocks": {"GPU Core": "400.0 MHz"},
    "Load": {"GPU Core": "4.0 %", "D3D 3D": "3.9 %"},
    "Data": {"GPU Memory Used": "287.0 MB", "GPU Memory Total": "512.0 MB"},
}, "images_icon/ati.png")

RADEON_RX = node("AMD Radeon RX 6700 XT", {
    "Clocks": {"GPU Core": "2589,0 MHz"},  # coma decimal (Windows en español)
    "Temperatures": {"GPU Core": "61,0 °C", "GPU Hot Spot": "75,0 °C"},
    "Load": {"GPU Core": "97,0 %"},
    "SmallData": {"GPU Memory Used": "9216,0 MB", "GPU Memory Total": "12288,0 MB"},
}, "images_icon/ati.png")

INTEL_IGPU = node("Intel(R) UHD Graphics 630", {
    "Load": {"D3D 3D": "12.5 %", "D3D Video Decode": "0.0 %"},
    "Data": {"D3D Shared Memory Used": "512.0 MB"},
}, "images_icon/intel.png")


def test_real_pc_nvidia_plus_radeon_igpu():
    gpus = gpu.lhm_gpus(tree(CPU, RTX, RADEON_IGPU))
    assert [g["name"] for g in gpus] == ["NVIDIA GeForce RTX 3050", "AMD Radeon(TM) Graphics"]
    best = gpu.pick_gpu(gpus)
    assert best["name"] == "NVIDIA GeForce RTX 3050"  # la de más VRAM, no la integrada
    assert best["gpu"] == 31.0 and best["gtemp"] == 42.0 and best["gclk"] == 600.0
    assert abs(best["vramu"] - 1359 / 1024) < 1e-6 and best["vramt"] == 8.0


def test_amd_discrete_over_intel_igpu():
    best = gpu.pick_gpu(gpu.lhm_gpus(tree(CPU, INTEL_IGPU, RADEON_RX)))
    assert best["name"] == "AMD Radeon RX 6700 XT"
    assert best["gpu"] == 97.0 and best["gtemp"] == 61.0 and best["gclk"] == 2589.0
    assert best["vramu"] == 9.0 and best["vramt"] == 12.0


def test_intel_igpu_only():
    best = gpu.pick_gpu(gpu.lhm_gpus(tree(CPU, INTEL_IGPU)))
    assert best["name"] == "Intel(R) UHD Graphics 630"
    assert best["gpu"] == 12.5          # sin "GPU Core": usa D3D 3D
    assert best["gtemp"] == -1 and best["gclk"] == -1 and best["vramt"] == -1
    assert best["vramu"] == 0.5         # memoria compartida usada


def test_cpu_is_not_a_gpu():
    assert gpu.lhm_gpus(tree(CPU)) == []
    assert gpu.pick_gpu([]) is None
    assert gpu.lhm_gpus(None) == []


def test_parse_value():
    assert gpu.parse_value("1359.0 MB") == (1359.0, "MB")
    assert gpu.parse_value("54,5 °C") == (54.5, "°C")
    assert gpu.parse_value("") == (None, "")
    assert gpu._to_gb("2.0 GB") == 2.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK: {len(tests)} tests de GPU")
