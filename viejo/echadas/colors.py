"""Resolución de colores de Excel (rgb, indexados, tema, tint, lumMod/lumOff)."""
from __future__ import annotations

import colorsys
import xml.etree.ElementTree as ET
import zipfile

from openpyxl.styles.colors import COLOR_INDEX

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

# Orden de colores de tema según la especificación de Excel (índice -> nombre)
THEME_ORDER = ["lt1", "dk1", "lt2", "dk2", "accent1", "accent2", "accent3",
               "accent4", "accent5", "accent6", "hlink", "folHlink"]
SCHEME_ALIAS = {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"}

DEFAULT_THEME = {
    "dk1": "000000", "lt1": "FFFFFF", "dk2": "1F497D", "lt2": "EEECE1",
    "accent1": "4F81BD", "accent2": "C0504D", "accent3": "9BBB59",
    "accent4": "8064A2", "accent5": "4BACC6", "accent6": "F79646",
    "hlink": "0000FF", "folHlink": "800080",
}


def load_theme(xlsx_path) -> dict:
    theme = dict(DEFAULT_THEME)
    try:
        with zipfile.ZipFile(xlsx_path) as z:
            name = next((n for n in z.namelist() if n.startswith("xl/theme/") and n.endswith(".xml")), None)
            if not name:
                return theme
            root = ET.fromstring(z.read(name))
        scheme = root.find(f".//{A}clrScheme")
        if scheme is None:
            return theme
        for el in scheme:
            key = el.tag.replace(A, "")
            srgb = el.find(f"{A}srgbClr")
            sysc = el.find(f"{A}sysClr")
            if srgb is not None:
                theme[key] = srgb.get("val").upper()
            elif sysc is not None:
                theme[key] = (sysc.get("lastClr") or "000000").upper()
    except Exception:
        pass
    return theme


def _hex_to_rgb(h):
    h = h[-6:]
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _rgb_to_hex(r, g, b):
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(v * 255))) for v in (r, g, b))


def apply_tint(hex6: str, tint: float) -> str:
    """Tint de Excel (celdas): aplica sobre la luminosidad HLS."""
    r, g, b = _hex_to_rgb(hex6)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if tint < 0:
        l = l * (1 + tint)
    else:
        l = l * (1 - tint) + tint
    return _rgb_to_hex(*colorsys.hls_to_rgb(h, l, s))


def apply_lum(hex6: str, lum_mod: float | None, lum_off: float | None) -> str:
    r, g, b = _hex_to_rgb(hex6)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if lum_mod is not None:
        l *= lum_mod
    if lum_off is not None:
        l += lum_off
    l = max(0.0, min(1.0, l))
    return _rgb_to_hex(*colorsys.hls_to_rgb(h, l, s))


def openpyxl_color(color, theme: dict, *, is_fill: bool) -> str | None:
    """Convierte un openpyxl Color a '#RRGGBB'. None = sin color / automático."""
    if color is None:
        return None
    try:
        t = color.type
        if t == "rgb":
            v = color.rgb
            if not isinstance(v, str) or v in ("00000000",):
                return None
            base = v[-6:]
        elif t == "indexed":
            idx = color.indexed
            if idx in (64, 65) or idx is None:  # automático / fondo de sistema
                return None
            if idx >= len(COLOR_INDEX):
                return None
            base = COLOR_INDEX[idx][-6:]
        elif t == "theme":
            idx = color.theme
            if idx is None or idx >= len(THEME_ORDER):
                return None
            base = theme.get(THEME_ORDER[idx], "000000")
        else:
            return None
        tint = color.tint or 0
        if tint:
            return apply_tint(base, tint)
        return "#" + base.upper()
    except Exception:
        return None


def drawingml_color(parent, theme: dict) -> str | None:
    """Lee el primer hijo de color DrawingML (srgbClr, schemeClr, sysClr, prstClr)."""
    if parent is None:
        return None
    for el in parent:
        tag = el.tag.replace(A, "")
        base = None
        if tag == "srgbClr":
            base = el.get("val")
        elif tag == "schemeClr":
            key = SCHEME_ALIAS.get(el.get("val"), el.get("val"))
            base = theme.get(key, "000000")
        elif tag == "sysClr":
            base = el.get("lastClr") or ("FFFFFF" if el.get("val") == "window" else "000000")
        elif tag == "prstClr":
            base = {"black": "000000", "white": "FFFFFF", "red": "FF0000",
                    "blue": "0000FF", "green": "00FF00", "yellow": "FFFF00"}.get(el.get("val"), "000000")
        if base is None:
            continue
        mod = el.find(f"{A}lumMod")
        off = el.find(f"{A}lumOff")
        lm = int(mod.get("val")) / 100000 if mod is not None else None
        lo = int(off.get("val")) / 100000 if off is not None else None
        if lm is not None or lo is not None:
            return apply_lum(base, lm, lo)
        return "#" + base.upper()
    return None
