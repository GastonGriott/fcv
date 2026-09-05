"""Parte el per-seed de la corrida SCP OR-Library en sus dos clases de densidad.

Las clases `scp4` (2 % de densidad de cobertura) y `scp6` (5 %) tienen la MISMA
dimension (200 filas x 1000 columnas) pero optimos en escalas distintas -- 429-641
contra 131-161 -- asi que sus gaps porcentuales NO son comparables entre si. El paper
(§5, tabla `tab:setcov`) las reporta en filas separadas por eso, y estas son las
cifras que sostienen esa tabla.

Uso, desde proyectos/iaa-tema2/corrida_poa/ y con Python 3.12 (el 3.13 del PATH no
tiene scipy y `analyze_admision.py` aborta):

    py -3.12 split_clases_scp.py
    py -3.12 analyze_admision.py --perseed _tmp_scp4_perseed.csv --methods ga,mga
    py -3.12 analyze_admision.py --perseed _tmp_scp6_perseed.csv --methods ga,mga

Los `_tmp_*.csv` son derivados desechables: no se versionan.
"""
import csv, sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

SRC = "fcv_v2_floor_ils_ga_mga_orlib_scp_perseed.csv"
rows = list(csv.DictReader(open(SRC, newline="")))
assert rows, "perseed vacio"

CLASES = {
    "scp4": {"scp41", "scp42", "scp43", "scp44", "scp45",
             "scp46", "scp47", "scp48", "scp49", "scp410"},
    "scp6": {"scp61", "scp62", "scp63", "scp64", "scp65"},
}

# control: la union de las clases debe ser exactamente el set de tags del CSV
tags_csv = {r["tag"] for r in rows}
union = set().union(*CLASES.values())
assert union == tags_csv, f"clases no cubren el CSV: falta {tags_csv - union}, sobra {union - tags_csv}"

for nombre, keep in CLASES.items():
    sub = [r for r in rows if r["tag"] in keep]
    assert len(sub) == len(keep) * 4 * 31, f"{nombre}: {len(sub)} filas, esperaba {len(keep)*4*31}"
    out = f"_tmp_{nombre}_perseed.csv"
    w = csv.DictWriter(open(out, "w", newline=""), fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(sub)
    print(f"{nombre}: {len(keep)} instancias, {len(sub)} filas -> {out}")
