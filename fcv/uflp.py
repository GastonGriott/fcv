"""fcv.uflp — Uncapacitated Facility Location como familia FCV.

Optimo EXACTO por enumeracion de subconjuntos de facilities (factible para
m<=~18, sin necesidad de MILP). Dado un conjunto abierto S, la asignacion optima
es trivial: cada cliente a la facility abierta mas barata. Por eso el optimo se
obtiene enumerando 2^m-1 subconjuntos no vacios.

Representacion: vector binario sobre m facilities. Objetivo a MINIMIZAR:
    f(x) = sum_{j abierta} open_cost[j] + sum_i min_{j abierta} assign_cost[i][j]
    (penalizacion si no hay ninguna abierta)
Vecindario: open/close una facility (1-flip) + swap (cerrar una, abrir otra)."""
import itertools
import random
from .core import Problem


class UFLP(Problem):
    def __init__(self, open_cost, assign_cost, name="uflp"):
        self.f = list(open_cost)              # costo de abrir cada facility
        self.c = [list(row) for row in assign_cost]  # n_clients x m
        self.m = len(open_cost)
        self.n_clients = len(assign_cost)
        self.name = name
        self.PEN = 1 + sum(self.f) + sum(max(row) for row in self.c)
        self._opt = None

    def random_solution(self, rng):
        x = [rng.randint(0, 1) for _ in range(self.m)]
        if not any(x):
            x[rng.randrange(self.m)] = 1
        return x

    def neighbors(self, sol):
        opened = [j for j, x in enumerate(sol) if x]
        closed = [j for j, x in enumerate(sol) if not x]
        for j in range(self.m):               # 1-flip open/close
            nb = list(sol)
            nb[j] ^= 1
            yield nb
        for a in opened:                       # swap
            for b in closed:
                nb = list(sol)
                nb[a], nb[b] = 0, 1
                yield nb

    def _cost_of_set(self, opened):
        if not opened:
            return self.PEN
        cost = sum(self.f[j] for j in opened)
        for i in range(self.n_clients):
            cost += min(self.c[i][j] for j in opened)
        return cost

    def objective(self, sol):
        return self._cost_of_set([j for j, x in enumerate(sol) if x])

    def ceiling(self):
        if self._opt is None:
            best = self.PEN
            for r in range(1, self.m + 1):
                for combo in itertools.combinations(range(self.m), r):
                    cst = self._cost_of_set(combo)
                    if cst < best:
                        best = cst
            self._opt = best
        return self._opt, True

    def space_size(self):
        return 2 ** self.m


def make_instance(m, seed, n_clients=None, fmax=50, cmax=100):
    rng = random.Random(seed)
    if n_clients is None:
        n_clients = 2 * m
    f = [rng.randint(fmax // 2, fmax) for _ in range(m)]
    c = [[rng.randint(1, cmax) for _ in range(m)] for _ in range(n_clients)]
    return UFLP(f, c, name=f"uflp_m{m}_s{seed}")
