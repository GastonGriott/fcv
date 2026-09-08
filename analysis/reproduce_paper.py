"""Reproduce las cifras del paper que `analyze_admision.py` no emite.

El README prometia que «every rank, p-value and verdict can be recomputed», y no era
cierto: el ranking de Friedman, la distancia critica de Nemenyi y el conteo de
floor-triviales por familia no salian de ningun script publicado.

Y los emite DOS VECES, con y sin el filtro C2, porque ahi hay una decision de protocolo
que el paper tomo en silencio: el Algoritmo 1 admite «on U» —el conjunto que queda tras
excluir las instancias floor-triviales— pero el ranking y los denominadores publicados
se calcularon sobre las 81 sin filtrar. La diferencia no es cosmetica.

Uso, desde cualquier directorio, con Python 3.12+ y SciPy:

    py -3.12 analysis/reproduce_paper.py
"""
import csv
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
RESULTS = os.path.join(RAIZ, "results")

from fcv import core, stats  # noqa: E402


def key(r):
    return (r["family"], r["tag"], r["n"], r["idx"], r["decoder"])


def cargar(nombre):
    """(metodo -> {instancia -> corridas}), y el presupuesto por instancia."""
    ruta = os.path.join(RESULTS, nombre)
    if not os.path.exists(ruta):
        sys.exit(f"FALTA el CSV: {ruta}")
    with open(ruta, encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))

    por_metodo, budget = {}, {}
    for r in filas:
        k = key(r)
        budget[k] = float(r["budget"])
        por_metodo.setdefault(r["method"], {}).setdefault(k, []).append({
            "fes_to_target": None if r["ftt"] in ("", "None") else float(r["ftt"]),
            "best": float(r["best"]),
            "seed": int(r["seed"]),
        })
    for d in por_metodo.values():
        for k in d:
            d[k].sort(key=lambda x: x["seed"])
    return por_metodo, budget


def ranking(por_metodo, instancias, etiqueta):
    metodos = sorted(por_metodo)
    # average_ranks() ordena ASCENDENTE (rank 1 = valor mas chico), y aca mas SRate
    # es mejor: se pasa el negativo para que el rank 1 sea el mejor metodo. Sin esto
    # el ranking sale invertido y plausible — mbDE aparece primero en vez de ultimo.
    matriz = [[-core.success_rate(por_metodo[m][p]) for m in metodos] for p in instancias]

    chi2, p, ranks = stats.friedman(matriz)
    cd = stats.nemenyi_cd(k=len(metodos), N=len(instancias))

    print(f"\n--- Friedman / Nemenyi — {etiqueta} ---")
    print(f"  N = {len(instancias)} problemas, k = {len(metodos)} metodos")
    print(f"  chi2 = {chi2:.4f}   p = {p:.3e}   CD = {cd:.4f}")
    orden = sorted(zip(metodos, ranks), key=lambda t: t[1])
    for m, r in orden:
        print(f"    {m:>6}  {r:.3f}")
    mejor_rank = orden[0][1]
    empatados = [m for m, r in orden if r - mejor_rank < cd]
    print(f"  empatados con el mejor: {', '.join(empatados)}")
    return dict(orden)


def main():
    print("=" * 78)
    print("REPRODUCCION DE LAS CIFRAS DEL PAPER — estudio factorial (§4)")
    print("=" * 78)

    por_metodo, budget = cargar("fcv_v2_perseed.csv")
    instancias = sorted(set.intersection(*(set(d) for d in por_metodo.values())))

    triv = {}
    for piso in ("floor", "ils"):
        triv[piso] = {k for k in instancias
                      if core.is_floor_trivial(por_metodo[piso][k], budget[k])}

    print(f"\nC2 — floor-triviales sobre {len(instancias)} problemas")
    for piso, nombre in (("floor", "minimo"), ("ils", "fuerte")):
        n = len(triv[piso])
        porfam = {}
        for k in triv[piso]:
            porfam[k[0]] = porfam.get(k[0], 0) + 1
        print(f"  piso {nombre:7s}: {n:2d} excluidas -> quedan {len(instancias)-n} "
              f"con evidencia   {porfam}")
    print("  🔴 Esos son los EXCLUIDOS. El abstract reporta «moves the evidence set")
    print("     from 12 to 27», que es al reves: el conjunto va de 69 a 54.")

    todos = ranking(por_metodo, instancias, "las 81, SIN filtrar (lo publicado)")

    u = [k for k in instancias if k not in triv["ils"]]
    con_c2 = ranking(por_metodo, u, "las 54 de U, filtradas con el piso que ADMITE")

    print("\n--- Que mueve el filtro ---")
    for m in sorted(todos, key=lambda x: con_c2[x]):
        print(f"    {m:>6}  {todos[m]:.3f}  ->  {con_c2[m]:.3f}   ({con_c2[m]-todos[m]:+.3f})")


if __name__ == "__main__":
    main()
