"""fcv.exact — el TECHO del protocolo, calculado y no citado.

C3 mide la distancia al techo, asi que un techo equivocado equivoca C3 en todas
las instancias a la vez. Los optimos de OR-Library circulan como tabla copiada de
paper en paper; aca se resuelven con un solver exacto y la tabla publicada queda
como contraste, no como fuente.

Todo lo que se calcula se cachea en disco junto a los datos, con la VIA anotada,
para que el paper pueda declarar como se obtuvo cada techo sin volver a correrlo
y para que los 32 workers de la corrida no lo recalculen uno por uno.
"""
import itertools
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data_orlib")
CACHE = os.path.join(DATA_DIR, "_optima.json")


def _load():
    if os.path.exists(CACHE):
        try:
            return json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            pass                          # cache corrupto: se recalcula, no se miente
    return {}


def _save(d):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = CACHE + ".tmp"
        json.dump(d, open(tmp, "w", encoding="utf-8"), indent=1, sort_keys=True)
        os.replace(tmp, CACHE)
    except OSError:
        pass                              # sin cache es mas lento, no incorrecto


def cached(name, via, compute, **meta):
    """Devuelve el optimo de `name`, calculandolo una sola vez."""
    d = _load()
    if name in d:
        return d[name]["opt"]
    opt = compute()
    d[name] = dict(opt=opt, via=via, **meta)
    _save(d)
    return opt


def provenance(name):
    """Como se obtuvo el techo de esta instancia. Para declararlo en el paper."""
    return _load().get(name)


# --------------------------------------------------------------------------- #
# Set covering: min c.x  s.t.  A x >= 1,  x binaria                           #
# --------------------------------------------------------------------------- #
def scp_optimum(m, n, costs, row_cols, integer_costs=True):
    import numpy as np
    from scipy.optimize import milp, LinearConstraint, Bounds
    A = np.zeros((m, n))
    for i, cols in enumerate(row_cols):
        for j in cols:
            A[i, j] = 1.0
    res = milp(c=np.asarray(costs, dtype=float),
               constraints=LinearConstraint(A, lb=1),
               integrality=np.ones(n), bounds=Bounds(0, 1))
    if not res.success:
        raise RuntimeError(f"MILP del set covering no cerro: {res.message}")
    # con costos enteros el optimo es entero: el solver devuelve 138.00000000000003
    # y ese ruido de coma flotante se propagaria al gap de C3.
    return round(res.fun) if integer_costs else float(res.fun)


# --------------------------------------------------------------------------- #
# UFLP:  f(S) = sum_{i in S} fijo_i + sum_j min_{i in S} c_ji                  #
# --------------------------------------------------------------------------- #
ENUM_MAX_M = 20      # sobre esto, 2^m deja de ser razonable en Python puro


def uflp_optimum_enumerate(m, fixed, cost):
    """Exacto por enumeracion de los subconjuntos no vacios."""
    n = len(cost)
    best = float("inf")
    for r in range(1, m + 1):
        for S in itertools.combinations(range(m), r):
            c = sum(fixed[j] for j in S) + sum(min(cost[i][j] for j in S)
                                               for i in range(n))
            if c < best:
                best = c
    return best


def uflp_optimum_milp(m, fixed, cost):
    """Exacto por MILP (HiGHS). y_i binaria (abrir planta i), x_ij continua en
    [0,1]: dada y, la asignacion optima ya es entera, asi que relajar x no pierde
    exactitud y le saca mucho trabajo al solver."""
    import numpy as np
    from scipy.optimize import milp, LinearConstraint, Bounds
    n = len(cost)
    nv = m + m * n

    def xi(i, j):
        return m + i * n + j

    c = np.zeros(nv)
    c[:m] = fixed
    for i in range(m):
        for j in range(n):
            c[xi(i, j)] = cost[j][i]      # cost esta indexado [cliente][planta]

    A_eq = np.zeros((n, nv))              # cada cliente, exactamente una planta
    for j in range(n):
        for i in range(m):
            A_eq[j, xi(i, j)] = 1.0
    A_le = np.zeros((m * n, nv))          # x_ij <= y_i
    for i in range(m):
        for j in range(n):
            A_le[i * n + j, xi(i, j)] = 1.0
            A_le[i * n + j, i] = -1.0

    integrality = np.zeros(nv)
    integrality[:m] = 1
    res = milp(c=c,
               constraints=[LinearConstraint(A_eq, lb=1, ub=1),
                            LinearConstraint(A_le, ub=0)],
               integrality=integrality, bounds=Bounds(0, 1))
    if not res.success:
        raise RuntimeError(f"MILP del UFLP no cerro: {res.message}")
    return float(res.fun)


def uflp_optimum(m, fixed, cost):
    """Enumeracion si m es chico, MILP si no. Las dos vias son exactas y coinciden
    donde se solapan."""
    if m <= ENUM_MAX_M:
        return uflp_optimum_enumerate(m, fixed, cost), "enumeration"
    return uflp_optimum_milp(m, fixed, cost), "milp-highs"
