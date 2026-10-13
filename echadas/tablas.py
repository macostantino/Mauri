"""Tablas derivadas de una echada generada (composición y posiciones)."""
from __future__ import annotations

from .generador import BOBINAS, Echada, pos_info

ABBR = {"Óvalo": "O", "Triángulo": "T", "Rect. redondeado": "R", "Heptágono": "H", "Hexágono": "X",
        "Rombo": "D", "Pentágono": "P", "Octógono": "G"}


def composicion(ech: Echada) -> list[dict]:
    filas = []
    for ci, c in enumerate(ech.cuerpos):
        reparto = []
        for t in ech.tiradas:
            hojas = [h for (_, _, cc, h) in t.hojas if cc == ci]
            if hojas:
                reparto.append(f"T{t.numero}: {len(hojas) * 4} págs. (hojas {min(hojas) + 1}-{max(hojas) + 1})"
                               if len(hojas) > 1 else f"T{t.numero}: 4 págs. (hoja {hojas[0] + 1})")
        filas.append({"#": ci + 1, "Cuerpo": c.nombre, "Figura": c.figura, "Págs.": c.paginas,
                      "Reparto en tiradas": " · ".join(reparto)})
    return filas


COLORES = 4  # Full Color (CMYK): una chapa por color


def chapas_tirada(ech: Echada, t, repite_8: bool = True) -> int:
    """Chapas por color de una tirada: cada cuadrante (ALTO/BAJO) de cada cara de cada pliego que lleve al
    menos una página es una chapa de 4 págs. Con REPITE (tirada de 8) se montan también las de ALTO."""
    cuadrantes = {(p.web, p.cara, pos_info(p.cara, p.col)[0]) for p in ech.colocaciones if p.tirada == t.numero}
    if repite_8 and t.puede_repetir:
        cuadrantes |= {(w, c, "ALTO") for (w, c, _) in cuadrantes}
    return len(cuadrantes)


def chapas(ech: Echada, repite_8: bool = True) -> list[tuple[int, int]]:
    """[(chapas por color, chapas totales)] por tirada."""
    return [(n, n * COLORES) for n in (chapas_tirada(ech, t, repite_8) for t in ech.tiradas)]


def texto_chapas(ech: Echada, repite_8: bool = True) -> str:
    ch = chapas(ech, repite_8)
    total = sum(x[1] for x in ch)
    det = " · ".join(f"Tirada {i}: {x[1]}" for i, x in enumerate(ch, 1))
    return f"{total}: {det}"


def resumen(ech: Echada, repite_8: bool = True) -> list[tuple[str, str]]:
    return [
        ("Total de páginas", str(ech.total)),
        ("Combinación de cuerpos", ech.config),
        ("Tiradas", " | ".join(f"{t.paginas}" for t in ech.tiradas) + f"  ({len(ech.tiradas)})"),
        ("Pliegos (webs)", str(sum(len(t.webs) for t in ech.tiradas))),
        ("Hojas de 4 págs.", str(ech.total // 4)),
        ("Chapas", texto_chapas(ech, repite_8)),
        ("Bobinas", ech.descripcion_bobinas),
    ]


def posiciones(ech: Echada) -> list[dict]:
    filas = []
    for p in sorted(ech.colocaciones, key=lambda p: (p.tirada, p.web, p.cara, -p.col, p.fila)):
        header, lado_pos = pos_info(p.cara, p.col)
        c = ech.cuerpos[p.cuerpo]
        filas.append({
            "Tirada": p.tirada, "Web": p.web, "Lado": "LADO " + p.cara[1:], "Cuadrante": header,
            "Posición": lado_pos, "Columna": p.col, "Fila": "Superior" if p.fila == "top" else "Inferior",
            "Cuerpo": c.nombre, "Figura": c.figura, "Página": p.pagina, "Hoja del cuerpo": p.hoja + 1,
        })
    return filas


def grilla(ech: Echada, tirada, web) -> tuple[list[str], list[list[str]]]:
    """Tabla compacta de un pliego: columnas en orden de dibujo; filas superior/inferior."""
    t = ech.tiradas[tirada - 1]
    orden = []
    for cara in ("L10", "L13"):
        cols = (0, 1, 2, 3) if cara == "L10" else (3, 2, 1, 0)
        if t.medio_formato:
            cols = (2, 3) if cara == "L10" else (3, 2)
        orden += [(cara, c) for c in cols]
    headers = []
    for cara, col in orden:
        h, pos = pos_info(cara, col)
        headers.append(f"L{cara[1:]} {h} {pos}")
    rows = []
    for fila in ("top", "bot"):
        r = []
        for cara, col in orden:
            p = ech.en(tirada, web, cara, col, fila)
            if p is None:
                r.append("")
                continue
            c = ech.cuerpos[p.cuerpo]
            r.append(f"{p.pagina}" + (f" [{ABBR.get(c.figura, '?')}]" if c.figura in ABBR else ""))
        rows.append(r)
    return headers, rows
