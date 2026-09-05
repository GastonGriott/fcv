"""Reconstruye el CSV per-seed desde los .json del cache de `fcv.run_v2`.

Para que sirve
--------------
`run_v2` escribe los CSV recien cuando TODAS las celdas terminaron. El cache, en
cambio, se escribe celda por celda y se sincroniza a GCS cada 10 min. Cuando una
corrida larga tiene una parte lista y otra en curso —o cuando se decide cortarla—,
este script arma el CSV con lo que ya existe, en el MISMO formato que produce
`run_v2._write_outputs`, de modo que `analyze_admision.py` lo consume sin cambios.

No inventa nada: cada fila sale de un `per_seed` ya calculado y cacheado. Las
celdas que no estan en el cache simplemente no aparecen, y el chequeo de
integridad de `analyze_admision.py` se encarga de que su ausencia no pase
inadvertida.

Uso:
    python cache_to_csv.py <dir_cache> <salida.csv>
"""
import csv
import json
import os
import sys

COLS = ["family", "tag", "n", "idx", "decoder", "method", "dim",
        "budget", "f_opt", "exact", "seed", "best", "ftt", "fes"]


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, out = sys.argv[1], sys.argv[2]
    if not os.path.isdir(src):
        sys.exit(f"no existe el directorio de cache: {src}")

    filas, celdas, metodos = [], 0, {}
    for nombre in sorted(os.listdir(src)):
        if not nombre.endswith(".json"):
            continue
        with open(os.path.join(src, nombre), encoding="utf-8") as fh:
            d = json.load(fh)
        r = d.get("res")
        if r is None:                       # cache de otra version del formato
            print(f"  !! {nombre}: sin clave 'res', se omite")
            continue
        celdas += 1
        metodos[r["method"]] = metodos.get(r["method"], 0) + 1
        for s in r["per_seed"]:
            filas.append([r["family"], r["tag"], r["n"], r["idx"], r["decoder"],
                          r["method"], r["dim"], r["budget"], r["f_opt"],
                          r["exact"], s["seed"], s["best"],
                          "" if s["ftt"] is None else s["ftt"], s["fes"]])

    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        w.writerows(filas)

    print(f"{celdas} celdas -> {len(filas)} filas en {out}")
    for m, c in sorted(metodos.items()):
        print(f"    {m:6s} {c} celdas")


if __name__ == "__main__":
    main()
