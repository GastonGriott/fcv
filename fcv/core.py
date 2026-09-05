"""fcv.core — Floor-Ceiling Validation, núcleo del protocolo (stdlib + scipy stats).

Todo se MINIMIZA. Una evaluacion = una llamada a objective() (incluye vecinos del
local search; sin ventaja de presupuesto). Ver FCV.md para la especificacion.
"""
import math
import random
import statistics
import sys
from abc import ABC, abstractmethod


class Problem(ABC):
    """Contrato que implementa cada familia. Objetivo a MINIMIZAR."""
    name = "problem"

    @abstractmethod
    def random_solution(self, rng):
        """Devuelve una solucion (representacion binaria/lista)."""

    @abstractmethod
    def neighbors(self, sol):
        """Itera vecinos (vecindario estandar minimo de la familia)."""

    @abstractmethod
    def objective(self, sol):
        """Valor a minimizar (con penalizacion/reparacion de factibilidad)."""

    @abstractmethod
    def ceiling(self):
        """Devuelve (f_opt, is_exact). Optimo exacto o cota dual con gap."""

    def space_size(self):
        """Cardinalidad del espacio de busqueda (para el eje 'tamano')."""
        return None


class _Counter:
    __slots__ = ("fes",)
    def __init__(self):
        self.fes = 0


def floor_run(problem, budget, seed, f_target, tol=1e-9):
    """Random-restart best-improvement local search (el PISO). Sin tuning.
    Devuelve dict(best, fes_to_target|None, fes_used)."""
    rng = random.Random(seed)
    c = _Counter()

    def ev(sol):
        c.fes += 1
        return problem.objective(sol)

    best = math.inf
    fes_to_target = None
    cur = problem.random_solution(rng)
    cur_f = ev(cur)
    while c.fes < budget:
        # mejor vecino
        improved = False
        best_nb, best_nb_f = None, cur_f
        for nb in problem.neighbors(cur):
            if c.fes >= budget:
                break
            f = ev(nb)
            if f < best_nb_f - 1e-12:
                best_nb_f, best_nb, improved = f, nb, True
        if improved:
            cur, cur_f = best_nb, best_nb_f
        else:
            # optimo local -> reinicio aleatorio
            cur = problem.random_solution(rng)
            cur_f = ev(cur) if c.fes < budget else cur_f
        if cur_f < best:
            best = cur_f
        if fes_to_target is None and best <= f_target + tol:
            fes_to_target = c.fes
            break
    return {"best": best, "fes_to_target": fes_to_target, "fes_used": c.fes}


def run_method(solver_factory, problem, budget, seed, f_target, tol=1e-9):
    """Corre una metaheuristica generica. solver_factory(problem, budget, rng)
    debe devolver un iterable de (fes_acumuladas, mejor_valor) o un dict con
    'best' y 'fes_to_target'. Para el demo usamos floor_run-like adapters."""
    raise NotImplementedError  # se conecta a los solvers reales en F2+


# --------------------------------------------------------------------------- #
# Metricas del protocolo                                                      #
# --------------------------------------------------------------------------- #
def success_rate(runs):
    return sum(1 for r in runs if r["fes_to_target"] is not None) / len(runs)


def necessity_ratio(floor_runs, budget):
    """NR = mediana(FES-to-target del floor) / budget. Si el floor no alcanza
    en algunas corridas, usa solo las exitosas; si ninguna, NR=inf."""
    hits = [r["fes_to_target"] for r in floor_runs if r["fes_to_target"] is not None]
    if not hits:
        return math.inf
    return statistics.median(hits) / budget


def is_floor_trivial(floor_runs, budget, tau=0.05):
    """True si el floor resuelve (SRate=1) en <tau del presupuesto -> la instancia
    no aporta evidencia sobre la necesidad de una metaheuristica."""
    return success_rate(floor_runs) >= 1.0 and necessity_ratio(floor_runs, budget) < tau


def gap_to_ceiling(runs, f_opt):
    """Gap de optimalidad medio: (f - f_opt)/|f_opt| sobre el mejor de cada corrida."""
    if f_opt == 0:
        return statistics.mean(r["best"] - f_opt for r in runs)
    return statistics.mean((r["best"] - f_opt) / abs(f_opt) for r in runs)


def holm(pvals):
    """Holm-Bonferroni. Devuelve lista de p ajustados en el orden original."""
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    adj = [0.0] * m
    run_max = 0.0
    for rank, i in enumerate(idx):
        a = min(1.0, (m - rank) * pvals[i])
        run_max = max(run_max, a)
        adj[i] = run_max
    return adj


def mcnemar_exact(floor_succ, method_succ):
    """Test de McNemar exacto (binomial) sobre indicadores de exito pareados.
    floor_succ, method_succ: listas 0/1 por semilla. Devuelve p (dos colas)."""
    b = sum(1 for f, m in zip(floor_succ, method_succ) if f == 1 and m == 0)  # floor si, metodo no
    c = sum(1 for f, m in zip(floor_succ, method_succ) if f == 0 and m == 1)  # metodo si, floor no
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * p)


def _require_wilcoxon():
    """scipy es dependencia DURA del analisis, no del motor de corrida.

    El motor (floor_run y los solvers) es stdlib puro a proposito, para que corra
    en cualquier VM sin instalar nada. Los tests, en cambio, necesitan scipy — y
    antes esto era un `except: p = 1.0` que devolvia "no significativo" en silencio
    cuando faltaba. Un p=1.0 inventado se lee igual que uno medido, y en esta
    maquina el `python` del PATH resulto ser un 3.13 SIN scipy mientras el 3.12 si
    lo tiene: los diagnosticos salieron todos en 1.0 sin que nada lo dijera.
    Ahora revienta con la instruccion en pantalla."""
    try:
        from scipy.stats import wilcoxon
        return wilcoxon
    except ImportError as e:
        raise ImportError(
            "El analisis estadistico de FCV necesita scipy y este interprete no lo "
            f"tiene ({sys.executable}). Sin el, el test devolveria un p inventado "
            "que se lee igual que uno medido. Corre el analisis con el interprete "
            "que si lo tiene (en esta maquina, Python 3.12) o instala scipy aqui."
        ) from e


def instance_regime(runs_by_method):
    """Regimen de medicion de UNA instancia. Lo fijan los datos, no el autor.

    'target-reachable': algun metodo alcanza el techo en al menos una semilla, asi
    que el evento de exito es observable y C1 se mide contra el techo.
    'budget-bound': nadie lo alcanza nunca. El exito al techo NO es observable, y
    medir C1 ahi da SRate 0 para todos: McNemar empata en cero y devuelve p=1 para
    cualquier par de metodos, por buenos o malos que sean. Un 'no pasa' obtenido
    asi no es evidencia contra el candidato, es ausencia de evidencia.

    runs_by_method: dict metodo -> lista de corridas de esa instancia."""
    for runs in runs_by_method.values():
        if any(r["fes_to_target"] is not None for r in runs):
            return "target-reachable"
    return "budget-bound"


def endogenous_bar(floor_runs):
    """Barra endogena para el regimen budget-bound: la mediana, sobre las semillas,
    del mejor valor que alcanza el PISO. El piso queda por construccion en SRate~0.5,
    que es donde McNemar tiene mas potencia, y la semantica de C1 no se mueve: sigue
    siendo 'le gana al piso en fiabilidad'. Lo unico que cambia es donde esta la
    barra, porque el techo dejo de ser alcanzable dentro del presupuesto."""
    return statistics.median(r["best"] for r in floor_runs)


def success_indicators(runs, bar=None, tol=1e-9):
    """Indicadores 0/1 de exito por semilla. Sin barra, exito = alcanzar el techo
    (regimen target-reachable). Con barra, exito = terminar en o bajo la barra
    (regimen budget-bound)."""
    if bar is None:
        return [1 if r["fes_to_target"] is not None else 0 for r in runs]
    return [1 if r["best"] <= bar + tol else 0 for r in runs]


def floor_dominance(method_runs, floor_runs, bar=None):
    """C1: la metaheuristica debe ganarle al piso en FIABILIDAD.

    La velocidad va como diagnostico secundario y NO gatea la admision: en las
    instancias duras que interesan el SRate del piso ronda cero, asi que casi no
    hay semillas con exito en ambos y un test de velocidad seria estructuralmente
    incapaz de admitir a un metodo cuya ventaja es la fiabilidad. Quien decide es
    'reliability_better' con su p; Holm se aplica despues, sobre la familia.

    bar=None  -> regimen target-reachable: exito = alcanzar el techo; el
                 diagnostico secundario es la velocidad (FES-to-target).
    bar=valor -> regimen budget-bound: exito = terminar en o bajo la barra; como
                 no hay FES-to-target que comparar, el diagnostico secundario pasa
                 a ser la calidad final (Wilcoxon pareado sobre el mejor valor)."""
    f_succ = success_indicators(floor_runs, bar)
    m_succ = success_indicators(method_runs, bar)
    p_rel = mcnemar_exact(f_succ, m_succ)
    srate_m, srate_f = sum(m_succ) / len(m_succ), sum(f_succ) / len(f_succ)

    if bar is None:
        # velocidad: Wilcoxon pareado sobre FES-to-target donde AMBOS tuvieron exito
        pairs = [(rm["fes_to_target"], rf["fes_to_target"])
                 for rm, rf in zip(method_runs, floor_runs)
                 if rm["fes_to_target"] is not None and rf["fes_to_target"] is not None]
        diag = "speed"
    else:
        # calidad final: Wilcoxon pareado sobre el mejor valor, todas las semillas
        pairs = [(rm["best"], rf["best"])
                 for rm, rf in zip(method_runs, floor_runs)]
        diag = "quality"
    p_diag, better = 1.0, None
    if len(pairs) >= 1 and any(a != b for a, b in pairs):
        wilcoxon = _require_wilcoxon()
        a = [p[0] for p in pairs]
        b = [p[1] for p in pairs]
        _, p_diag = wilcoxon(a, b)
        better = "method" if statistics.median(a) < statistics.median(b) else "floor"
    return {
        "srate_method": srate_m, "srate_floor": srate_f,
        "p_reliability": p_rel, "reliability_better": srate_m > srate_f,
        "regime": "target-reachable" if bar is None else "budget-bound",
        "bar": bar, "diagnostic": diag,
        "p_speed": p_diag, "speed_faster": better,   # nombres historicos: no romper
        "p_diagnostic": p_diag, "diagnostic_better": better,
        "n_speed_pairs": len(pairs),
    }


def floor_frontier(dims, srates, full=1.0):
    """Metrica de dificultad operativa: la MENOR dimension donde el SRate del piso
    cae bajo 'full' (= deja de resolver siempre). Es mejor proxy de dificultad que
    log|S|: separa 'grande-pero-facil' (frontier alta o inexistente) de
    'moderado-pero-duro' (frontier baja). Devuelve None si el piso nunca falla en
    el rango probado (problema floor-trivial en toda la escalera)."""
    for d, sr in sorted(zip(dims, srates)):
        if sr < full - 1e-9:
            return d
    return None


def floor_effort_scaling(sizes, median_fes):
    """Ajusta log(FES) ~ k*log(log|S|) + b. Devuelve k (exponente). k<1 sugiere
    'grande pero facil'. sizes = |espacio| por instancia; median_fes = FES-to-opt."""
    xs, ys = [], []
    for s, fe in zip(sizes, median_fes):
        if s and s > 1 and fe and fe > 0:
            xs.append(math.log(math.log(s)))
            ys.append(math.log(fe))
    if len(xs) < 2:
        return None
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den else None
