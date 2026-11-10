"""FPS del juego en primer plano, leídos de RivaTuner Statistics Server (RTSS).

RTSS (viene con MSI Afterburner, o se instala solo) mide los FPS de cualquier juego, de cualquier
marca de GPU, y los publica en una memoria compartida ("RTSSSharedMemoryV2") que cualquier
programa puede leer sin permisos de administrador. Sin RTSS abierto, no hay FPS (devuelve None).

Formato (RTSSSharedMemory.h del SDK de RTSS):
  cabecera: dwSignature ('RTSS'), dwVersion, dwAppEntrySize, dwAppArrOffset, dwAppArrSize, ...
  entrada por aplicación: dwProcessID, szName[260], dwFlags, dwTime0, dwTime1, dwFrames, ...
  FPS = 1000 * dwFrames / (dwTime1 - dwTime0)
"""

import struct
import sys

MAP_NAME = "RTSSSharedMemoryV2"
SIGNATURE = 0x52545353  # 'RTSS'
HEADER = struct.Struct("<5I")  # signature, version, app entry size, app array offset, app array size
ENTRY_PID = struct.Struct("<I")
ENTRY_TIMES = struct.Struct("<4I")  # time0, time1, frames, frame time (tras pid + name[260] + flags)
TIMES_OFFSET = 4 + 260 + 4


def parse(buf, pid):
    """FPS de la aplicación con ese pid en una copia de la memoria de RTSS; None si no está."""
    if len(buf) < HEADER.size:
        return None
    sig, version, entry_size, arr_offset, arr_size = HEADER.unpack_from(buf, 0)
    if sig != SIGNATURE or version < 0x00020000 or entry_size < TIMES_OFFSET + ENTRY_TIMES.size:
        return None
    for i in range(arr_size):
        off = arr_offset + i * entry_size
        if off + entry_size > len(buf):
            break
        if ENTRY_PID.unpack_from(buf, off)[0] != pid:
            continue
        time0, time1, frames, _ = ENTRY_TIMES.unpack_from(buf, off + TIMES_OFFSET)
        if time0 and time1 > time0 and frames:
            return 1000.0 * frames / (time1 - time0)
        return None
    return None


def foreground_pid():
    """PID de la ventana activa (el juego que se está jugando)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32")
    user32.GetForegroundWindow.restype = wintypes.HWND
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value or None


def _read_shared_memory():
    """Copia de la memoria compartida de RTSS, o None si RTSS no está abierto."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenFileMappingW.restype = wintypes.HANDLE
    k32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k32.MapViewOfFile.restype = ctypes.c_void_p
    k32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
    k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    FILE_MAP_READ = 4
    handle = k32.OpenFileMappingW(FILE_MAP_READ, False, MAP_NAME)  # no la crea si no existe
    if not handle:
        return None
    try:
        view = k32.MapViewOfFile(handle, FILE_MAP_READ, 0, 0, 0)
        if not view:
            return None
        try:
            head = ctypes.string_at(view, HEADER.size)
            sig, _, entry_size, arr_offset, arr_size = HEADER.unpack(head)
            if sig != SIGNATURE:
                return None
            return ctypes.string_at(view, arr_offset + arr_size * entry_size)
        finally:
            k32.UnmapViewOfFile(view)
    finally:
        k32.CloseHandle(handle)


def read_fps():
    """FPS del juego en primer plano según RTSS; None si RTSS no está abierto o no hay juego."""
    if sys.platform != "win32":
        return None
    try:
        pid = foreground_pid()
        buf = _read_shared_memory() if pid else None
        return parse(buf, pid) if buf else None
    except (OSError, ValueError, struct.error):
        return None


def rtss_running():
    if sys.platform != "win32":
        return False
    try:
        return _read_shared_memory() is not None
    except (OSError, ValueError, struct.error):
        return False
