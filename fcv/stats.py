"""fcv.stats — bateria estadistica no-parametrica grado-publicacion (Derrac et al.
2011, DOI 10.1016/j.swevo.2011.02.002; Garcia et al. 2010, DOI 10.1016/j.ins.2009.
12.010). Friedman omnibus + rankings promedio + post-hoc Nemenyi (diagrama CD) y
Holm 1xN contra un control, mas tamanos de efecto. Datos: matriz problemas x
algoritmos de un escalar de desempeño (menor = mejor)."""
import math
import statistics
import sys


def average_ranks(matrix):
    """matrix[p][a] = desempeño (menor mejor) del algoritmo a en el problema p.
    Devuelve ranks promedio por algoritmo (1 = mejor), manejando empates (rank medio)."""
    P = len(matrix); A = len(matrix[0])
    acc = [0.0] * A
    for row in matrix:
        order = sorted(range(A), key=lambda a: row[a])
        ranks = [0.0] * A
        i = 0
        while i < A:
            j = i
            while j + 1 < A and abs(row[order[j + 1]] - row[order[i]]) < 1e-12:
                j += 1
            avg = sum(range(i + 1, j + 2)) / (j - i + 1)   # ranks 1-based promediados
            for k in range(i, j + 1):
                ranks[order[k]] = avg
            i = j + 1
        for a in range(A):
            acc[a] += ranks[a]
    return [s / P for s in acc]


def friedman(matrix):
    """Test de Friedman. Devuelve (estadistico, p, ranks_promedio). Usa scipy si
    esta; si no, aproximacion chi2 con la formula estandar."""
    P = len(matrix); A = len(matrix[0])
    ranks = average_ranks(matrix)
    try:
        from scipy.stats import friedmanchisquare
    except ImportError as e:
        # La formula cerrada NO corrige por empates y aca hay muchos (el SRate toma
        # pocos valores distintos): sobre los 81 problemas del estudio da 185.8
        # contra los 247.4 de scipy, y encima sin p. Devolver eso en silencio hacia
        # que dos corridas del mismo script dieran estadisticos distintos segun el
        # interprete que la lanzara.
        raise ImportError(
            f"friedman() necesita scipy y este interprete no lo tiene "
            f"({sys.executable}). La aproximacion sin correccion por empates da un "
            f"estadistico distinto (185.8 vs 247.4 en el estudio) y ningun p-valor."
        ) from e
    cols = [[matrix[p][a] for p in range(P)] for a in range(A)]
    stat, p = friedmanchisquare(*cols)
    return stat, p, ranks


# q_alpha (studentized range / sqrt(2)) para Nemenyi, alpha=0.05, k=2..12
_Q05 = {2: 1.960, 3: 2.343, 4: 2.569, 5: 2.728, 6: 2.850, 7: 2.949,
        8: 3.031, 9: 3.102, 10: 3.164, 11: 3.219, 12: 3.268}
_Q10 = {2: 1.645, 3: 2.052, 4: 2.291, 5: 2.460, 6: 2.589, 7: 2.693,
        8: 2.780, 9: 2.855, 10: 2.920, 11: 2.978, 12: 3.030}


def nemenyi_cd(k, N, alpha=0.05):
    """Critical Difference de Nemenyi: CD = q_alpha * sqrt(k(k+1)/(6N)).
    k = nº algoritmos, N = nº problemas. Dos ranks que difieren < CD no son
    significativamente distintos."""
    q = (_Q05 if alpha == 0.05 else _Q10).get(k)
    if q is None:
        return None
    return q * math.sqrt(k * (k + 1) / (6.0 * N))


def wilcoxon_effect(a, b):
    """Wilcoxon signed-rank pareado + tamaño de efecto rank-biserial r. Devuelve
    dict(p, r, R_plus, R_minus, median_diff). a,b listas pareadas (menor mejor)."""
    diffs = [(x - y) for x, y in zip(a, b) if abs(x - y) > 1e-12]
    n = len(diffs)
    if n == 0:
        return {"p": 1.0, "r": 0.0, "R_plus": 0.0, "R_minus": 0.0, "median_diff": 0.0}
    order = sorted(range(n), key=lambda i: abs(diffs[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(abs(diffs[order[j + 1]]) - abs(diffs[order[i]])) < 1e-12:
            j += 1
        avg = sum(range(i + 1, j + 2)) / (j - i + 1)
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    Rp = sum(ranks[i] for i in range(n) if diffs[i] > 0)
    Rm = sum(ranks[i] for i in range(n) if diffs[i] < 0)
    total = Rp + Rm
    r = (Rp - Rm) / total if total else 0.0           # rank-biserial
    try:
        from scipy.stats import wilcoxon
    except ImportError as e:
        raise ImportError(
            f"wilcoxon_effect() necesita scipy y este interprete no lo tiene "
            f"({sys.executable}). Antes devolvia p=1.0, que se lee como 'no "
            f"significativo' medido cuando en realidad no se midio nada."
        ) from e
    _, p = wilcoxon(a, b)
    return {"p": p, "r": r, "R_plus": Rp, "R_minus": Rm,
            "median_diff": statistics.median([x - y for x, y in zip(a, b)])}


def holm(pvals):
    """Holm-Bonferroni. p ajustados en orden original (igual a core.holm)."""
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals); adj = [0.0] * m; run = 0.0
    for rank, i in enumerate(idx):
        run = max(run, min(1.0, (m - rank) * pvals[i]))
        adj[i] = run
    return adj


def cd_diagram(names, ranks, cd, path):
    """Dibuja un diagrama de Critical Difference (Demsar). Guarda PNG en path."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        return f"matplotlib no disponible: {e}"
    order = sorted(range(len(names)), key=lambda i: ranks[i])
    lo, hi = math.floor(min(ranks)), math.ceil(max(ranks))
    fig, ax = plt.subplots(figsize=(7.0, 0.6 * len(names) + 1.4))
    ax.set_xlim(lo, hi); ax.set_ylim(0, len(names) + 1)
    ax.plot([lo, hi], [len(names) + 0.5] * 2, "k-", lw=1)
    for x in range(lo, hi + 1):
        ax.plot([x, x], [len(names) + 0.45, len(names) + 0.5], "k-", lw=1)
        ax.text(x, len(names) + 0.7, str(x), ha="center", fontsize=8)
    for rank, oi in enumerate(order):
        y = len(names) - rank
        ax.plot([ranks[oi], ranks[oi]], [y, len(names) + 0.5], "k-", lw=0.8)
        ax.plot([ranks[oi], lo if ranks[oi] < (lo + hi) / 2 else hi], [y, y], "k-", lw=0.8)
        ax.text(lo - 0.05 if ranks[oi] < (lo + hi) / 2 else hi + 0.05, y,
                f"{names[oi]} ({ranks[oi]:.2f})",
                ha="right" if ranks[oi] < (lo + hi) / 2 else "left",
                va="center", fontsize=9)
    if cd:
        ax.plot([lo, lo + cd], [0.6, 0.6], "k-", lw=3)
        ax.text(lo + cd / 2, 0.9, f"CD={cd:.2f}", ha="center", fontsize=8)
    ax.axis("off")
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)
    return path
