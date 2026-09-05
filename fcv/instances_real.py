"""fcv.instances_real — instancias benchmark DURAS de la literatura (no plantadas).

Knapsack 0/1: generadores de Pisinger (Where are the hard knapsack problems?,
Computers & OR 2005, DOI 10.1016/j.cor.2004.03.002). Las clases correlacionadas
son genuinamente duras para busqueda local (gran gap LP-IP + 'core' plano: los
pesos en cualquier ventana ordenada por eficiencia varian poco, asi que los 1-flip
casi nunca mejoran respetando la capacidad). El optimo es EXACTO via DP (la clase
Knapsack ya lo provee; DP no se afecta por la correlacion). Mantenemos R=1000 para
que el DP sea tratable en stdlib; cap_frac=0.5 (el regimen mas duro).

Uso: knap_class("strongly", n=200, seed=0) -> Knapsack lista para FCV."""
import hashlib
import random
from .knapsack import Knapsack

R_DEFAULT = 1000


def _capacity(w, cap_frac):
    return max(max(w), int(cap_frac * sum(w)))


def _kind_seed(kind):
    """Entero determinista a partir del nombre de clase. NO usar hash(): Python
    aleatoriza hash() de str por proceso (PYTHONHASHSEED), lo que generaria
    instancias distintas para el mismo (clase,n,idx) en cada worker."""
    return int.from_bytes(hashlib.sha1(kind.encode()).digest()[:4], "big")


def knap_class(kind, n, seed, R=R_DEFAULT, cap_frac=0.5):
    """Genera una instancia knapsack de la clase de dureza dada (Pisinger).
    kind in {uncorrelated, weakly, strongly, inverse, subsetsum, mstr, spanner}.
    Reproducible entre procesos (seed determinista, sin hash() de str)."""
    rng = random.Random((_kind_seed(kind) ^ (n * 100003) ^ (seed * 7919)) & 0x7fffffff)
    if kind == "uncorrelated":
        w = [rng.randint(1, R) for _ in range(n)]
        v = [rng.randint(1, R) for _ in range(n)]
    elif kind == "weakly":
        w = [rng.randint(1, R) for _ in range(n)]
        v = [max(1, wj + rng.randint(-R // 10, R // 10)) for wj in w]
    elif kind == "strongly":
        w = [rng.randint(1, R) for _ in range(n)]
        v = [wj + R // 10 for wj in w]
    elif kind == "inverse":
        v = [rng.randint(1, R) for _ in range(n)]
        w = [vj + R // 10 for vj in v]
    elif kind == "subsetsum":
        w = [rng.randint(1, R) for _ in range(n)]
        v = list(w)
    elif kind == "mstr":                     # multiple strongly correlated mstr(3R/10,2R/10,6)
        k1, k2, d = 3 * R // 10, 2 * R // 10, 6
        w = [rng.randint(1, R) for _ in range(n)]
        v = [wj + (k1 if wj % d == 0 else k2) for wj in w]
    elif kind == "spanner":                  # span(2,10) base strongly correlated
        m, vspan = 10, 2
        sw = [rng.randint(1, R) for _ in range(vspan)]
        sv = [wj + R // 10 for wj in sw]
        sw = [max(1, x // (m + 1)) for x in sw]
        sv = [max(1, x // (m + 1)) for x in sv]
        w, v = [], []
        for _ in range(n):
            k = rng.randrange(vspan)
            a = rng.randint(1, m)
            w.append(a * sw[k]); v.append(a * sv[k])
    else:
        raise ValueError(f"clase knapsack desconocida: {kind}")
    C = _capacity(w, cap_frac)
    return Knapsack(w, v, C, name=f"kp_{kind}_n{n}_s{seed}")


# Clases recomendadas para el estudio: control facil + duras
KNAP_CLASSES_EASY = ["uncorrelated"]
KNAP_CLASSES_HARD = ["strongly", "inverse", "mstr", "spanner"]
KNAP_CLASSES_ALL = KNAP_CLASSES_EASY + KNAP_CLASSES_HARD
