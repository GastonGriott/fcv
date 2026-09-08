"""Analisis de admision FCV: aplica los tres criterios del protocolo a uno o mas
metodos candidatos, contra el piso fuerte, sobre cualquier conjunto de instancias.

Usa SOLO las funciones del paquete `fcv`, para que el veredicto salga del mismo
codigo que define el protocolo y no de un analisis paralelo escrito para la ocasion.

EL PROTOCOLO, TAL COMO LO DEFINE EL PAPER (§3)
----------------------------------------------
C1  El candidato le gana al PISO FUERTE en FIABILIDAD (McNemar pareado por semilla,
    Holm dentro de la familia). La velocidad va como DIAGNOSTICO secundario y NO
    gatea la admision.
C2  La instancia no es floor-trivial: NR = mediana(FES-to-opt del piso)/B, y se
    excluyen las que tienen NR < tau. Que piso mide esa trivialidad cambia el
    resultado, asi que se reportan LOS DOS (ver mas abajo).
C3  La calidad se declara como distancia al techo.

REGIMEN DE MEDICION — por par (candidato, piso) en cada instancia
-----------------------------------------------------------------
Si ni el candidato ni el piso alcanzan el techo en ninguna semilla, el evento de
exito no es observable: los dos quedan en SRate 0, McNemar empata en cero y
devuelve p=1 para cualquier par de metodos, por bueno o malo que sea el candidato.
Un "no pasa" obtenido asi no es evidencia contra el candidato, es AUSENCIA de
evidencia, y el protocolo tiene que distinguir las dos cosas.

En ese regimen (budget-bound) la barra deja de ser el techo y pasa a ser endogena:
la mediana, sobre las semillas, del mejor valor del piso fuerte. La semantica de C1
no se mueve —sigue siendo "le gana al piso en fiabilidad"— y el test, la correccion
y la lectura son los mismos; lo unico que cambia es donde esta la barra, porque el
techo dejo de ser alcanzable dentro del presupuesto. El diagnostico secundario pasa
de velocidad (no hay FES-to-target que comparar) a calidad final.

CORRIDAS ANALIZADAS CON ESTE SCRIPT
-----------------------------------
1) POA in-protocol, 2026-09-02 — 135 instancias generadas x 31 semillas
   (VM e2-highcpu-32: 197 min para poa/mpoa + 36 min para el piso, 91 core-h).
   El piso se recorrio entero ese dia en vez de reusar el de junio, para que todo
   el conjunto salga del mismo codigo y el mismo dia. La corrida de junio se
   reprodujo EXACTA: 5.022 corridas comparables, identicas semilla por semilla
   entre Windows local y Debian en GCE (ver `check_reproducibilidad.py`).

     python analyze_admision.py --perseed fcv_v2_poa_perseed.csv
                                          fcv_v2_floor_ils_perseed.csv

2) OR-Library, 2026-09-03 — scp41..scp48 x 31 semillas, benchmark real de Beasley
   (1990) con optimo publicado. Responde a la critica de "instancias plantadas":
   aca la dificultad no la fija nuestro generador.

     python analyze_admision.py --perseed fcv_v2_floor_ils_mpoa_orlib_perseed.csv

Uso general (desde proyectos/iaa-tema2/corrida_poa/):
     python analyze_admision.py --perseed A.csv [B.csv ...]
                                [--floor ils] [--methods poa,mpoa] [--seeds 31]
"""
import argparse
import csv
import os
import statistics
import sys

# La raiz del repo (donde vive el paquete `fcv`) es el padre de analysis/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fcv import core

# La consola de Windows usa cp1252 y rompe los guiones largos del reporte, que
# despues queda archivado como evidencia con caracteres invalidos.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Este script EMITE VEREDICTOS, asi que no puede arrancar sin poder calcularlos.
# En esta maquina conviven dos interpretes y el `python` del PATH resulto ser el
# 3.13, que no tiene scipy, mientras el 3.12 si; el Friedman salia 185.8 en vez de
# 247.4 y los Wilcoxon en 1.0, sin que nada lo advirtiera.
try:
    import scipy  # noqa: F401
except ImportError:
    sys.exit(f"ABORTA: este interprete no tiene scipy ({sys.executable}).\n"
             f"       Sin el, los p-valores del veredicto serian inventados.\n"
             f"       Usa el interprete que si lo tiene (aqui, Python 3.12).")

TAU = 0.05          # C2: umbral de floor-trivialidad
ALPHA = 0.05
FLOOR_DEFAULT = 'ils'      # piso FUERTE: contra el se admite
FLOOR_MIN = 'floor'        # piso MINIMO: el otro con el que se puede medir C2


def load(paths):
    rows = []
    for p in paths:
        if not os.path.exists(p):
            sys.exit(f"FALTA el CSV: {p}")
        with open(p, encoding='utf-8') as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def key(r):
    return (r['family'], r['tag'], r['n'], r['idx'], r['decoder'])


def runs_by(rows, method):
    """Agrupa las corridas por instancia, en el formato que espera `fcv.core`."""
    d = {}
    for r in rows:
        if r['method'] != method:
            continue
        d.setdefault(key(r), []).append({
            'fes_to_target': None if r['ftt'] in ('', 'None') else float(r['ftt']),
            'best': float(r['best']),
            'seed': int(r['seed']),
        })
    for k in d:
        d[k].sort(key=lambda x: x['seed'])   # el pareado por semilla lo exige McNemar
    return d


def check_integridad(runs, nombre, n_seeds):
    """Una corrida a medias mentiria en silencio: aborta si falta alguna semilla."""
    malas = {k: len(v) for k, v in runs.items() if len(v) != n_seeds}
    if malas:
        print(f"  !! {nombre}: {len(malas)} celdas con != {n_seeds} semillas "
              f"-> {sorted(malas.items())[:5]}")
        return False
    return True


def c2_report(runs_piso, comunes, budget, etiqueta):
    """Instancias floor-triviales segun UN piso. Devuelve el conjunto que sobrevive."""
    no_triv = [k for k in comunes
               if k in runs_piso
               and not core.is_floor_trivial(runs_piso[k], budget[k], tau=TAU)]
    triv = len(comunes) - len(no_triv)
    print(f"     con piso {etiqueta:9s}: {triv:>3}/{len(comunes)} triviales "
          f"-> quedan {len(no_triv)} con evidencia")
    if triv:
        porfam = {}
        for k in comunes:
            if k in runs_piso and core.is_floor_trivial(runs_piso[k], budget[k], tau=TAU):
                porfam[k[0]] = porfam.get(k[0], 0) + 1
        tot = {}
        for k in comunes:
            tot[k[0]] = tot.get(k[0], 0) + 1
        detalle = '  '.join(f"{f}={porfam.get(f, 0)}/{tot[f]}" for f in sorted(tot))
        print(f"     {'':14s}  por familia: {detalle}")
    return no_triv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--perseed', nargs='+', required=True)
    ap.add_argument('--floor', default=FLOOR_DEFAULT)
    ap.add_argument('--methods', default=None,
                    help='coma-separados; por defecto, todos los del CSV menos el piso')
    ap.add_argument('--seeds', type=int, default=31)
    ap.add_argument('--c2-floor', default=FLOOR_DEFAULT, choices=['floor', 'ils'],
                    help='piso con el que se filtra C2 para evaluar C1/C3 (se '
                         'reportan los dos, pero el filtro usa este)')
    args = ap.parse_args()

    rows = load(args.perseed)
    presentes = sorted({r['method'] for r in rows})
    if args.floor not in presentes:
        sys.exit(f"el piso '{args.floor}' no esta en el CSV (hay: {presentes})")
    cands = (args.methods.split(',') if args.methods
             else [m for m in presentes if m not in (args.floor, FLOOR_MIN)])
    if not cands:
        sys.exit(f"no hay metodos candidatos que evaluar (en el CSV: {presentes})")

    FLOOR = runs_by(rows, args.floor)
    MIN = runs_by(rows, FLOOR_MIN) if FLOOR_MIN in presentes else {}
    CAND = {m: runs_by(rows, m) for m in cands}
    budget = {key(r): float(r['budget']) for r in rows}
    f_opt = {key(r): float(r['f_opt']) for r in rows}
    exacto = {key(r): r['exact'] == 'True' for r in rows}

    print(f"metodos en el CSV: {presentes}")
    print(f"piso fuerte: {args.floor}   candidatos: {cands}")
    ok = check_integridad(FLOOR, args.floor, args.seeds)
    for m in cands:
        ok = check_integridad(CAND[m], m, args.seeds) and ok
    if not ok:
        sys.exit("\nABORTA: la corrida esta incompleta. Un analisis sobre celdas a "
                 "medias da un veredicto que no se sostiene.")

    comunes = sorted(set.intersection(set(FLOOR), *[set(CAND[m]) for m in cands]))
    if not comunes:
        sys.exit("ABORTA: ninguna instancia tiene piso y candidato a la vez.")
    n_aprox = sum(1 for k in comunes if not exacto[k])
    print(f"\nconjunto completo: {len(comunes)} instancias, todas con piso propio "
          f"corrido el mismo dia")
    print(f"familias: {sorted({k[0] for k in comunes})}")
    if n_aprox:
        print(f"!! techo NO exacto (cota LP o mejor conocido) en {n_aprox}/"
              f"{len(comunes)}: C3 mide distancia a una COTA, hay que declararlo")
    print()

    # --- C2 ---------------------------------------------------------------
    # Que piso mide la trivialidad cambia el conjunto de evidencia, y bastante:
    # una instancia que el piso fuerte resuelve siempre y rapido no aporta nada
    # sobre si hace falta una metaheuristica, aunque el piso minimo sufra en ella.
    # Se reportan los dos y se declara cual filtra.
    print(f"C2 — floor-triviales (el piso resuelve SIEMPRE en <{TAU:.0%} del presupuesto)")
    sobrevive = {}
    if MIN:
        sobrevive[FLOOR_MIN] = c2_report(MIN, comunes, budget, 'MINIMO')
    sobrevive[args.floor] = c2_report(FLOOR, comunes, budget, f'FUERTE({args.floor})')
    if args.c2_floor not in sobrevive:
        sys.exit(f"pediste filtrar C2 con el piso '{args.c2_floor}', que no esta "
                 f"en el CSV (hay: {sorted(sobrevive)})")
    no_triv = sobrevive[args.c2_floor]
    print(f"     ==> filtra el piso {args.c2_floor}: {len(no_triv)} instancias "
          f"pasan a C1/C3")
    if not no_triv:
        print("     ==> C2 se llevo TODAS las instancias: el conjunto no aporta\n"
              "         evidencia y C1/C3 no son evaluables. No es un fallo del\n"
              "         script: es el veredicto.")
        return
    print()
    n = len(no_triv)

    # --- C1 ---------------------------------------------------------------
    for nombre, M in CAND.items():
        # regimen POR PAR (candidato, piso): si ninguno de los dos alcanza el techo
        # en esa instancia, el exito no es observable y la barra pasa a ser endogena.
        bars, regimenes = {}, {}
        for k in no_triv:
            reg = core.instance_regime(FLOOR[k])
            regimenes[k] = reg
            bars[k] = core.endogenous_bar(FLOOR[k]) if reg == 'budget-bound' else None
        n_bound = sum(1 for k in no_triv if regimenes[k] == 'budget-bound')

        ds = {k: core.floor_dominance(M[k], FLOOR[k], bar=bars[k]) for k in no_triv}
        adj = dict(zip(no_triv, core.holm([ds[k]['p_reliability'] for k in no_triv])))
        gana = [k for k in no_triv
                if ds[k]['reliability_better'] and adj[k] < ALPHA]
        pierde = [k for k in no_triv
                  if ds[k]['srate_method'] < ds[k]['srate_floor'] and adj[k] < ALPHA]
        ciegas = [k for k in no_triv
                  if ds[k]['srate_method'] == 0.0 and ds[k]['srate_floor'] == 0.0]

        print(f"C1 — {nombre} contra el piso fuerte '{args.floor}', en {n} instancias")
        print(f"     regimen: target-reachable {n - n_bound}  |  budget-bound "
              f"{n_bound} (barra endogena = mediana del piso)")
        print(f"     SRate medio: {statistics.mean(ds[k]['srate_method'] for k in no_triv):.3f}"
              f"  |  piso: {statistics.mean(ds[k]['srate_floor'] for k in no_triv):.3f}")
        print(f"     gana en fiabilidad (Holm): {len(gana)}/{n}   "
              f"pierde: {len(pierde)}/{n}")
        print(f"     p ajustado: min {min(adj.values()):.3e}  max {max(adj.values()):.3e}")
        if ciegas:
            print(f"     !! {len(ciegas)}/{n} instancias sin poder discriminante "
                  f"(ambos en SRate 0): ahi C1 no dice nada")
        veredicto = ('PASA' if len(gana) == n else 'NO PASA')
        razon = ('por evidencia' if (gana or pierde)
                 else 'INDETERMINADO: el conjunto no discrimina')
        print(f"     ==> {veredicto} ({razon})")
        # diagnostico secundario: no gatea, se reporta
        diag = 'velocidad' if n_bound < n else 'calidad final'
        mejor = sum(1 for k in no_triv
                    if ds[k]['diagnostic_better'] == 'method'
                    and ds[k]['p_diagnostic'] < ALPHA)
        print(f"     [diagnostico, no gatea] mejor en {diag}: {mejor}/{n}\n")

    # --- C3 ---------------------------------------------------------------
    gi = [core.gap_to_ceiling(FLOOR[k], f_opt[k]) for k in no_triv]
    print("C3 — distancia al techo" + (" (COTA, no optimo)" if n_aprox else " exacto"))
    print(f"     piso {args.floor}: mediana {statistics.median(gi):.2%}  "
          f"peor {max(gi):.2%}")
    if MIN:
        gm = [core.gap_to_ceiling(MIN[k], f_opt[k]) for k in no_triv if k in MIN]
        if gm:
            print(f"     piso minimo: mediana {statistics.median(gm):.2%}  "
                  f"peor {max(gm):.2%}")
    for nombre, M in CAND.items():
        gm = [core.gap_to_ceiling(M[k], f_opt[k]) for k in no_triv]
        peor = sum(1 for a, b in zip(gm, gi) if a > b)
        print(f"     {nombre:5s}: mediana {statistics.median(gm):.2%}  "
              f"peor {max(gm):.2%}   queda mas lejos que el piso en {peor}/{n}")
    print()

    for nombre, M in CAND.items():
        nunca = sum(1 for k in M if core.success_rate(M[k]) == 0.0)
        print(f"Referencia sobre las {len(M)} instancias corridas: {nombre} nunca "
              f"alcanzo el techo en {nunca} de ellas.")


if __name__ == '__main__':
    main()
