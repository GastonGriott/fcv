"""fcv.scp_orlib — Set Covering REAL de OR-Library (Beasley), formato estandar.

Formato OR-Library SCP:
  linea 1: m(filas) n(columnas)
  luego: n costos de columna
  luego, por cada fila i: k_i  (numero de columnas que la cubren) y la lista de columnas (1-based)

Techo: se RESUELVE con MILP exacto (HiGHS via scipy) y se cachea en disco; el dict
KNOWN_OPT con los valores publicados queda solo como CONTRASTE, y `load` aborta si
los dos no coinciden. La cota LP sigue disponible como respaldo para instancias que
el MILP no cierre. Objetivo PONDERADO (costos)."""
import os
import urllib.request
import random

from . import exact
from .core import Problem

ORLIB_BASE = "http://people.brunel.ac.uk/~mastjjb/jeb/orlib/files/"
KNOWN_OPT = {"scp41": 429, "scp42": 512, "scp43": 516, "scp44": 494, "scp45": 512,
             "scp46": 560, "scp47": 430, "scp48": 492, "scp49": 641, "scp410": 514}


def download(name):
    url = ORLIB_BASE + name + ".txt"
    req = urllib.request.Request(url, headers={"User-Agent": "fcv/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def parse_scp(text):
    toks = text.split()
    it = iter(toks)
    m = int(next(it)); n = int(next(it))
    costs = [int(next(it)) for _ in range(n)]
    col_rows = [[] for _ in range(n)]      # columnas que cubren cada fila -> por columna
    row_cols = []
    for i in range(m):
        k = int(next(it))
        cols = [int(next(it)) - 1 for _ in range(k)]
        row_cols.append(cols)
        for j in cols:
            col_rows[j].append(i)
    return m, n, costs, row_cols, col_rows


def lp_lower_bound(m, n, costs, row_cols):
    """Cota inferior por relajacion LP: min c.x s.t. cobertura, 0<=x<=1.

    Devuelve None SOLO si el LP no converge, que es informacion real. Que falte
    scipy no es eso: es que la maquina no puede calcular la cota, y confundir las
    dos cosas hacia que `ceiling()` devolviera la constante de penalizacion como si
    fuera el techo, con C3 midiendo el gap contra un numero inventado."""
    import numpy as np
    from scipy.optimize import linprog
    # A_ub x <= b_ub  con  -cobertura x <= -1
    A = np.zeros((m, n))
    for i, cols in enumerate(row_cols):
        for j in cols:
            A[i, j] = -1.0
    b = -np.ones(m)
    res = linprog(c=costs, A_ub=A, b_ub=b, bounds=[(0, 1)] * n, method="highs")
    return float(res.fun) if res.success else None


def greedy_upper_bound(m, n, costs, row_cols, col_rows):
    """Cobertura greedy (costo/cobertura-nueva) -> cota superior factible."""
    covered = [False] * m
    n_unc = m
    chosen, total = [], 0
    col_set = [set(rs) for rs in col_rows]
    while n_unc > 0:
        best_j, best_ratio = None, float("inf")
        for j in range(n):
            new = sum(1 for i in col_set[j] if not covered[i])
            if new > 0:
                ratio = costs[j] / new
                if ratio < best_ratio:
                    best_ratio, best_j = ratio, j
        for i in col_set[best_j]:
            if not covered[i]:
                covered[i] = True; n_unc -= 1
        chosen.append(best_j); total += costs[best_j]
    return total


class SetCoverWeighted(Problem):
    def __init__(self, m, n, costs, row_cols, col_rows, name, opt=None, lp=None):
        self.m, self.n = m, n
        self.costs = costs
        self.col_set = [set(rs) for rs in col_rows]
        self.row_cols = row_cols
        self.name = name
        self.opt = opt
        self.lp = lp
        self.P = sum(costs) + 1

    def random_solution(self, rng):
        return [rng.randint(0, 1) for _ in range(self.n)]

    def neighbors(self, sol):
        for j in range(self.n):
            nb = list(sol); nb[j] ^= 1
            yield nb

    def objective(self, sol):
        covered = set()
        cost = 0
        for j, x in enumerate(sol):
            if x:
                cost += self.costs[j]; covered |= self.col_set[j]
        return cost + self.P * (self.m - len(covered))

    def ceiling(self):
        if self.opt is not None:
            return self.opt, True
        if self.lp is not None:
            return self.lp, False
        raise RuntimeError(
            f"{self.name}: sin optimo publicado y sin cota LP, esta instancia no "
            f"tiene techo. Antes se devolvia la constante de penalizacion "
            f"({self.P}) como techo, y C3 reportaba el gap contra ese numero."
        )

    def space_size(self):
        return 2 ** self.n


DATA_DIR = os.path.join(os.path.dirname(__file__), "data_orlib")


def load(name, allow_download=True):
    """Carga una instancia de OR-Library. Prefiere la copia local de data_orlib/ y
    solo descarga si falta: con 32 workers en paralelo, una descarga por celda
    contra el servidor de Brunel es fragil, y ademas innecesaria porque estas
    instancias son inmutables desde 1990."""
    local = os.path.join(DATA_DIR, name + ".txt")
    if os.path.exists(local):
        text = open(local, encoding="utf-8").read()
    elif allow_download:
        text = download(name)
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(local, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError:
            pass                      # sin cache es mas lento, no incorrecto
    else:
        text = open(name, encoding="utf-8").read()
    m, n, costs, row_cols, col_rows = parse_scp(text)
    # El techo se RESUELVE (MILP exacto, cacheado en disco), no se copia de la tabla
    # publicada: KNOWN_OPT queda solo como contraste. La cota LP era ademas un gasto
    # fijo en cada una de las 32 celdas que cargan la instancia, y con el optimo
    # exacto disponible no hace falta.
    opt = exact.cached(name, "milp-highs",
                       lambda: exact.scp_optimum(m, n, costs, row_cols),
                       m=m, n=n, family="scp_orlib")
    publicado = KNOWN_OPT.get(name)
    if publicado is not None and abs(opt - publicado) > 1e-6:
        raise ValueError(
            f"{name}: el optimo que resuelve el MILP ({opt}) NO coincide con el "
            f"valor publicado ({publicado}). Uno de los dos esta mal y C3 mide "
            f"contra el techo, asi que no se sigue hasta aclararlo.")
    return SetCoverWeighted(m, n, costs, row_cols, col_rows, name, opt=opt, lp=None)
