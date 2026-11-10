<div align="center">

# VitaMon

**Turn your PS Vita into a live hardware monitor for your Windows PC.**

CPU, GPU, temperatures, RAM, network and disk on the Vita's screen, updated every second over WiFi.

[![Build](https://github.com/MrWhite2312-IS/VitaPCMonitor/actions/workflows/build.yml/badge.svg)](https://github.com/MrWhite2312-IS/VitaPCMonitor/actions/workflows/build.yml)
[![Latest release](https://img.shields.io/github/v/release/MrWhite2312-IS/VitaPCMonitor?include_prereleases&label=download)](https://github.com/MrWhite2312-IS/VitaPCMonitor/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**English** · [Español](README.es.md)

</div>

<!-- Add a photo of the Vita running VitaMon here, e.g.:
<p align="center"><img src="docs/vita.jpg" alt="VitaMon running on a PS Vita" width="640"></p>
-->

## Features

- **CPU:** total load, a bar per thread, temperature and the CPU model name.
- **GPU (NVIDIA):** load, temperature, VRAM used/total and core clock.
- **RAM, network** (upload/download KB/s) and **disk** activity.
- **60-second graphs** for CPU and GPU load and temperature.
- **Compact view** with four big numbers, readable from across the desk.
- **No setup on the network side:** the PC broadcasts on your LAN and the Vita picks it up. No IPs to type in most cases.
- **Small Windows app with a window, not a console.** It can start with Windows and runs minimized.
- **6 languages** on both the Vita and the PC: English, Español, Português, Français, Deutsch, Italiano.
- **Local only:** data goes from your PC to your Vita over UDP on your own network. Nothing is sent to the internet.

## Requirements

- A PS Vita (or PS TV) with **HENkaku / Ensō** and **VitaShell**.
- A **Windows 10/11** PC on the same network as the Vita (WiFi or Ethernet).
- Optional: an **NVIDIA** GPU for GPU stats, and **LibreHardwareMonitor** for CPU temperature ([details](#optional-sensors)).

## Quick start

### 1. Download

> **Beta:** VitaMon is in public beta. If something doesn't work, please [open an issue](https://github.com/MrWhite2312-IS/VitaPCMonitor/issues) with your Vita firmware, Windows version and GPU.

Get both files from the [latest release](https://github.com/MrWhite2312-IS/VitaPCMonitor/releases) (the newest one at the top of the list):

| File | Goes on |
|------|---------|
| `VitaMon.vpk` | the PS Vita |
| `VitaMon.exe` | the Windows PC (single file) |
| `VitaMon-windows.zip` | the Windows PC: the same app as a folder, if your antivirus complains about the single `.exe` |

### 2. Install on the Vita

1. Copy `VitaMon.vpk` to the Vita with VitaShell:
   - **WiFi (FTP):** press SELECT in VitaShell, then open the `ftp://IP:1337` address it shows in your PC's file explorer and copy the VPK to `ux0:data/`.
   - **USB:** press START in VitaShell → *USB connection*, then copy the VPK to the drive that appears on the PC.
2. In VitaShell, select the VPK, press ✕ and confirm the install. **VitaMon** appears on the home screen.

### 3. Run on the PC

1. Put `VitaMon.exe` in any folder. It does not need to be installed. If you downloaded the `.zip`, extract it and keep the whole `VitaMon` folder together.
2. Double-click it. A small window opens and starts sending right away.
3. The first time, Windows asks about network access: allow it on **Private networks**.

<p align="center"><img src="docs/ventana.png" alt="VitaMon window on Windows" width="420"></p>

| Option | What it does |
|--------|--------------|
| **Language** | Changes the window language. |
| **Vita IP** | Leave it empty. You only need it if the Vita gets nothing ([see below](#troubleshooting)). |
| **Start / Stop** | Starts or stops sending. |
| **Start sending when opened** | No need to press Start every time. |
| **Open when Windows starts** | Launches VitaMon minimized at login. |
| **Data sources** | Shows whether GPU and CPU-temperature data are available, and how to fix it if not. |

Settings are saved in `%APPDATA%\VitaMon\config.json`.

### 4. Open VitaMon on the Vita

Within a couple of seconds the status changes from **Waiting** to **Connected** and the stats appear.

| Button | Action |
|--------|--------|
| SELECT | Change language (remembered for next time) |
| □ | Compact view: CPU %, CPU °C, GPU %, GPU °C in big numbers |
| △ | Debug overlay: last packet, packets/s, IP addresses |
| START | Quit |

The first time, the app uses the Vita's system language (English if it isn't one of the six). The status in the corner shows **Waiting** (nothing received yet, with the Vita's IP), **Connected**, or **No signal** (no data for 3 s; the last values stay on screen, dimmed).

## Optional sensors

CPU load, RAM, network and disk always work. Two things need a bit more:

### CPU temperature: LibreHardwareMonitor

Windows does not expose CPU temperature to normal programs, so VitaMon reads it from [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor):

1. Run LibreHardwareMonitor **as administrator**.
2. Enable *Options → Remote Web Server → Run* (port 8085).
3. Check that `http://localhost:8085/data.json` opens in your browser.

Without it, CPU temperature shows as `--`. The VitaMon window tells you whether it is detected.

### GPU: NVIDIA only (for now)

GPU stats come from `nvidia-smi`, which is installed with the NVIDIA driver. On AMD or Intel GPUs the GPU panel shows `--` (the model name still appears). AMD/Intel support is a welcome contribution: the GPU reader is isolated in `read_gpu_nvidia()` in [`server/vitamon_server.py`](server/vitamon_server.py).

## Troubleshooting

**The Vita stays on "Waiting for data"**

1. Make sure the PC and the Vita are on the same network (for example, both on `192.168.1.x`).
2. Make sure your network is set to **Private** in Windows (*Settings → Network & Internet → Properties*).
3. Many routers block broadcast traffic, especially between WiFi and Ethernet or on guest networks. Type the IP shown on the Vita's waiting screen into **Vita IP**, then press **Stop** and **Start**.
4. If it still doesn't work, allow VitaMon through the firewall (PowerShell as administrator):

   ```powershell
   New-NetFirewallRule -DisplayName "VitaMon UDP" -Direction Outbound -Protocol UDP -RemotePort 10555 -Action Allow -Profile Private
   ```

**CPU temperature is `--`:** LibreHardwareMonitor isn't running, wasn't started as administrator, or its Remote Web Server is off.

**GPU is `--`:** not an NVIDIA GPU, or `nvidia-smi` doesn't work. Try running `nvidia-smi` in a terminal.

**"VitaMon is already open":** there is already a VitaMon window, maybe minimized in the taskbar. Only one can run at a time.

**Windows SmartScreen or antivirus warning:** the `.exe` is not code-signed, and Python apps packaged with PyInstaller sometimes trigger false positives. Click *More info → Run anyway*. The folder version (`VitaMon-windows.zip`) tends to get fewer false positives than the single `.exe`. You can also check the source and the [build log](https://github.com/MrWhite2312-IS/VitaPCMonitor/actions/workflows/build.yml), or [build it yourself](#build-the-windows-app) or [run it from source](#run-from-source).

## How it works

```
psutil ────────────────┐
nvidia-smi ────────────┼ ──► VitaMon.exe ──── UDP :10555, 1 line/s ───► VitaMon
LibreHardwareMonitor ──┘        (PC)                                    (PS Vita, C + vita2d)
```

The PC sends one plain-text line per second as a UDP broadcast (or to a single IP). The Vita listens on port 10555, parses the line and draws it with [vita2d](https://github.com/xerpi/libvita2d). To save battery, the app runs the Vita's CPU at 111 MHz.

<details>
<summary>Protocol (v1)</summary>

One ASCII line per datagram, under 1024 bytes:

```
VMON1;host=DESKTOP;cpun=Ryzen 5 5600G;gpun=RTX 3050;cpu=23.4;cores=12,30,...;ctemp=54.0;ram=55.1;ramu=8.8;ramt=16.0;gpu=12;gtemp=60;vramu=1.2;vramt=8.0;gclk=1500;up=123.4;down=456.7;disk=40.2;ts=1731258000
```

`-1` means "not available". The app ignores unknown keys and any datagram that doesn't start with `VMON1;`, so new fields can be added without breaking older versions.

</details>

## Building from source

```
server/   PC app (Python + psutil, tkinter window)
vita/     Vita homebrew app (C + VitaSDK + vita2d)
tools/    LiveArea asset generator
```

Every push builds both files on GitHub Actions. Pushing a `v*` tag publishes them as a release.

### Run from source

Requires Python 3.10+.

```bat
cd server
pip install -r requirements.txt
pythonw vitamon_gui.py
```

`vitamon_gui.py` accepts `--start` and `--minimized`. There is also a console version: `python vitamon_server.py --verbose` (options: `--port`, `--interval`, `--target VITA_IP`, `--lhm-url`, `--verbose`).

### Build the Windows app

From the `server` folder:

```bat
build_exe.bat
```

It creates a virtual environment in `server\.venv-build`, installs psutil, PyInstaller and Pillow, and writes `server\dist\VitaMon.exe` (a single file with no console) and `server\dist\VitaMon-windows.zip` (the same app as a folder).

### Build the Vita app

Install [VitaSDK](https://vitasdk.org/) (on macOS/Linux, `vdpm` is enough) with the `zlib libpng libjpeg-turbo libvita2d` packages, plus `cmake`:

```bash
export VITASDK=$HOME/vitasdk
export PATH=$VITASDK/bin:$PATH
git clone https://github.com/vitasdk/vdpm && cd vdpm
./bootstrap-vitasdk.sh
vdpm install zlib libpng libjpeg-turbo libvita2d
```

Then:

```bash
cd vita && mkdir build && cd build && cmake .. && make
```

This produces `vita/build/VitaMon.vpk`. Or use Docker: `docker run --rm -v "$PWD":/src -w /src/vita vitasdk/vitasdk sh -c "mkdir -p build && cd build && cmake .. && make"`.

LiveArea assets live in `vita/sce_sys/`. To regenerate them: `pip install pillow && python tools/make_assets.py`.

### Tests

```bash
# protocol parser
cd vita/tests && gcc -std=c11 -Wall -I../src ../src/protocol.c test_protocol.c -o test_protocol -lm && ./test_protocol
# translations: nothing missing, format specifiers match
cd vita/tests && gcc -std=c11 -Wall -I../src ../src/lang.c test_lang.c -o test_lang && ./test_lang
# a real server line through the C parser
cd server && python test_server_line.py
# see what the PC is sending (from another terminal or machine)
python server/test_listener.py
```

## Contributing

Issues and pull requests are welcome. Some good places to start:

- **New language or translation fixes:** the Vita strings are in [`vita/src/lang.c`](vita/src/lang.c) (add the language to the `Lang` enum in `lang.h`), and the PC strings are in [`server/i18n.py`](server/i18n.py). `test_lang` checks that nothing is missing. The Vita's built-in font covers Latin scripts (accents, ñ, ç, ß) but not Japanese, Chinese or Korean.
- **AMD / Intel GPU support** on the PC side.
- **Linux/macOS sender:** the console server already runs there (CPU temperature through psutil), but it hasn't been tested much.

## License

[MIT](LICENSE)
