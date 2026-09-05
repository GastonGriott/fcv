"""fcv.decoders — control del decoder (penalty vs repair) para responder la critica
adversarial mas fuerte: "la dificultad que reportas es artefacto del decoder, no del
problema". Diseno: fijar vecindario, presupuesto, instancias y seeds; variar SOLO el
mecanismo de manejo de restricciones, y medir cuanto se mueve la frontera floor-fail.

  - PENALTY (base): la familia original con f(x) = costo + P*violacion.
  - REPAIR (Baldwiniano): se evalua la solucion REPARADA (siempre factible); el
    genotipo en la poblacion no se reescribe (los metodos solo usan .objective).

Repair knapsack: DROP por value-density ascendente hasta factible + ADD greedy
(Chu-Beasley, DOI 10.1023/A:1009642405419). Repair SCP: ADD greedy por costo/
cobertura-nueva + REMOVE de columnas redundantes (Beasley-Chu 1996,
DOI 10.1016/0377-2217(95)00159-X). Precedente del diseño de control: Ishibuchi 2005
(Lamarckian vs Baldwinian, DOI 10.1007/978-3-540-31880-4_26); taxonomia Coello 2002
(DOI 10.1016/S0045-7825(01)00323-1)."""
from .core import Problem


def repair_knapsack(kp, x):
    """Devuelve un genotipo binario FACTIBLE para la instancia Knapsack kp."""
    chosen = set(i for i, b in enumerate(x) if b)
    wt = sum(kp.w[i] for i in chosen)
    if wt > kp.C:                                   # DROP por menor value-density
        for i in sorted(chosen, key=lambda i: kp.v[i] / kp.w[i]):
            if wt <= kp.C:
                break
            chosen.discard(i); wt -= kp.w[i]
    # ADD greedy por value-density descendente
    for i in sorted((i for i in range(kp.n) if i not in chosen),
                    key=lambda i: -kp.v[i] / kp.w[i]):
        if wt + kp.w[i] <= kp.C:
            chosen.add(i); wt += kp.w[i]
    out = [0] * kp.n
    for i in chosen:
        out[i] = 1
    return out


def repair_scp(sc, x):
    """Devuelve un genotipo binario FACTIBLE (cobertura total) para SetCoverWeighted."""
    chosen = set(j for j, b in enumerate(x) if b)
    cov_count = [0] * sc.m
    for j in chosen:
        for i in sc.col_set[j]:
            cov_count[i] += 1
    uncovered = set(i for i in range(sc.m) if cov_count[i] == 0)
    # ADD greedy por costo/cobertura-nueva
    while uncovered:
        best_j, best_ratio = None, float("inf")
        for j in range(sc.n):
            if j in chosen:
                continue
            new = len(sc.col_set[j] & uncovered)
            if new > 0:
                ratio = sc.costs[j] / new
                if ratio < best_ratio:
                    best_ratio, best_j = ratio, j
        if best_j is None:
            break
        chosen.add(best_j)
        for i in sc.col_set[best_j]:
            cov_count[i] += 1
        uncovered -= sc.col_set[best_j]
    # REMOVE columnas redundantes (mayor costo primero)
    for j in sorted(chosen, key=lambda j: -sc.costs[j]):
        if all(cov_count[i] >= 2 for i in sc.col_set[j]):
            chosen.discard(j)
            for i in sc.col_set[j]:
                cov_count[i] -= 1
    out = [0] * sc.n
    for j in chosen:
        out[j] = 1
    return out


class RepairProblem(Problem):
    """Envuelve una familia para usar decoder de REPARACION (Baldwiniano). objective
    repara y puntua la solucion factible (sin penalizacion). decode() expone el
    fenotipo reparado. El resto delega en la base => mismo vecindario y techo."""
    def __init__(self, base, repair_fn, cost_fn):
        self.base = base
        self.repair_fn = repair_fn
        self.cost_fn = cost_fn
        self.name = base.name + "+repair"

    def random_solution(self, rng):
        return self.base.random_solution(rng)

    def neighbors(self, sol):
        return self.base.neighbors(sol)

    def decode(self, sol):
        return self.repair_fn(self.base, sol)

    def objective(self, sol):
        return self.cost_fn(self.base, self.repair_fn(self.base, sol))

    def ceiling(self):
        return self.base.ceiling()

    def space_size(self):
        return self.base.space_size()


def repair_scp_planted(sc, x):
    """Repair para SetCover plantado (unicost): ADD greedy por max cobertura-nueva
    (sin señal de costo) + REMOVE de columnas redundantes. sc.columns = frozensets."""
    chosen = set(j for j, b in enumerate(x) if b)
    cov_count = [0] * sc.n_rows
    for j in chosen:
        for i in sc.columns[j]:
            cov_count[i] += 1
    uncovered = set(i for i in range(sc.n_rows) if cov_count[i] == 0)
    while uncovered:
        best_j, best_new = None, 0
        for j in range(sc.n_cols):
            if j in chosen:
                continue
            new = len(sc.columns[j] & uncovered)
            if new > best_new:
                best_new, best_j = new, j
        if best_j is None:
            break
        chosen.add(best_j)
        for i in sc.columns[best_j]:
            cov_count[i] += 1
        uncovered -= sc.columns[best_j]
    for j in sorted(chosen):
        if all(cov_count[i] >= 2 for i in sc.columns[j]):
            chosen.discard(j)
            for i in sc.columns[j]:
                cov_count[i] -= 1
    out = [0] * sc.n_cols
    for j in chosen:
        out[j] = 1
    return out


def _kp_cost(kp, x):
    return -sum(v for v, b in zip(kp.v, x) if b)          # factible => sin penalizacion


def _scp_cost(sc, x):
    return sum(c for c, b in zip(sc.costs, x) if b)


def _scp_planted_cost(sc, x):
    return sum(1 for b in x if b)                          # unicost: nº de columnas


def with_repair(problem):
    """Devuelve la version REPAIR de un Knapsack, SetCoverWeighted o SetCover (plantado)."""
    from .knapsack import Knapsack
    from .scp_orlib import SetCoverWeighted
    from .scp import SetCover
    if isinstance(problem, Knapsack):
        return RepairProblem(problem, repair_knapsack, _kp_cost)
    if isinstance(problem, SetCoverWeighted):
        return RepairProblem(problem, repair_scp, _scp_cost)
    if isinstance(problem, SetCover):
        return RepairProblem(problem, repair_scp_planted, _scp_planted_cost)
    raise TypeError(f"sin decoder de repair para {type(problem).__name__}")
