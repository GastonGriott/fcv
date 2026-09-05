"""fcv.run_v2 — corrida ROBUSTA grado-publicacion (ver EXPERIMENT_DESIGN_v2.md).

Diferencias clave vs run_parallel (v1):
  - Instancias DURAS reales: clases de Pisinger (knapsack) + SCP (plantado y, opc.,
    OR-Library) + UFLP. Mezcla de control facil + duras.
  - 8 METODOS factoriales: floor, ils (piso fuerte), {ga,bpso,bde}x{vanilla,memetico}.
  - Brazo de DECODER: penalty (base) y repair (Baldwiniano) para el sub-estudio de
    control de decoder.
  - Salida POR-SEED (best, fes_to_target, fes_used) -> habilita Friedman/Wilcoxon/CD.
  - 31 seeds por defecto. Cache firmado resumible. Picklable para ProcessPoolExecutor.

Uso:  python -m fcv.run_v2 --quick
      import fcv.run_v2 as r; r.run(jobs=-1)            # Colab/local, horas
"""
import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import os
import random
import statistics

from . import core, methods, knapsack, scp, uflp
from .instances_real import knap_class
from .decoders import with_repair

# cache dir: env var FCV_CACHE_V2 tiene prioridad (para Drive en Colab; la var de
# entorno la heredan workers fork Y spawn). Default = junto al paquete.
CACHE_DIR = os.environ.get("FCV_CACHE_V2") or os.path.join(
    os.path.dirname(__file__), "..", "_cache_v2")
N_SEEDS = 31
BUDGET_MULT = 10000
SIG_VER = "v2.2"   # v2.2: instancias knapsack con seed determinista (fix hash()) +
                   #       operador memetico unificado (descenso completo del mejor)

METHODS = {
    "floor":  (core.floor_run, {}),
    "ils":    (methods.ils_run, {}),
    "ga":     (methods.ga_run, {}),
    "mga":    (methods.ga_run, {"memetic": True}),
    "bpso":   (methods.bpso_run, {}),
    "mbpso":  (methods.bpso_run, {"memetic": True}),
    "bde":    (methods.bde_run, {}),
    "mbde":   (methods.bde_run, {"memetic": True}),
    "poa":    (methods.poa_run, {}),
    "mpoa":   (methods.poa_run, {"memetic": True}),
}

# --- registro de instancias (specs picklables: tuplas de datos planos) --------
# spec = (family, tag, n, idx)
def build_instance(spec):
    family, tag, n, idx = spec
    if family == "knapsack":
        return knap_class(tag, n, seed=idx)
    if family == "scp":
        return scp.make_instance(n, seed=10_000 * n + idx)
    if family == "uflp":
        return uflp.make_instance(n, seed=10_000 * n + idx)
    if family == "scp_orlib":
        from . import scp_orlib
        return scp_orlib.load(tag)
    if family == "uflp_orlib":
        from . import uflp_orlib
        return uflp_orlib.load(tag)
    raise ValueError(f"familia desconocida: {family}")


# grilla por defecto: control facil + duras. Tamanos elegidos para que la corrida
# completa (8 metodos x 31 seeds x budget 1e4*dim en Python puro) quepa en ~horas en
# 12 nucleos; el regimen de inversion de veredicto y la frontera floor-fail ya
# aparecen en n<=80 (ver smoke tests).
KNAP_SIZES = [30, 50, 80, 120]   # 120 anade un punto de escala para "reaparece a escala"
KNAP_TAGS = ["uncorrelated", "strongly", "inverse", "mstr", "spanner"]
SCP_SIZES = [40, 60, 90, 120]
UFLP_SIZES = [12, 16, 18]
INSTANCES_PER = 5
DECODERS = ["penalty"]                      # "repair" se activa en el sub-estudio


def default_specs(instances=INSTANCES_PER):
    specs = []
    for tag in KNAP_TAGS:
        for n in KNAP_SIZES:
            for idx in range(instances):
                specs.append(("knapsack", tag, n, idx))
    for n in SCP_SIZES:
        for idx in range(instances):
            specs.append(("scp", "", n, idx))
    for n in UFLP_SIZES:
        for idx in range(instances):
            specs.append(("uflp", "", n, idx))
    return specs


# Ocho instancias, no tres: run_v2 paraleliza POR CELDA, asi que 8 x 4 metodos = 32
# celdas llenan exactamente una VM de 32 nucleos. El tiempo de pared lo fija la celda
# mas lenta (31 semillas secuenciales), de modo que correr 3 instancias en esa misma
# maquina costaria lo mismo y dejaria 20 nucleos ociosos.
ORLIB_PILOT = ["scp41", "scp42", "scp43", "scp44",
               "scp45", "scp46", "scp47", "scp48"]

# Conjunto completo de set covering real. Se deja FUERA el grupo scp5*, que tiene
# 2000 columnas: el presupuesto del protocolo es 10^4 x dim, asi que duplica las
# evaluaciones y ademas encarece cada una (el vecindario 1-flip recorre las 2000
# columnas), y sale del orden de 4x el costo de un scp4*. No aporta un regimen
# nuevo —scp6* ya da otra densidad a la misma dimension— y si multiplicaria por
# tres el tiempo de pared de la corrida completa.
ORLIB_SCP_FULL = ["scp41", "scp42", "scp43", "scp44", "scp45",
                  "scp46", "scp47", "scp48", "scp49", "scp410",   # m=200 n=1000
                  "scp61", "scp62", "scp63", "scp64", "scp65"]    # m=200 n=1000


def orlib_specs(names=None):
    """Set covering REAL de OR-Library (Beasley 1990), con optimo exacto.

    Son la respuesta a la critica de "instancias plantadas": aca la dificultad no
    la fija nuestro generador. Ojo con el costo: estas instancias tienen 1000
    columnas, asi que el presupuesto del protocolo (10.000 x dim) son 10^7
    evaluaciones por semilla. El campo `n` del spec es solo etiqueta; la dimension
    real se lee de la instancia."""
    return [("scp_orlib", nm, 1000, 0) for nm in (names or ORLIB_PILOT)]


def orlib_scp_full_specs():
    return orlib_specs(ORLIB_SCP_FULL)


def orlib_uflp_specs(names=None):
    """UFLP REAL de OR-Library. Cierra la otra mitad de la critica: la familia que
    el estudio declaraba floor-trivial se evaluaba solo sobre instancias propias de
    m<=18. Aca m va 16 -> 25 -> 50 y el techo es exacto (enumeracion o MILP).

    Son baratas: dim 50 en el peor caso, o sea 5x10^5 evaluaciones contra los 10^7
    de un set covering. Entran casi de arriba en cualquier corrida."""
    from .uflp_orlib import UFLP_ALL
    return [("uflp_orlib", nm, 0, 0) for nm in (names or UFLP_ALL)]


def orlib_all_specs():
    """Todo el benchmark real: set covering + UFLP."""
    return orlib_scp_full_specs() + orlib_uflp_specs()


SPEC_SETS = {"default": default_specs, "orlib": orlib_specs,
             "orlib_scp": orlib_scp_full_specs, "orlib_uflp": orlib_uflp_specs,
             "orlib_all": orlib_all_specs}


def _sig(spec, decoder, method, n_seeds):
    return hashlib.sha1(
        f"{spec}|{decoder}|{method}|{n_seeds}|{BUDGET_MULT}|{SIG_VER}".encode()
    ).hexdigest()[:16]


def _cache_path(spec, decoder, method, n_seeds):
    os.makedirs(CACHE_DIR, exist_ok=True)
    fam, tag, n, idx = spec
    key = f"{fam}_{tag}_{n}_{idx}_{decoder}_{method}_n{n_seeds}"
    return os.path.join(CACHE_DIR, key + ".json")


def _cell(task):
    spec, decoder, method, n_seeds = task
    path = _cache_path(spec, decoder, method, n_seeds)
    sig = _sig(spec, decoder, method, n_seeds)
    if os.path.exists(path):
        try:
            d = json.load(open(path, encoding="utf-8"))
            if d.get("sig") == sig:
                return d["res"]
        except Exception:
            pass
    inst = build_instance(spec)
    if decoder == "repair":
        inst = with_repair(inst)
    f_opt, exact = inst.ceiling()
    dim = len(inst.random_solution(random.Random(0)))
    budget = BUDGET_MULT * dim
    fn, kw = METHODS[method]
    per_seed = []
    for s in range(n_seeds):
        r = fn(inst, budget, s, f_opt, **kw)
        per_seed.append({"seed": s, "best": r["best"],
                         "ftt": r["fes_to_target"], "fes": r["fes_used"]})
    res = {
        "family": spec[0], "tag": spec[1], "n": spec[2], "idx": spec[3],
        "decoder": decoder, "method": method, "dim": dim, "budget": budget,
        "f_opt": f_opt, "exact": bool(exact), "per_seed": per_seed,
    }
    tmp = path + ".tmp"
    json.dump({"sig": sig, "res": res}, open(tmp, "w", encoding="utf-8"))
    os.replace(tmp, path)
    return res


def build_tasks(specs, decoders, methods_list, n_seeds):
    return [(sp, dec, m, n_seeds)
            for sp in specs for dec in decoders for m in methods_list]


def run(jobs=None, specs=None, decoders=DECODERS,
        methods_list=tuple(METHODS), n_seeds=N_SEEDS, out_prefix=None):
    if specs is None:
        specs = default_specs()
    tasks = build_tasks(specs, decoders, methods_list, n_seeds)
    if not jobs or jobs < 1:
        jobs = max(1, (os.cpu_count() or 2))
    n_tasks = len(tasks)
    print(f"FCV v2: {n_tasks} celdas x {n_seeds} seeds, {jobs} workers "
          f"(cpu={os.cpu_count()})", flush=True)
    # progreso granular: as_completed -> avanza por celda REALMENTE terminada (fuera
    # de orden), no por orden de envio como ex.map. Asi una celda lenta no congela el
    # contador mientras los otros workers avanzan. El dashboard (fcv.progress) corre en
    # el PROCESO PRINCIPAL y pinta una barra de color por metodo + por familia + TOTAL;
    # cae a tqdm/barra unica si rich no esta disponible. Solo presentacion.
    from .progress import live_dashboard
    results = []
    with cf.ProcessPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(_cell, t): t for t in tasks}
        with live_dashboard(tasks, jobs) as dash:
            for fut in cf.as_completed(futs):
                r = fut.result()
                results.append(r)
                sp, _dec, m, _ = futs[fut]
                dash.advance(m, sp[0])      # sp[0] = familia
    if out_prefix is None:
        out_prefix = os.path.join(os.path.dirname(__file__), "..", "fcv_v2")
    _write_outputs(results, out_prefix)
    return results


def _write_outputs(results, out_prefix):
    # 1) per-seed largo
    ps_path = out_prefix + "_perseed.csv"
    with open(ps_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["family", "tag", "n", "idx", "decoder", "method", "dim",
                    "budget", "f_opt", "exact", "seed", "best", "ftt", "fes"])
        for r in results:
            for ps in r["per_seed"]:
                w.writerow([r["family"], r["tag"], r["n"], r["idx"], r["decoder"],
                            r["method"], r["dim"], r["budget"], r["f_opt"],
                            r["exact"], ps["seed"], ps["best"], ps["ftt"], ps["fes"]])
    # 2) agregado por celda
    ag_path = out_prefix + "_agg.csv"
    with open(ag_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["family", "tag", "n", "idx", "decoder", "method", "dim", "budget",
                    "f_opt", "srate", "nr", "mean_gap", "median_best", "median_ftt"])
        for r in results:
            ps = r["per_seed"]
            runs = [{"fes_to_target": x["ftt"], "best": x["best"]} for x in ps]
            srate = core.success_rate(runs)
            nr = core.necessity_ratio(runs, r["budget"])
            gap = core.gap_to_ceiling(runs, r["f_opt"])
            hits = [x["ftt"] for x in ps if x["ftt"] is not None]
            w.writerow([r["family"], r["tag"], r["n"], r["idx"], r["decoder"],
                        r["method"], r["dim"], r["budget"], r["f_opt"],
                        round(srate, 4), nr if nr == float("inf") else round(nr, 5),
                        round(gap, 6), statistics.median(x["best"] for x in ps),
                        round(statistics.median(hits), 1) if hits else ""])
    print(f"\nper-seed -> {ps_path}\nagg      -> {ag_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--jobs", type=int, default=-1)
    a = ap.parse_args()
    if a.quick:
        run(jobs=a.jobs, specs=[("knapsack", "strongly", 30, 0), ("scp", "", 40, 0)],
            methods_list=("floor", "ils", "ga", "mga", "bpso", "bde"), n_seeds=5)
    else:
        run(jobs=a.jobs)
