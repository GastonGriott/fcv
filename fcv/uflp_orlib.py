"""fcv.uflp_orlib — Uncapacitated Facility Location REAL de OR-Library (Beasley).

Archivos cap71..cap134, formato estandar de OR-Library:

    linea 1:  m (plantas)  n (clientes)
    m veces:  capacidad_i  costo_fijo_i
    n veces:  demanda_j  y luego m costos, el de asignar TODA la demanda de j a i

El costo ya viene multiplicado por la demanda ("cost of allocating all of the
demand of customer j to warehouse i"), asi que el modelo es directamente

    f(S) = sum_{i in S} fijo_i + sum_j min_{i in S} c_ji

que es exactamente la clase `uflp.UFLP` que ya usa el estudio: se reusa, no se
duplica. Por que estas instancias valen como UNcapacitated: en cap71 la capacidad
de una sola planta (58268) iguala la demanda total (58268), de modo que cualquier
planta puede servir a todos los clientes y la restriccion de capacidad nunca ata.
Verificado leyendo el archivo, no supuesto.

EL TECHO SE CALCULA, NO SE CITA
-------------------------------
Los optimos de estas instancias circulan como tabla en la literatura, pero una
tabla copiada es una cita que nadie puede reproducir — y si el techo esta mal, C3
esta mal en todas las instancias a la vez. Aca se resuelven de verdad:

  m <= 20  enumeracion de los 2^m subconjuntos (exacto por construccion)
  m >  20  MILP con HiGHS via scipy.optimize.milp

Ambas vias son exactas y una valida a la otra donde se solapan. cap71 da
932615.75 por enumeracion, que coincide con el valor publicado.
"""
import os
import urllib.request

from . import exact
from .uflp import UFLP

ORLIB_BASE = "http://people.brunel.ac.uk/~mastjjb/jeb/orlib/files/"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data_orlib")

# Los tres grupos que la literatura trata como uncapacitated. m crece 16 -> 25 -> 50,
# que es justo lo que interesa: la dimension binaria del problema.
UFLP_GROUPS = {
    "cap7":  ["cap71", "cap72", "cap73", "cap74"],          # m=16, n=50
    "cap10": ["cap101", "cap102", "cap103", "cap104"],      # m=25, n=50
    "cap13": ["cap131", "cap132", "cap133", "cap134"],      # m=50, n=50
}
UFLP_ALL = [nm for g in UFLP_GROUPS.values() for nm in g]


def download(name):
    url = ORLIB_BASE + name + ".txt"
    req = urllib.request.Request(url, headers={"User-Agent": "fcv/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "ignore")


def parse_cap(text):
    """Devuelve (m, n, capacidades, costos_fijos, demandas, costos[n][m])."""
    it = iter(text.split())
    m = int(next(it))
    n = int(next(it))
    caps, fixed = [], []
    for _ in range(m):
        caps.append(float(next(it)))
        fixed.append(float(next(it)))
    demands, cost = [], []
    for _ in range(n):
        demands.append(float(next(it)))
        cost.append([float(next(it)) for _ in range(m)])
    return m, n, caps, fixed, demands, cost


def optimum(name, m, fixed, cost):
    """Optimo exacto, calculado una vez y cacheado en disco por `fcv.exact`."""
    via = ("enumeration" if m <= exact.ENUM_MAX_M else "milp-highs")
    return exact.cached(name, via,
                        lambda: exact.uflp_optimum(m, fixed, cost)[0],
                        m=m, n=len(cost), family="uflp_orlib")


def load(name, allow_download=True):
    """Carga una instancia UFLP de OR-Library. Prefiere la copia local y solo
    descarga si falta: con 32 workers en paralelo, una descarga por celda contra el
    servidor de Brunel es fragil, y ademas innecesaria porque estas instancias son
    inmutables desde 1988."""
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
            pass
    else:
        raise FileNotFoundError(f"falta {local} y la descarga esta deshabilitada")

    m, n, caps, fixed, demands, cost = parse_cap(text)
    # La instancia solo es uncapacitated si una planta sola aguanta toda la demanda.
    # Si algun dia se agrega un grupo capacitated, esto lo caza en vez de dar un
    # optimo que no corresponde al modelo que resolvemos.
    if min(caps) < sum(demands) - 1e-6:
        raise ValueError(
            f"{name}: la planta mas chica (cap {min(caps):.0f}) no cubre la demanda "
            f"total ({sum(demands):.0f}), asi que la capacidad ATA y esta instancia "
            f"no es uncapacitated. El modelo de fcv.uflp no la representa.")

    inst = UFLP(fixed, cost, name=name)
    inst._opt = optimum(name, m, fixed, cost)      # techo exacto, ya calculado
    return inst
