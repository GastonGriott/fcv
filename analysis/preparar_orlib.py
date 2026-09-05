"""Prepara el benchmark real de OR-Library ANTES de gastar una VM en la corrida.

Hace tres cosas, en este orden, porque cada una puede abortar la siguiente:

1. Descarga y cachea las instancias (una sola vez; en la corrida hay 32 workers y
   una descarga por celda contra el servidor de Brunel es fragil).
2. RESUELVE el techo exacto de cada una (MILP con HiGHS, o enumeracion cuando la
   dimension lo permite) y lo cachea. Donde existe un valor publicado, lo contrasta
   y aborta si no coincide: C3 mide contra el techo, asi que un techo equivocado
   equivoca todas las instancias a la vez.
3. Mide la VELOCIDAD real de cada metodo sobre cada tamano, con un presupuesto
   recortado, para poder dimensionar la corrida con datos en vez de estimarla. La
   corrida anterior se apago con 30 h por delante justamente porque nadie habia
   medido que POA era 6x mas lento que M-POA.

Uso (necesita el interprete con scipy; en esta maquina, Python 3.12):
    python preparar_orlib.py                 # todo
    python preparar_orlib.py --solo-techos   # 1 y 2
"""
import argparse
import os
import sys
import time

# La raiz del repo (donde vive el paquete `fcv`) es el padre de analysis/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

try:
    import scipy  # noqa: F401
except ImportError:
    sys.exit(f"ABORTA: este interprete no tiene scipy ({sys.executable}); sin el no "
             f"se puede resolver el techo exacto. Usa Python 3.12.")

from fcv import exact, run_v2

BENCH_BUDGET = 200_000      # presupuesto recortado, solo para medir fes/s
BENCH_SEEDS = 1


def preparar_techos():
    specs = run_v2.orlib_all_specs()
    print(f"=== Techos exactos de {len(specs)} instancias de OR-Library ===")
    print(f"{'instancia':10} {'familia':11} {'dim':>5} {'techo':>16} {'via':12} {'seg':>6}")
    insts = {}
    for spec in specs:
        t0 = time.time()
        inst = run_v2.build_instance(spec)
        opt, es_exacto = inst.ceiling()
        if not es_exacto:
            sys.exit(f"ABORTA: {spec[1]} devolvio un techo NO exacto. C3 mediria "
                     f"contra una cota y el paper lo declara como optimo.")
        prov = exact.provenance(spec[1]) or {}
        dim = len(inst.random_solution(__import__('random').Random(0)))
        insts[spec] = (inst, dim)
        print(f"{spec[1]:10} {spec[0]:11} {dim:>5} {opt:>16.2f} "
              f"{prov.get('via', '?'):12} {time.time() - t0:>6.1f}")
    return insts


def medir_velocidad(insts):
    """fes/s por (metodo, dimension). Una semilla, presupuesto recortado."""
    # Una instancia representativa por GRUPO, no por dimension: scp4* y scp6* tienen
    # las dos 1000 columnas pero distinta densidad de cobertura, y la densidad es
    # justo lo que encarece cada evaluacion (la union de conjuntos cubiertos).
    # Medir solo una de las dos dimensionaria mal la otra.
    porgrupo = {}
    for spec, (inst, dim) in insts.items():
        grupo = spec[1].rstrip('0123456789')          # scp41 -> scp, cap131 -> cap
        if spec[0] == 'scp_orlib':
            grupo = spec[1][:4].rstrip('0123456789')  # scp41 -> scp4, scp61 -> scp6
            grupo = spec[1][:4] if spec[1][:4] in ('scp4', 'scp5', 'scp6') else grupo
        else:
            grupo = f"cap{len(str(dim))}_{dim}"
        porgrupo.setdefault((spec[0], dim, grupo), (spec, inst))
    print(f"\n=== Velocidad por metodo ({BENCH_BUDGET:,} evaluaciones, 1 semilla) ===")
    metodos = ["floor", "ils", "ga", "mga", "bpso", "mbpso", "bde", "mbde"]
    print(f"{'grupo':8} {'dim':>5} " + "".join(f"{m:>9}" for m in metodos))
    velocidades = {}
    for (fam, dim, grupo), (spec, inst) in sorted(porgrupo.items()):
        f_opt, _ = inst.ceiling()
        fila = f"{grupo:8} {dim:>5} "
        for m in metodos:
            fn, kw = run_v2.METHODS[m]
            t0 = time.time()
            r = fn(inst, BENCH_BUDGET, 0, f_opt, **kw)
            dt = max(time.time() - t0, 1e-9)
            fps = r["fes_used"] / dt
            velocidades[(grupo, m)] = fps
            fila += f"{fps:>9,.0f}"
        print(fila)
    return velocidades


def dimensionar(insts, velocidades, workers=32):
    """Horas de pared de la corrida completa, con las velocidades medidas."""
    metodos = ["floor", "ils", "ga", "mga", "bpso", "mbpso", "bde", "mbde"]
    print(f"\n=== Dimensionamiento con {run_v2.N_SEEDS} semillas y {workers} workers ===")
    celdas = []
    for spec, (inst, dim) in insts.items():
        budget = run_v2.BUDGET_MULT * dim
        grupo = (spec[1][:4] if spec[0] == 'scp_orlib'
                 else f"cap{len(str(dim))}_{dim}")
        for m in metodos:
            fps = velocidades.get((grupo, m))
            if not fps:
                continue
            horas = budget * run_v2.N_SEEDS / fps / 3600.0
            celdas.append((horas, spec[1], m))
    celdas.sort(reverse=True)
    total = sum(h for h, _, _ in celdas)
    # con N celdas y W workers, la pared es al menos max(celda) y ~total/W si
    # reparte bien; el limitante real es el mayor de los dos
    pared = max(total / workers, celdas[0][0]) if celdas else 0
    print(f"  celdas: {len(celdas)}   core-horas totales: {total:,.1f}")
    print(f"  celda mas lenta: {celdas[0][1]} / {celdas[0][2]} = {celdas[0][0]:.1f} h")
    print(f"  PARED ESTIMADA con {workers} workers: {pared:.1f} h")
    print(f"  (cota inferior: ninguna corrida baja de la celda mas lenta, porque las "
          f"31 semillas de una celda van en serie)")
    print("\n  las 8 celdas mas caras:")
    for h, nm, m in celdas[:8]:
        print(f"    {nm:10} {m:6} {h:6.1f} h")
    return pared


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-techos", action="store_true")
    ap.add_argument("--workers", type=int, default=32)
    a = ap.parse_args()
    insts = preparar_techos()
    if not a.solo_techos:
        vel = medir_velocidad(insts)
        dimensionar(insts, vel, a.workers)
