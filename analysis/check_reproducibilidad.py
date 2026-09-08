"""Verifica que la corrida del piso del 2026-09-02 reproduce la de junio.

Compara `floor` e `ils` semilla por semilla entre:
  results/fcv_v2_perseed.csv            — junio, Windows local, 81 instancias
  results/fcv_v2_floor_ils_perseed.csv  — septiembre, Debian en GCE, 135

Solo se comparan las instancias que ambas comparten. La igualdad se exige EXACTA
sobre las tres columnas de resultado (best, ftt, fes): el paquete es stdlib puro
con semilla determinista, asi que una diferencia aqui significaria que algo del
entorno se filtro al resultado — y eso invalidaria comparar corridas de fechas
distintas, que es justo lo que el analisis de admision necesita hacer.

Uso:  python analysis/check_reproducibilidad.py    (desde cualquier directorio)
Salida: codigo 0 si todo reproduce, 1 si hay divergencias.
"""
import csv
import os
import sys


def load(path):
    with open(path, encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def index(rows, method):
    """(instancia, semilla) -> tripleta de resultado."""
    return {
        (r['family'], r['tag'], r['n'], r['idx'], r['decoder'], r['seed']):
            (r['best'], r['ftt'], r['fes'])
        for r in rows if r['method'] == method
    }


def main():
    # Rutas relativas al repo, no al directorio desde el que se invoca.
    res = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'results')
    nuevo = load(os.path.join(res, 'fcv_v2_floor_ils_perseed.csv'))
    viejo = load(os.path.join(res, 'fcv_v2_perseed.csv'))

    total_dif = 0
    for metodo in ('floor', 'ils'):
        a, b = index(nuevo, metodo), index(viejo, metodo)
        comunes = set(a) & set(b)
        difs = [k for k in comunes if a[k] != b[k]]
        total_dif += len(difs)
        print(f"{metodo:>6}: {len(comunes)} corridas comparables | "
              f"identicas {len(comunes) - len(difs)} | distintas {len(difs)}")
        for k in difs[:5]:
            print(f"         {k}\n           hoy   {a[k]}\n           junio {b[k]}")

    if total_dif:
        print(f"\nFALLA: {total_dif} corridas no reproducen.")
        return 1
    print("\nOK: la corrida de junio reproduce exacta en otra maquina y otro sistema.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
