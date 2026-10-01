"""
Motor de imposición: GENERA echadas nuevas (no lee plantillas).

Modelo de la rotativa (deducido de las planillas de referencia y verificado contra ellas):

* Formato tabloide. Cada "hoja" del producto (una tira/ribbon) lleva 4 páginas:
  en la cara impar la página p arriba y N+1-p abajo; en la cara opuesta p+1 arriba y N-p abajo.
* Una tirada tiene hasta 2 bobinas/webs: F (1ª) y A (2ª). Cada web tiene 4 columnas (0..3)
  y dos caras: LADO 10 y LADO 13. En LADO 10 la columna c se dibuja en la posición c
  (ALTO izq, ALTO der, BAJO izq, BAJO der); en LADO 13 se dibuja espejada (posición 7-c).
* Orden de las hojas dentro de la tirada (de afuera hacia adentro del producto):
  columna 3 → 0; en columnas impares primero F y luego A, en pares primero A y luego F.
  La página impar va en LADO 10 si la columna es impar, en LADO 13 si es par.
* Capacidad por tamaño de tirada (columnas usadas por cada web):
     4 → F{3}            8 → F{3,2}            12 → F{3,2} A{2}
    16 → F{0..3}        24 → F{0..3} A{0,2}    32 → F{0..3} A{0..3}
  (hasta 12 págs. se dibuja en medio formato: solo cuadrantes BAJO).
* Tiradas: se llenan de 32 en 32; la última lleva el resto. Los cuerpos consumen hojas en orden,
  pasando de una tirada a la siguiente (un cuerpo puede repartirse entre tiradas: "32 de 36").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

LAYOUTS = {
    4: {"F": (3,)},
    8: {"F": (3, 2)},
    12: {"F": (3, 2), "A": (2,)},
    16: {"F": (0, 1, 2, 3)},
    24: {"F": (0, 1, 2, 3), "A": (0, 2)},
    32: {"F": (0, 1, 2, 3), "A": (0, 1, 2, 3)},
}
SIZES = sorted(LAYOUTS)
MAX_TIRADA = 32
FIGURAS = ["Sin figura", "Óvalo", "Triángulo", "Rect. redondeado", "Heptágono", "Hexágono", "Rombo",
           "Pentágono", "Octógono"]
GEOM = {"Óvalo": "ellipse", "Triángulo": "triangle", "Rect. redondeado": "roundRect",
        "Heptágono": "heptagon", "Hexágono": "hexagon", "Rombo": "diamond", "Pentágono": "pentagon",
        "Octógono": "octagon"}


def display_pos(face: str, col: int) -> int:
    """Posición 0..7 en la fila dibujada (L10: 0-3, L13: espejo 7-c)."""
    return col if face == "L10" else 7 - col


def pos_info(face: str, col: int):
    """(cuadrante ALTO/BAJO, Izq/Der) de una columna en una cara."""
    p = display_pos(face, col)
    header = "ALTO" if p in (0, 1, 6, 7) else "BAJO"
    lado_pos = "Izq" if p % 2 == 0 else "Der"
    return header, lado_pos


def leaf_order(size: int):
    lay = LAYOUTS[size]
    out = []
    for col in (3, 2, 1, 0):
        for web in (("F", "A") if col % 2 else ("A", "F")):
            if col in lay.get(web, ()):
                out.append((web, col))
    return out


@dataclass
class Cuerpo:
    paginas: int
    nombre: str = ""
    figura: str = "Sin figura"


@dataclass
class Colocacion:
    tirada: int          # 1..n
    web: str             # F / A
    cara: str            # L10 / L13
    col: int             # 0..3
    fila: str            # top / bot
    cuerpo: int          # índice del cuerpo (0..)
    pagina: int
    hoja: int            # hoja (leaf) dentro del cuerpo, 0 = exterior


@dataclass
class Tirada:
    numero: int
    paginas: int             # páginas reales impresas
    formato: int             # tamaño de layout usado (4..32)
    hojas: list = field(default_factory=list)       # [(web, col, cuerpo, hoja)]
    contenido: list = field(default_factory=list)   # [(cuerpo, páginas)] en orden

    @property
    def webs(self):
        return [w for w in ("F", "A") if w in LAYOUTS[self.formato]]

    @property
    def medio_formato(self):
        return self.formato <= 12

    def descripcion(self, cuerpos):
        partes = []
        for ci, n in self.contenido:
            c = cuerpos[ci]
            if n == c.paginas:
                partes.append(f"{n}")
            else:
                partes.append(f"{n} de {c.paginas}")
        return " + ".join(partes)


@dataclass
class Echada:
    cuerpos: list
    tiradas: list
    colocaciones: list
    avisos: list = field(default_factory=list)

    @property
    def total(self):
        return sum(c.paginas for c in self.cuerpos)

    @property
    def config(self):
        return "+".join(str(c.paginas) for c in self.cuerpos)

    def en(self, tirada, web, cara, col, fila):
        for p in self.colocaciones:
            if (p.tirada, p.web, p.cara, p.col, p.fila) == (tirada, web, cara, col, fila):
                return p
        return None


def parse_config(texto: str) -> list[int]:
    partes = [p for p in re.split(r"[+\s,;]+", str(texto).strip()) if p]
    if not partes or not all(p.isdigit() for p in partes):
        raise ValueError("Escriba los cuerpos como números separados por '+', por ejemplo 20+8+4.")
    return [int(p) for p in partes]


def plan_tiradas(total: int) -> list[int]:
    if total <= MAX_TIRADA:
        return [total]
    n, resto = divmod(total, MAX_TIRADA)
    return [MAX_TIRADA] * n + ([resto] if resto else [])


def generar(cuerpos: list[Cuerpo] | list[int] | str, tiradas: list[int] | None = None) -> Echada:
    if isinstance(cuerpos, str):
        cuerpos = parse_config(cuerpos)
    cuerpos = [c if isinstance(c, Cuerpo) else Cuerpo(int(c)) for c in cuerpos]
    avisos = []
    for i, c in enumerate(cuerpos):
        if c.paginas <= 0 or c.paginas % 4:
            raise ValueError(f"El cuerpo {i + 1} tiene {c.paginas} págs.: cada cuerpo debe ser múltiplo de 4.")
        if not c.nombre:
            c.nombre = "Tapa" if i == 0 and len(cuerpos) > 1 else (f"Cuerpo {i + 1}" if len(cuerpos) > 1 else "Único")
    total = sum(c.paginas for c in cuerpos)
    sizes = tiradas or plan_tiradas(total)
    if sum(sizes) != total:
        raise ValueError(f"Las tiradas suman {sum(sizes)} y los cuerpos {total}.")

    # secuencia global de hojas (web, col) por tirada
    tir_objs, secuencia = [], []
    for ti, size in enumerate(sizes, start=1):
        if size % 4:
            raise ValueError(f"Tirada {ti}: {size} págs. no es múltiplo de 4.")
        formato = next((s for s in SIZES if s >= size), None)
        if formato is None:
            raise ValueError(f"Tirada {ti}: {size} págs. supera el máximo de {MAX_TIRADA}.")
        if formato != size:
            avisos.append(f"Tirada {ti}: {size} págs. no tiene formato propio; se usa el de {formato} "
                          f"dejando {(formato - size) // 4} hoja(s) en blanco (sin plantilla de referencia).")
        t = Tirada(numero=ti, paginas=size, formato=formato)
        tir_objs.append(t)
        for web, col in leaf_order(formato)[: size // 4]:
            secuencia.append((ti, web, col))

    colocaciones = []
    k = 0
    for ci, c in enumerate(cuerpos):
        n = c.paginas
        for j in range(n // 4):
            ti, web, col = secuencia[k]
            k += 1
            t = tir_objs[ti - 1]
            t.hojas.append((web, col, ci, j))
            if t.contenido and t.contenido[-1][0] == ci:
                t.contenido[-1] = (ci, t.contenido[-1][1] + 4)
            else:
                t.contenido.append((ci, 4))
            impar, par = 2 * j + 1, 2 * j + 2
            cara_impar = "L10" if col % 2 else "L13"
            cara_par = "L13" if cara_impar == "L10" else "L10"
            for cara, arriba in ((cara_impar, impar), (cara_par, par)):
                colocaciones.append(Colocacion(ti, web, cara, col, "top", ci, arriba, j))
                colocaciones.append(Colocacion(ti, web, cara, col, "bot", ci, n + 1 - arriba, j))
    return Echada(cuerpos=cuerpos, tiradas=tir_objs, colocaciones=colocaciones, avisos=avisos)


def figuras_por_defecto(n: int) -> list[str]:
    return [FIGURAS[i % len(FIGURAS)] for i in range(n)]
