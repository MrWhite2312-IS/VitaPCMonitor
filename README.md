# VitaMon: monitor de PC en la PS Vita

El PC (Windows) manda sus métricas por UDP broadcast una vez por segundo, y la Vita las muestra a pantalla completa: CPU, GPU, temperaturas, RAM, red y disco.

```
server/   servidor del PC (Python + psutil)
vita/     app homebrew (C + VitaSDK + vita2d)
tools/    generador de los assets de LiveArea
```

## 1. Compilar la app de la Vita (macOS / Linux)

### Instalar VitaSDK con vdpm

```bash
export VITASDK=$HOME/vitasdk
export PATH=$VITASDK/bin:$PATH
git clone https://github.com/vitasdk/vdpm
cd vdpm
./bootstrap-vitasdk.sh
vdpm install zlib libpng libjpeg-turbo libvita2d
```

Con `VITASDK` en tu carpeta personal no hace falta sudo (el default `/usr/local/vitasdk` sí lo pide). Solo se instalan los paquetes que usa VitaMon. El `install-all.sh` del repo instala más de 100 y falla con el cliente pacman nuevo de vdpm. Agrega los dos `export` a tu `~/.zshrc` o `~/.bashrc`. También necesitas `cmake` (en macOS: `brew install cmake`).

### Compilar

```bash
cd vita && mkdir build && cd build && cmake .. && make
```

Eso produce `vita/build/VitaMon.vpk`.

### Instalar en la Vita

1. Abre **VitaShell** en la Vita (requiere HENkaku/Ensō).
2. Pasa el VPK:
   - **FTP:** pulsa SELECT en VitaShell, y conéctate desde el PC a la dirección `ftp://IP:1337` que aparece en pantalla. Copia el VPK a `ux0:data/`.
   - **USB:** pulsa START → *USB connection*, y copia el VPK a la unidad que aparece.
3. En VitaShell, ve al VPK, pulsa X e instala.

### Assets de LiveArea

Ya están en `vita/sce_sys/`. Para regenerarlos: `pip install pillow && python tools/make_assets.py` (salen como PNG 8-bit indexados, que es lo que acepta la Vita).

## 2. Servidor en el PC (Windows)

Requiere Python 3.10+.

```bat
cd server
pip install -r requirements.txt
python vitamon_server.py --verbose
```

Al arrancar muestra el puerto, el modo (broadcast o unicast) y qué fuentes encontró (psutil, nvidia-smi, LHM).

Opciones: `--port 10555`, `--interval 1.0`, `--target IP_VITA`, `--lhm-url http://localhost:8085/data.json`, `--verbose`.

`run_vitamon.bat` lo inicia con doble clic (si existe `server\.venv`, lo activa primero).

### Firewall de Windows

La primera vez, Windows pregunta si permite Python: marca **Redes privadas**. Si no preguntó, crea una regla de salida desde PowerShell como administrador:

```powershell
New-NetFirewallRule -DisplayName "VitaMon UDP" -Direction Outbound -Protocol UDP -RemotePort 10555 -Action Allow -Profile Private
```

Asegúrate de que tu red WiFi/Ethernet esté marcada como **Privada**.

### Temperatura de la CPU: LibreHardwareMonitor

psutil no lee temperaturas en Windows, así que se usan las de [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor):

1. Ejecuta LibreHardwareMonitor **como administrador**.
2. Activa *Options → Remote Web Server → Run* (puerto 8085).
3. Comprueba que `http://localhost:8085/data.json` abre en el navegador.

Sin esto, la temperatura de la CPU aparece como `--`.

### GPU NVIDIA

Se lee con `nvidia-smi`, que viene con el driver. Si no está en el PATH, la GPU aparece como `--` (el servidor lo reintenta cada 30 s).

### Arrancar con Windows

- **Lo simple:** pulsa Win+R, escribe `shell:startup` y crea ahí un acceso directo a `server\run_vitamon.bat`.
- **Sin ventana / antes de iniciar sesión:** Programador de tareas → *Crear tarea básica* → desencadenador *Al iniciar sesión* → acción *Iniciar un programa*: `pythonw.exe`, argumentos `vitamon_server.py`, *Iniciar en*: la carpeta `server`.

## 3. Uso en la Vita

| Botón | Acción |
|-------|--------|
| START | Salir |
| □ | Vista compacta (CPU %, CPU °C, GPU %, GPU °C en grande) |
| △ | Overlay de debug (última línea recibida, paquetes/s, IP de origen) |

Estados: **Esperando** (no llegó nada aún; muestra la IP de la Vita), **Conectado**, **Sin señal** (más de 3 s sin datos; muestra los últimos valores atenuados).

## 4. Pruebas sin la Vita

```bash
# test del parser C en el host
cd vita/tests && gcc -std=c11 -Wall -I../src ../src/protocol.c test_protocol.c -o test_protocol -lm && ./test_protocol

# una línea real del servidor pasada por el parser C
cd server && python test_server_line.py

# ver lo que manda el servidor (en otra terminal u otra máquina)
python server/test_listener.py
```

## 5. Troubleshooting

- **"Esperando datos" para siempre:**
  - Corre `test_listener.py` en otra máquina de la misma red. Si tampoco recibe, es el firewall o la red.
  - Revisa que el PC y la Vita estén en la misma subred (por ejemplo, ambos en `192.168.1.x`).
  - Algunos routers bloquean broadcast (aislamiento de AP). Usa unicast: `python vitamon_server.py --target IP_VITA` (la IP sale en la pantalla de espera).
- **Temperatura de CPU en `--`:** LibreHardwareMonitor no está corriendo, no se abrió como admin, o el Remote Web Server está apagado.
- **GPU en `--`:** `nvidia-smi` no está en el PATH. Prueba `nvidia-smi` en una terminal.

## Protocolo (v1)

Una línea ASCII por datagrama, menor a 1024 bytes:

```
VMON1;host=DESKTOP-PC;cpu=23.4;cores=12,30,...;ctemp=54.0;ram=55.1;ramu=8.8;ramt=16.0;gpu=12;gtemp=60;vramu=1.2;vramt=8.0;gclk=1500;up=123.4;down=456.7;disk=40.2;ts=1731258000
```

`-1` significa "no disponible". La app ignora claves desconocidas y cualquier datagrama que no empiece con `VMON1;`.
