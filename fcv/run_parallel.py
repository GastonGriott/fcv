"""fcv.run_parallel — corre la grilla FCV en paralelo (ProcessPoolExecutor) con
cache firmado resumible. Mirror del run_cli.py de tmlpa-pufferfish, adaptado al
contrato fcv.Problem. Celda = (familia, tamano, instancia, metodo).

Uso:  python -m fcv.run_parallel            # grilla por defecto
      python -m fcv.run_parallel --quick    # grilla chica (smoke)
Pensado para correr en Colab: import fcv.run_parallel; run(jobs=-1).
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import statistics

from . import core, methods, knapsack, scp, uflp

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "_cache")
N_SEEDS = 15
BUDGET_MULT = 10000

# registros (picklables por nombre)
FAMILIES = {
    "knapsack": knapsack.make_instance,
    "scp":      scp.make_instance,
    "uflp":     uflp.make_instance,
}
METHODS = {
    "floor": core.floor_run,      # piso minimo (RR best-improvement 1-flip)
    "ils":   methods.ils_run,     # piso fuerte
    "ga":    methods.ga_run,
}
# grilla por defecto: tamanos por familia (dim de busqueda)
GRID = {
    "knapsack": [20, 30, 40, 50, 60],
    "scp":      [40, 60, 90],
    "uflp":     [12, 16, 18],
}
INSTANCES_PER_SIZE = 5


def _sig(family, size, idx, method, n_seeds):
    return hashlib.sha1(
        f"{family}|{size}|{idx}|{method}|{n_seeds}|{BUDGET_MULT}|v1".encode()
    ).hexdigest()[:16]


def _cache_path(family, size, idx, method, n_seeds):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{family}_{size}_{idx}_{method}_n{n_seeds}.json")


def _cell(task):
    family, size, idx, method, n_seeds = task
    path = _cache_path(family, size, idx, method, n_seeds)
    sig = _sig(family, size, idx, method, n_seeds)
    if os.path.exists(path):
        try:
            d = json.load(open(path, encoding="utf-8"))
            if d.get("sig") == sig:
                return d["res"]
        except Exception:
            pass
    inst = FAMILIES[family](size, seed=10_000 * size + idx)
    f_opt, _ = inst.ceiling()
    import random
    dim = len(inst.random_solution(random.Random(0)))
    budget = BUDGET_MULT * dim
    fn = METHODS[method]
    runs = [fn(inst, budget, s, f_opt) for s in range(n_seeds)]
    res = {
        "family": family, "size": size, "idx": idx, "method": method,
        "dim": dim, "budget": budget, "f_opt": f_opt,
        "srate": core.success_rate(runs),
        "nr": core.necessity_ratio(runs, budget),
        "gap": core.gap_to_ceiling(runs, f_opt),
    }
    tmp = path + ".tmp"
    json.dump({"sig": sig, "res": res}, open(tmp, "w", encoding="utf-8"))
    os.replace(tmp, path)
    return res


def build_tasks(grid=GRID, instances=INSTANCES_PER_SIZE, n_seeds=N_SEEDS,
                methods_list=("floor", "ils", "ga")):
    tasks = []
    for fam, sizes in grid.items():
        for size in sizes:
            for idx in range(instances):
                for m in methods_list:
                    tasks.append((fam, size, idx, m, n_seeds))
    return tasks


def run(jobs=None, grid=GRID, instances=INSTANCES_PER_SIZE, n_seeds=N_SEEDS,
        methods_list=("floor", "ils", "ga"), out_csv=None):
    tasks = build_tasks(grid, instances, n_seeds, methods_list)
    if not jobs or jobs < 1:
        jobs = max(1, (os.cpu_count() or 2))
    print(f"FCV grid: {len(tasks)} celdas, {jobs} workers (cpu={os.cpu_count()})")
    results = []
    with cf.ProcessPoolExecutor(max_workers=jobs) as ex:
        for i, r in enumerate(ex.map(_cell, tasks), 1):
            results.append(r)
            if i % 10 == 0 or i == len(tasks):
                print(f"  {i}/{len(tasks)}")
    # agregar por (familia, tamano, metodo): SRate medio sobre instancias
    agg = {}
    for r in results:
        key = (r["family"], r["size"], r["method"])
        agg.setdefault(key, []).append(r)
    rows = []
    for (fam, size, m), rs in sorted(agg.items()):
        rows.append({
            "family": fam, "size": size, "method": m,
            "mean_srate": round(statistics.mean(x["srate"] for x in rs), 3),
            "mean_nr": round(statistics.mean(x["nr"] for x in rs if x["nr"] != float("inf")) , 4)
                       if any(x["nr"] != float("inf") for x in rs) else "inf",
            "mean_gap": round(statistics.mean(x["gap"] for x in rs), 5),
            "n_inst": len(rs),
        })
    # frontera floor-fail por (familia, metodo): menor tamano con mean_srate<1
    print("\nfamily  size  method  meanSRate  meanNR  meanGap")
    for r in rows:
        print(f"  {r['family']:>9} {r['size']:>4} {r['method']:>6} "
              f"{r['mean_srate']:>9} {str(r['mean_nr']):>8} {r['mean_gap']:>8}")
    if out_csv:
        import csv
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print(f"\nCSV -> {out_csv}")
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--jobs", type=int, default=-1)
    a = ap.parse_args()
    if a.quick:
        run(jobs=a.jobs, grid={"knapsack": [10, 20]}, instances=3, n_seeds=5,
            methods_list=("floor",), out_csv=None)
    else:
        run(jobs=a.jobs, out_csv=os.path.join(os.path.dirname(__file__), "..", "fcv_grid.csv"))
