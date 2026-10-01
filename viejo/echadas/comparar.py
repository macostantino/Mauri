"""
Comparación de una echada GENERADA contra la plantilla del Excel de referencia.

El Excel solo se usa aquí, como control. Se compara posición por posición
(tirada, web F/A, LADO 10/13, columna, fila) la página y el cuerpo al que pertenece.
Las figuras del Excel (óvalo, triángulo...) identifican cuerpos; como el símbolo elegido
para cada suple varía entre hojas, se busca la correspondencia figura↔cuerpo y se informa.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .generador import Cuerpo, Echada, generar

COL_L10 = {("ALTO", "Izq"): 0, ("ALTO", "Der"): 1, ("BAJO", "Izq"): 2, ("BAJO", "Der"): 3}
COL_L13 = {("BAJO", "Izq"): 3, ("BAJO", "Der"): 2, ("ALTO", "Izq"): 1, ("ALTO", "Der"): 0}


def _ints(s) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", str(s or ""))]


def cuerpos_de_indice(entry) -> list[int]:
    """Lista de cuerpos de una fila del índice (en el orden de la echada)."""
    if entry.kind == "variante":
        return _ints(entry.config)
    tapa = int(float(entry.tapa_pags))
    conf = _ints(entry.tapa_conf)
    suples = _ints(entry.suples)
    prefijo = []
    if sum(conf) > tapa:  # p. ej. '4+28+8' con tapa 36: el 4 es un cuerpo previo
        for k in range(1, len(conf)):
            if sum(conf[k:]) == tapa:
                prefijo = conf[:k]
                break
    return prefijo + [tapa] + suples


def tiradas_de_indice(entry) -> list[int] | None:
    if entry.kind == "variante":
        return None
    return [sum(_ints(t)) for t in entry.tiradas]


@dataclass
class Resultado:
    identica: bool
    posiciones: int
    coinciden: int
    diferencias: list = field(default_factory=list)   # dicts
    mapeo: dict = field(default_factory=dict)          # figura Excel -> nombre cuerpo generado
    notas: list = field(default_factory=list)

    @property
    def porcentaje(self):
        return 100.0 * self.coinciden / self.posiciones if self.posiciones else 0.0


def extraer_plantilla(sel) -> dict:
    """Posición -> lista de candidatos (figura, página) según la hoja del Excel."""
    sm = sel.sheet
    n_bands = len(sel.bands)
    out = {}
    for bi, band in enumerate(sel.bands):
        tirada = (n_bands - bi) if sel.entry.kind == "tiradas" else 1
        for blk_i in band.blocks:
            blk = sm.blocks[blk_i]
            for sl in blk.slots:
                web = sl.mark or ("F" if blk_i == band.blocks[0] else "A")
                cara = "L10" if sl.lado.endswith("10") else "L13"
                col = (COL_L10 if cara == "L10" else COL_L13)[(sl.header, sl.lado_pos)]
                fila = "top" if sl.fila == "Superior" else "bot"
                cands = []
                for i in sl.shapes:
                    s = sm.shapes[i]
                    nums = re.findall(r"\d+", s.clean_text)
                    if nums and len(set(nums)) == 1 and re.fullmatch(r"[\d\s]+", s.clean_text):
                        cands.append((s.label, int(nums[0])))
                if not cands and sl.page not in (None, ""):
                    try:
                        cands.append(("Sin figura", int(float(sl.page))))
                    except (TypeError, ValueError):
                        pass
                if cands:
                    out[(tirada, web, cara, col, fila)] = cands
    return out


def comparar(ech: Echada, plantilla: dict) -> Resultado:
    gen = {(p.tirada, p.web, p.cara, p.col, p.fila): p for p in ech.colocaciones}
    # correspondencia figura -> cuerpo, POR TIRADA (las planillas reutilizan símbolos entre tiradas)
    votos = defaultdict(Counter)
    for pos, cands in plantilla.items():
        g = gen.get(pos)
        if g is None:
            continue
        for fig, pag in cands:
            if pag == g.pagina:
                votos[(pos[0], fig)][g.cuerpo] += 1
    # cada (tirada, figura) puede agrupar uno o más cuerpos (hay hojas que repiten un símbolo),
    # pero cada cuerpo generado pertenece a una sola figura dentro de la tirada
    mapeo = defaultdict(set)
    asignado = {}
    for (t, fig), cnt in sorted(votos.items(), key=lambda kv: -sum(kv[1].values())):
        for cuerpo, n in cnt.most_common():
            if (t, cuerpo) not in asignado and n >= 2:
                mapeo[(t, fig)].add(cuerpo)
                asignado[(t, cuerpo)] = fig

    # tiradas de 8 págs. "repetidas": la planilla puede duplicar columnas 2-3 en 0-1
    formato = {t.numero: t.formato for t in ech.tiradas}

    def repeticion(pos):
        t, w, cara, col, fila = pos
        if formato.get(t) != 8 or col not in (0, 1):
            return None
        return gen.get((t, w, cara, col + 2, fila))

    difs, ok = [], 0
    todas = sorted(set(gen) | set(plantilla))
    for pos in todas:
        g, cands = gen.get(pos), plantilla.get(pos)
        t = pos[0]
        nota = ""
        if g is None and cands:
            g = repeticion(pos)
            nota = " (repite)" if g else ""
        esperado = None
        if cands:
            esperado = next(((f, p) for f, p in cands
                             if g and g.cuerpo in mapeo.get((t, f), ()) and p == g.pagina), cands[0])
        match = (g is not None and esperado is not None and g.cuerpo in mapeo.get((t, esperado[0]), ())
                 and esperado[1] == g.pagina)
        if match:
            ok += 1
        else:
            _, w, cara, col, fila = pos
            difs.append({
                "Tirada": t, "Web": w, "Lado": "LADO " + cara[1:], "Columna": col,
                "Fila": "Superior" if fila == "top" else "Inferior",
                "Generada": f"{ech.cuerpos[g.cuerpo].nombre} p.{g.pagina}{nota}" if g else "(vacía)",
                "Excel": f"{esperado[0]} p.{esperado[1]}" if esperado else "(vacía)",
            })
    nombres = {f"Tirada {t} · {fig}": " + ".join(ech.cuerpos[c].nombre for c in sorted(cs))
               for (t, fig), cs in sorted(mapeo.items())}
    res = Resultado(identica=not difs, posiciones=len(todas), coinciden=ok, diferencias=difs, mapeo=nombres)
    return res


def comparar_entrada(lib, entry, cuerpos: list[Cuerpo] | None = None):
    """Genera la echada de una fila del índice y la compara con su plantilla."""
    from .report import select
    ech = generar(cuerpos or cuerpos_de_indice(entry), tiradas_de_indice(entry))
    sel = select(lib, entry)
    return ech, sel, comparar(ech, extraer_plantilla(sel))


def buscar_en_indice(lib, config: list[int]):
    """Filas del índice cuya lista de cuerpos coincide exactamente con la configuración."""
    out = []
    for e in lib.entries:
        if not e.sheet:
            continue
        try:
            if cuerpos_de_indice(e) == list(config):
                out.append(e)
        except Exception:
            continue
    return out
