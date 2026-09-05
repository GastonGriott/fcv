"""fcv.knapsack — 0/1 Knapsack como familia FCV. Optimo exacto via DP.

Representacion: vector binario x in {0,1}^n. Objetivo a MINIMIZAR:
    f(x) = -valor(x) + P * max(0, peso(x) - C)
con P grande (penalizacion de sobrepeso). Vecindario: 1-flip. Optimo exacto por
programacion dinamica (pseudo-polinomial, exacto para pesos enteros)."""
import random
from .core import Problem


class Knapsack(Problem):
    def __init__(self, weights, values, capacity, name="knapsack"):
        self.w = list(weights)
        self.v = list(values)
        self.C = capacity
        self.n = len(weights)
        self.name = name
        self.P = 1 + sum(self.v)          # penalizacion > cualquier valor total
        self._opt = None

    def random_solution(self, rng):
        return [rng.randint(0, 1) for _ in range(self.n)]

    def neighbors(self, sol):
        for i in range(self.n):
            nb = list(sol)
            nb[i] ^= 1
            yield nb

    def objective(self, sol):
        val = sum(v for v, x in zip(self.v, sol) if x)
        wt = sum(w for w, x in zip(self.w, sol) if x)
        over = max(0, wt - self.C)
        return -val + self.P * over

    def ceiling(self):
        """Optimo exacto por DP 0/1 (maximiza valor con peso <= C)."""
        if self._opt is None:
            C = self.C
            dp = [0] * (C + 1)
            for w, v in zip(self.w, self.v):
                for cap in range(C, w - 1, -1):
                    cand = dp[cap - w] + v
                    if cand > dp[cap]:
                        dp[cap] = cand
            self._opt = -max(dp)          # como minimizacion: -valor_max
        return self._opt, True

    def space_size(self):
        return 2 ** self.n


def make_instance(n, seed, wmax=100, vmax=100, cap_frac=0.5):
    """Instancia aleatoria reproducible. capacidad = cap_frac * peso total."""
    rng = random.Random(seed)
    w = [rng.randint(1, wmax) for _ in range(n)]
    v = [rng.randint(1, vmax) for _ in range(n)]
    C = max(wmax, int(cap_frac * sum(w)))
    return Knapsack(w, v, C, name=f"kp_n{n}_s{seed}")
