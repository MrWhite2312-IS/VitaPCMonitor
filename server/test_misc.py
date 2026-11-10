#!/usr/bin/env python3
"""Tests sin hardware: FPS de RivaTuner, aviso de actualizaciones y respuesta de la Vita."""

import struct

import fps
import updates
import vitamon_server as vs


def rtss_buffer(entries, version=0x00020013, entry_size=0x1000, offset=0x100):
    buf = bytearray(offset + entry_size * len(entries))
    struct.pack_into("<5I", buf, 0, fps.SIGNATURE, version, entry_size, offset, len(entries))
    for i, (pid, t0, t1, frames) in enumerate(entries):
        off = offset + i * entry_size
        struct.pack_into("<I", buf, off, pid)
        struct.pack_into("<4I", buf, off + fps.TIMES_OFFSET, t0, t1, frames, 0)
    return bytes(buf)


def test_rtss_fps_of_foreground_app():
    buf = rtss_buffer([(100, 1000, 2000, 30), (200, 5000, 5500, 72)])
    assert fps.parse(buf, 200) == 144.0   # 72 frames en 500 ms
    assert fps.parse(buf, 100) == 30.0
    assert fps.parse(buf, 300) is None    # la ventana activa no es un juego


def test_rtss_invalid_data():
    assert fps.parse(b"", 1) is None
    assert fps.parse(rtss_buffer([(1, 0, 0, 0)]), 1) is None            # sin muestras todavía
    assert fps.parse(rtss_buffer([(1, 10, 20, 5)], version=0x00010000), 1) is None
    bad = bytearray(rtss_buffer([(1, 10, 20, 5)]))
    bad[0] = 0
    assert fps.parse(bytes(bad), 1) is None                              # firma incorrecta


def test_version_order():
    p = updates.parse_version
    assert p("v1.2.0-beta.1") < p("v1.2.0-beta.2") < p("v1.2.0") < p("v1.3.0-beta.1") < p("1.10.0")
    assert p("no-es-version") is None


def test_newest_release():
    rel = lambda tag, pre: {"tag_name": tag, "prerelease": pre, "html_url": f"https://x/{tag}"}
    releases = [rel("v1.2.0-beta.1", True), rel("v1.3.0-beta.1", True), rel("v1.1.0", False),
                {"tag_name": "v9.0.0", "draft": True, "prerelease": False}]
    assert updates.newest(releases, "1.2.0-beta.1") == ("v1.3.0-beta.1", "https://x/v1.3.0-beta.1")
    assert updates.newest(releases, "1.3.0-beta.1") is None
    assert updates.newest(releases, "1.0.0") == ("v1.1.0", "https://x/v1.1.0")  # estable: sin betas


def test_vita_ack():
    a = vs.parse_ack(b"VMONACK1;ver=1.3;batt=80;chg=1", "192.168.1.50")
    assert (a["ip"], a["ver"], a["batt"], a["chg"]) == ("192.168.1.50", "1.3", 80, True)
    b = vs.parse_ack(b"VMONACK1;ver=1.3;batt=-1;chg=0", "10.0.0.2")  # PS TV: sin batería
    assert b["batt"] == -1 and b["chg"] is False
    assert vs.parse_ack(b"VMON1;cpu=1", "1.2.3.4") is None
    assert vs.parse_ack(b"\xff\xfe", "1.2.3.4") is None


def test_fps_in_protocol_line():
    sample = {"host": "PC", "cpu": 1, "cores": [1], "ctemp": -1, "ram": 1, "ramu": 1, "ramt": 2,
              "gpu": 1, "gtemp": -1, "vramu": -1, "vramt": -1, "gclk": -1, "up": 0, "down": 0,
              "disk": 0, "ts": 0, "fps": 143.6}
    assert ";fps=143.6;" in vs.build_line(sample)
    sample["fps"] = -1
    assert ";fps=-1;" in vs.build_line(sample)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK: {len(tests)} tests (FPS, actualizaciones, respuesta de la Vita)")
