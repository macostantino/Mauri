"""Valida el MOTOR contra las plantillas: genera cada combinación del índice y la compara.

Uso:  python verificar.py ["Plantillas Echadas FullColor 28-4-2026.xlsx"]
"""
import sys
from pathlib import Path

from echadas.comparar import comparar_entrada
from echadas.loader import load_library

path = sys.argv[1] if len(sys.argv) > 1 else next(Path(__file__).parent.glob("Plantillas*.xlsx"))
lib = load_library(path)
ok, malas = 0, []
for e in lib.entries:
    ech, sel, r = comparar_entrada(lib, e)
    if r.identica:
        ok += 1
    else:
        malas.append((e, ech, r))
print(f"{ok} de {len(lib.entries)} combinaciones generadas son idénticas a su plantilla.")
for e, ech, r in malas:
    print(f"\nPlantilla {e.folio} ({ech.config}): {len(r.diferencias)} diferencia(s)")
    for d in r.diferencias:
        print("   ", d)
