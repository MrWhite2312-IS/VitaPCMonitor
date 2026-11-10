"""Lectores de GPU para AMD Radeon, Intel (y NVIDIA sin nvidia-smi).

Dos fuentes, de mejor a peor:
  1. LibreHardwareMonitor (el mismo web server que da la temperatura del CPU):
     carga, temperatura, reloj y VRAM de cualquier marca.
  2. Windows (sin instalar nada): contadores de rendimiento "GPU Engine" y "GPU Adapter Memory",
     los mismos del Administrador de tareas, más DXGI para el nombre y la VRAM total.
     Da carga y VRAM, pero no temperatura ni reloj.

Todas las funciones devuelven dicts con las claves del protocolo (gpu, gtemp, vramu, vramt, gclk)
y -1 donde no hay dato; vramu/vramt en GB.
"""

import re
import sys

NA = -1


# ---------- LibreHardwareMonitor ----------

def parse_value(value):
    """'1359.0 MB' -> (1359.0, 'MB'); '54,5 °C' -> (54.5, '°C'); (None, '') si no hay número."""
    m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*(\S*)", value or "")
    if not m:
        return None, ""
    return float(m.group(1).replace(",", ".")), m.group(2)


def _to_gb(value):
    num, unit = parse_value(value)
    if num is None or num < 0:
        return NA
    return {"KB": num / 2**20, "MB": num / 1024, "GB": num, "TB": num * 1024}.get(unit.upper(), num / 1024)


def _sensors(node):
    """{('Load', 'GPU Core'): '31.0 %', ...} de un nodo de hardware de LHM."""
    out = {}
    for group in node.get("Children", []):
        for s in group.get("Children", []):
            out[(group.get("Text"), s.get("Text"))] = s.get("Value")
    return out


def _is_gpu(sensors):
    loads = {name for (group, name) in sensors if group == "Load"}
    return bool(loads & {"GPU Core", "D3D 3D"}) and "CPU Total" not in loads


def _first(sensors, group, names):
    for name in names:
        value = sensors.get((group, name))
        if value is not None:
            num, _ = parse_value(value)
            if num is not None and num >= 0:
                return num
    return None


def lhm_gpus(tree):
    """Todas las GPU del árbol de LHM: lista de dicts con 'name', 'vram_total_gb' y las claves del protocolo."""
    found = []

    def walk(node):
        sensors = _sensors(node)
        if _is_gpu(sensors):
            used = (sensors.get(("Data", "GPU Memory Used")) or sensors.get(("SmallData", "GPU Memory Used"))
                    or sensors.get(("Data", "D3D Dedicated Memory Used")))
            total = (sensors.get(("Data", "GPU Memory Total")) or sensors.get(("SmallData", "GPU Memory Total"))
                     or sensors.get(("Data", "D3D Dedicated Memory Total")))
            if used is None:  # Intel integrada: solo memoria compartida
                used = sensors.get(("Data", "D3D Shared Memory Used"))
            load = _first(sensors, "Load", ["GPU Core", "D3D 3D"])
            temp = _first(sensors, "Temperatures", ["GPU Core", "GPU Hot Spot", "GPU Package", "GPU"])
            clock = _first(sensors, "Clocks", ["GPU Core"])
            found.append({
                "name": node.get("Text", ""),
                "vram_total_gb": _to_gb(total) if total else NA,
                "gpu": load if load is not None else NA,
                "gtemp": temp if temp is not None else NA,
                "gclk": clock if clock is not None else NA,
                "vramu": _to_gb(used) if used else NA,
                "vramt": _to_gb(total) if total else NA,
            })
            return
        for child in node.get("Children", []):
            walk(child)

    walk(tree or {})
    return found


def pick_gpu(gpus):
    """La GPU principal: la de más VRAM dedicada (la tarjeta de video, no la integrada)."""
    return max(gpus, key=lambda g: g.get("vram_total_gb", NA), default=None)


# ---------- Windows: DXGI + contadores de rendimiento (PDH) ----------

def dxgi_adapters():
    """[(nombre, luid '0xHHHHHHHH_0xLLLLLLLL', VRAM dedicada en bytes)] sin adaptadores por software."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class DESC1(ctypes.Structure):
        _fields_ = [("Description", wintypes.WCHAR * 128), ("VendorId", wintypes.UINT),
                    ("DeviceId", wintypes.UINT), ("SubSysId", wintypes.UINT), ("Revision", wintypes.UINT),
                    ("DedicatedVideoMemory", ctypes.c_size_t), ("DedicatedSystemMemory", ctypes.c_size_t),
                    ("SharedSystemMemory", ctypes.c_size_t), ("AdapterLuid", LUID), ("Flags", wintypes.UINT)]

    class GUID(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    # IID_IDXGIFactory1 = 770aae78-f26f-4dba-a829-253c83d1b387
    iid = GUID(0x770AAE78, 0xF26F, 0x4DBA, (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))

    def method(obj, index, restype, *argtypes):
        vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[index])

    adapters = []
    try:
        dxgi = ctypes.WinDLL("dxgi")
        factory = ctypes.c_void_p()
        if dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory)) != 0:
            return []
        enum_adapters1 = method(factory, 12, ctypes.c_long, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))
        i = 0
        while True:
            adapter = ctypes.c_void_p()
            if enum_adapters1(factory, i, ctypes.byref(adapter)) != 0:  # DXGI_ERROR_NOT_FOUND: no hay más
                break
            desc = DESC1()
            if method(adapter, 10, ctypes.c_long, ctypes.POINTER(DESC1))(adapter, ctypes.byref(desc)) == 0:
                if not desc.Flags & 2:  # DXGI_ADAPTER_FLAG_SOFTWARE ("Microsoft Basic Render Driver")
                    luid = f"0x{desc.AdapterLuid.HighPart & 0xFFFFFFFF:08X}_0x{desc.AdapterLuid.LowPart:08X}"
                    adapters.append((desc.Description, luid, desc.DedicatedVideoMemory))
            method(adapter, 2, wintypes.ULONG)(adapter)  # Release
            i += 1
        method(factory, 2, wintypes.ULONG)(factory)
    except (OSError, AttributeError, ValueError):
        return adapters
    return adapters


class WindowsGpu:
    """Carga y VRAM usada de la GPU principal con los contadores del Administrador de tareas."""

    PDH_FMT_DOUBLE = 0x200
    PDH_MORE_DATA = 0x800007D2

    def __init__(self):
        self.ok = False
        self.name = ""
        self.luid = None
        self.vram_total = NA
        if sys.platform != "win32":
            return
        adapters = dxgi_adapters()
        if adapters:
            self.name, self.luid, total = max(adapters, key=lambda a: a[2])
            self.vram_total = total / 2**30 if total else NA
        import ctypes
        from ctypes import wintypes
        self._ct, self._wt = ctypes, wintypes
        try:
            self.pdh = ctypes.WinDLL("pdh")
        except OSError:
            return
        self.query = wintypes.HANDLE()
        self.c_load, self.c_mem = wintypes.HANDLE(), wintypes.HANDLE()
        if self.pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.query)) != 0:
            return
        add = self.pdh.PdhAddEnglishCounterW
        if add(self.query, r"\GPU Engine(*)\Utilization Percentage", 0, ctypes.byref(self.c_load)) != 0:
            return
        add(self.query, r"\GPU Adapter Memory(*)\Dedicated Usage", 0, ctypes.byref(self.c_mem))
        self.pdh.PdhCollectQueryData(self.query)  # la primera lectura de un contador de % siempre es 0
        self.ok = True

    def _array(self, counter):
        ct, wt = self._ct, self._wt

        class FMT(ct.Structure):
            _fields_ = [("CStatus", wt.DWORD), ("value", ct.c_double)]

        class ITEM(ct.Structure):
            _fields_ = [("name", wt.LPWSTR), ("fmt", FMT)]

        size, count = wt.DWORD(0), wt.DWORD(0)
        r = self.pdh.PdhGetFormattedCounterArrayW(counter, self.PDH_FMT_DOUBLE, ct.byref(size), ct.byref(count), None)
        if r & 0xFFFFFFFF != self.PDH_MORE_DATA:
            return {}
        buf = (ct.c_byte * size.value)()
        if self.pdh.PdhGetFormattedCounterArrayW(counter, self.PDH_FMT_DOUBLE, ct.byref(size), ct.byref(count), buf):
            return {}
        items = ct.cast(buf, ct.POINTER(ITEM))
        return {items[i].name: items[i].fmt.value for i in range(count.value)}

    @staticmethod
    def _luid(instance):
        m = re.search(r"luid_(0x[0-9A-Fa-f]+_0x[0-9A-Fa-f]+)", instance)
        return m.group(1).upper().replace("0X", "0x") if m else None

    def sample(self):
        if not self.ok:
            return None
        if self.pdh.PdhCollectQueryData(self.query) != 0:
            return None
        # Igual que el Administrador de tareas: se suma cada tipo de motor (3D, Compute, VideoDecode...)
        # de todos los procesos, y la carga de la GPU es la del tipo más ocupado.
        per_engine, load, mem = {}, {}, {}
        for inst, v in self._array(self.c_load).items():
            m = re.search(r"engtype_(.+)$", inst)
            key = (self._luid(inst), m.group(1) if m else "")
            per_engine[key] = per_engine.get(key, 0.0) + v
        for (luid, _), v in per_engine.items():
            load[luid] = max(load.get(luid, 0.0), v)
        for inst, v in self._array(self.c_mem).items():
            mem[self._luid(inst)] = v
        luid = self.luid if self.luid in load or self.luid in mem else max(mem, key=mem.get, default=None)
        if luid is None:
            return None
        used = mem.get(luid)
        return {
            "gpu": min(100.0, load.get(luid, 0.0)),
            "gtemp": NA,
            "gclk": NA,
            "vramu": used / 2**30 if used is not None else NA,
            "vramt": self.vram_total,
        }
