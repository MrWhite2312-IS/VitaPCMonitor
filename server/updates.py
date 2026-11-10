"""Aviso de versión nueva: consulta los Releases públicos del repositorio en GitHub.

Solo envía una petición anónima a la API pública de GitHub (sin datos del usuario).
Si la versión instalada es beta, también avisa de betas nuevas; si es estable, solo de estables.
"""

import json
import re
import urllib.request

from version import APP_VERSION, REPO


def parse_version(tag):
    """'v1.2.0-beta.1' -> (1, 2, 0, 0, 1); '1.2.0' -> (1, 2, 0, 1, 0) (la estable va después de sus betas)."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)(?:-[A-Za-z]+\.?(\d+)?)?$", tag.strip())
    if not m:
        return None
    major, minor, patch, pre = m.groups()
    is_pre = "-" in tag
    return (int(major), int(minor), int(patch), 0 if is_pre else 1, int(pre or 0) if is_pre else 0)


def newest(releases, current=APP_VERSION):
    """(tag, url) del release más nuevo que la versión actual, o None."""
    cur = parse_version(current)
    if cur is None:
        return None
    want_pre = cur[3] == 0
    best = None
    for r in releases:
        if r.get("draft") or (r.get("prerelease") and not want_pre):
            continue
        v = parse_version(r.get("tag_name", ""))
        if v and v > cur and (best is None or v > best[0]):
            best = (v, r["tag_name"], r.get("html_url") or f"https://github.com/{REPO}/releases")
    return (best[1], best[2]) if best else None


def check(timeout=5):
    """Consulta GitHub; (tag, url) si hay una versión más nueva, None si no o si falla."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases?per_page=20",
        headers={"User-Agent": f"VitaMon/{APP_VERSION}", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return newest(json.load(resp))
    except (OSError, ValueError):
        return None
