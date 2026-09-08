"""fcv.methods — metaheuristicas binarias genericas con el MISMO conteo de FES
que el piso (floor_run). Devuelven dict(best, fes_to_target, fes_used).

Diseño FACTORIAL para responder la critica "tu GA no-memetico vs ILS memetico es
strawman": cada metodo poblacional tiene variante vanilla y memetica (flag
`memetic`) que comparte el MISMO operador de busqueda local (`_descend`,
first-improvement 1-flip) y el MISMO presupuesto de FES que el piso fuerte (ILS).

Paradigmas (genericos sobre cualquier Problem con representacion binaria 0/1):
  - GA  : torneo + cruce uniforme + bit-flip + elitismo        (Beasley-Chu-like)
  - bPSO: binary PSO con transfer V-shaped (Mirjalili 2013)     V2: |tanh(v)|
  - bDE : binary DE con probability-estimation operator (NMBDE, Wang 2012)
Refs: Kennedy-Eberhart 1997 (10.1109/ICSMC.1997.637339); Mirjalili 2013
(10.1016/j.swevo.2012.09.002); Wang 2012 NMBDE (10.1016/j.neucom.2011.11.033);
Neri-Cotta 2012 memetic review (10.1016/j.swevo.2011.11.003)."""
import math
import random


class _C:
    __slots__ = ("fes",)
    def __init__(self):
        self.fes = 0


def _descend(problem, x, fx, ev, budget, c, full=True):
    """Operador de busqueda local COMPARTIDO: first-improvement sobre el vecindario
    1-flip hasta optimo local (full=True) o un solo barrido (full=False). Cuenta
    FES via ev/c. Es el mismo operador que usa ILS, asi la comparacion memetica es
    justa por construccion. Devuelve (x, fx) mejorados (Lamarckiano: reescribe x)."""
    improved = True
    while improved and c.fes < budget:
        improved = False
        for nb in problem.neighbors(x):
            if c.fes >= budget:
                break
            f = ev(nb)
            if f < fx - 1e-12:
                x, fx, improved = nb, f, True
                break                      # primera mejora
        if not full:
            break
    return x, fx


def ils_run(problem, budget, seed, f_target, tol=1e-9, perturb_k=3):
    """Iterated Local Search = PISO FUERTE (defensa anti 'tu piso era debil').
    LS de primera-mejora hasta optimo local + perturbacion (k flips) + aceptar si
    no empeora. Mismo conteo de FES. Solo para representacion binaria (lista 0/1)."""
    rng = random.Random(seed)
    c = _C()

    def ev(sol):
        c.fes += 1
        return problem.objective(sol)

    dim = len(problem.random_solution(rng))
    cur = problem.random_solution(rng)
    cur_f = ev(cur)
    cur, cur_f = _descend(problem, cur, cur_f, ev, budget, c)
    best = cur_f
    fes_to_target = c.fes if best <= f_target + tol else None
    while c.fes < budget and fes_to_target is None:
        cand = list(cur)
        for _ in range(perturb_k):
            cand[rng.randrange(dim)] ^= 1
        cand_f = ev(cand)
        cand, cand_f = _descend(problem, cand, cand_f, ev, budget, c)
        if cand_f <= cur_f:
            cur, cur_f = cand, cand_f
        if cur_f < best:
            best = cur_f
        if fes_to_target is None and best <= f_target + tol:
            fes_to_target = c.fes
    return {"best": best, "fes_to_target": fes_to_target, "fes_used": c.fes}


def ga_run(problem, budget, seed, f_target, tol=1e-9,
           pop=30, pc=0.9, pm=None, tour_k=3, memetic=False, ls_elite=True):
    """GA binario. Minimiza problem.objective. 1 evaluacion = 1 FES.
    memetic=True -> aplica _descend (LS compartida) a cada hijo (Lamarckiano).
    ls_elite con memetic: si True solo refina el mejor de la generacion (mas barato)."""
    rng = random.Random(seed)
    c = _C()

    def ev(sol):
        c.fes += 1
        return problem.objective(sol)

    dim = len(problem.random_solution(rng))
    if pm is None:
        pm = 1.0 / dim

    X = [problem.random_solution(rng) for _ in range(pop)]
    F = [ev(x) for x in X]
    best = min(F)
    fes_to_target = c.fes if best <= f_target + tol else None

    def tournament():
        best_i = rng.randrange(pop)
        for _ in range(tour_k - 1):
            j = rng.randrange(pop)
            if F[j] < F[best_i]:
                best_i = j
        return X[best_i]

    while c.fes < budget and fes_to_target is None:
        bi = min(range(pop), key=lambda i: F[i])
        newX = [list(X[bi])]                         # elitismo
        while len(newX) < pop:
            p1, p2 = tournament(), tournament()
            if rng.random() < pc:
                child = [a if rng.random() < 0.5 else b for a, b in zip(p1, p2)]
            else:
                child = list(p1)
            for k in range(dim):
                if rng.random() < pm:
                    child[k] ^= 1
            newX.append(child)
        X = newX
        F = []
        for x in X:
            if c.fes >= budget:
                F.append(math.inf); continue
            F.append(ev(x))
        if memetic and c.fes < budget:
            if ls_elite:
                gi = min(range(pop), key=lambda i: F[i])
                X[gi], F[gi] = _descend(problem, X[gi], F[gi], ev, budget, c)
            else:
                for i in range(pop):
                    if c.fes >= budget:
                        break
                    X[i], F[i] = _descend(problem, X[i], F[i], ev, budget, c)
        cur_best = min(F)
        if cur_best < best:
            best = cur_best
        if fes_to_target is None and best <= f_target + tol:
            fes_to_target = c.fes
    return {"best": best, "fes_to_target": fes_to_target, "fes_used": c.fes}


def _vshaped(v):
    """Transfer V-shaped V2 de Mirjalili 2013: T(v)=|tanh(v)|. Mejor que la sigmoide
    S-shaped original de Kennedy-Eberhart para PSO binario."""
    return abs(math.tanh(v))


def bpso_run(problem, budget, seed, f_target, tol=1e-9,
             swarm=30, w=0.7, c1=1.7, c2=1.7, vmax=6.0, memetic=False):
    """Binary PSO con transfer V-shaped. Posicion 0/1; velocidad continua.
    Update V-shaped: si rand < T(v) -> el bit se invierte (complemento), si no,
    permanece. Parametros estandar (Shi-Eberhart inercia; vmax acota saturacion)."""
    rng = random.Random(seed)
    c = _C()

    def ev(sol):
        c.fes += 1
        return problem.objective(sol)

    dim = len(problem.random_solution(rng))
    X = [problem.random_solution(rng) for _ in range(swarm)]
    V = [[rng.uniform(-vmax, vmax) for _ in range(dim)] for _ in range(swarm)]
    F = [ev(x) for x in X]
    pbest = [list(x) for x in X]
    pbest_f = list(F)
    gi = min(range(swarm), key=lambda i: F[i])
    gbest, gbest_f = list(X[gi]), F[gi]
    best = gbest_f
    fes_to_target = c.fes if best <= f_target + tol else None

    while c.fes < budget and fes_to_target is None:
        for i in range(swarm):
            if c.fes >= budget:
                break
            for j in range(dim):
                r1, r2 = rng.random(), rng.random()
                V[i][j] = (w * V[i][j]
                           + c1 * r1 * (pbest[i][j] - X[i][j])
                           + c2 * r2 * (gbest[j] - X[i][j]))
                if V[i][j] > vmax: V[i][j] = vmax
                elif V[i][j] < -vmax: V[i][j] = -vmax
                if rng.random() < _vshaped(V[i][j]):
                    X[i][j] ^= 1                      # V-shaped: invierte el bit
            F[i] = ev(X[i])
            if F[i] < pbest_f[i]:
                pbest[i], pbest_f[i] = list(X[i]), F[i]
            if F[i] < gbest_f:
                gbest, gbest_f = list(X[i]), F[i]
        if memetic and c.fes < budget:                 # LS COMPARTIDA: descenso completo del mejor
            bi = min(range(swarm), key=lambda i: F[i])
            X[bi], F[bi] = _descend(problem, X[bi], F[bi], ev, budget, c)
            if F[bi] < pbest_f[bi]:
                pbest[bi], pbest_f[bi] = list(X[bi]), F[bi]
            if F[bi] < gbest_f:
                gbest, gbest_f = list(X[bi]), F[bi]
        if gbest_f < best:
            best = gbest_f
        if fes_to_target is None and best <= f_target + tol:
            fes_to_target = c.fes
    return {"best": best, "fes_to_target": fes_to_target, "fes_used": c.fes}


def _prob_estim(y, b=6.0):
    """🔴 NO reproduce el operador de NMBDE (Wang 2012). Ver fcv/NMBDE_OPERATOR.md.

    Mapea el mutante diferencial y=x_r1+F*(x_r2-x_r3) a P(bit=1) con
    g(y)=1/(1+exp(-2b(y-0.5))), que NO depende de F — y el rango de y si: es
    [-F, 1+F]. El comentario original decia "en [-1,2]", que es el rango para F=1,
    mientras el default es F=0.5.

    Contrastado contra los tres valores que el propio paper publica para F=0.5
    (0.2315 / 0.0266 / 0.9975), esta forma no reproduce ninguno. La fuente esta tras
    paywall y la ecuacion completa no se pudo verificar, asi que NO se corrige a
    ciegas: NMBDE_OPERATOR.md deja el test de aceptacion listo para cuando se consiga.

    Mientras tanto, ningun resultado que involucre bde/mbde es valido."""
    z = -2.0 * b * (y - 0.5)
    if z > 60: return 0.0
    if z < -60: return 1.0
    return 1.0 / (1.0 + math.exp(z))


def bde_run(problem, budget, seed, f_target, tol=1e-9,
            NP=30, F=0.5, CR=0.9, b=6.0, memetic=False):
    """Binary DE (NMBDE, Wang 2012): DE/rand/1 + probability-estimation operator
    para binarizar la mutacion sin redondeo trivial. F, CR estandar (Storn-Price)."""
    rng = random.Random(seed)
    c = _C()

    def ev(sol):
        c.fes += 1
        return problem.objective(sol)

    dim = len(problem.random_solution(rng))
    X = [problem.random_solution(rng) for _ in range(NP)]
    Fit = [ev(x) for x in X]
    best = min(Fit)
    fes_to_target = c.fes if best <= f_target + tol else None

    while c.fes < budget and fes_to_target is None:
        for i in range(NP):
            if c.fes >= budget:
                break
            r1, r2, r3 = i, i, i
            while r1 == i: r1 = rng.randrange(NP)
            while r2 in (i, r1): r2 = rng.randrange(NP)
            while r3 in (i, r1, r2): r3 = rng.randrange(NP)
            jrand = rng.randrange(dim)
            trial = list(X[i])
            for j in range(dim):
                if rng.random() < CR or j == jrand:
                    y = X[r1][j] + F * (X[r2][j] - X[r3][j])
                    trial[j] = 1 if rng.random() < _prob_estim(y, b) else 0
            ft = ev(trial)
            if ft <= Fit[i]:                         # seleccion DE (greedy)
                X[i], Fit[i] = trial, ft
                if ft < best:
                    best = ft
        if memetic and c.fes < budget:               # LS COMPARTIDA: descenso completo del mejor
            bi = min(range(NP), key=lambda i: Fit[i])
            X[bi], Fit[bi] = _descend(problem, X[bi], Fit[bi], ev, budget, c)
            if Fit[bi] < best:
                best = Fit[bi]
        if fes_to_target is None and best <= f_target + tol:
            fes_to_target = c.fes
    return {"best": best, "fes_to_target": fes_to_target, "fes_used": c.fes}


# --- POA: Pufferfish Optimization Algorithm (Al-Baik et al. 2024) -------------
# Portado al harness FCV desde el motor validado de TMLPA (tmlpa_engine.py 5a),
# que es la version usada en el entregable de MIA-103. Se preserva el algoritmo
# publicado; lo unico que cambia es el problema sobre el que opera y el conteo de
# FES, que ahora es el MISMO que el del piso y el del resto del factorial.
#
# El POA es continuo por definicion, asi que sobre representacion binaria opera
# via proxy continuo + binarizacion sigmoide (el mismo esquema del companion del
# paper original). Sus dos fases:
#   Fase 1 (ataque del predador): el pez se mueve hacia OTRO pez mejor elegido al
#     azar, con factor I in {1,2}.
#   Fase 2 (mecanismo de defensa): perturbacion de amplitud (ub-lb)/t, decreciente
#     con la iteracion t.
# Ambas con aceptacion greedy (se acepta si no empeora), que es lo que el paper
# especifica y una de las hipotesis del colapso observado en TMLPA.
#
# Ref: Al-Baik et al. (2024), Biomimetics 9(2):65, 10.3390/biomimetics9020065.

CONT_LB, CONT_UB = -4.0, 4.0


def _sigmoid(v):
    """Sigmoide numericamente estable (evita overflow de exp para v muy negativo)."""
    if v >= 0.0:
        return 1.0 / (1.0 + math.exp(-v))
    z = math.exp(v)
    return z / (1.0 + z)


def poa_run(problem, budget, seed, f_target, tol=1e-9, swarm=30, memetic=False):
    """Pufferfish Optimization Algorithm binario, con proxy continuo + sigmoide.

    `swarm=30` por paridad con GA/bPSO/bDE del factorial: el protocolo compara
    criterios de admision, y una poblacion distinta seria una variable confundida.
    El paper original no fija el tamano de poblacion."""
    rng = random.Random(seed)
    c = _C()

    def ev(sol):
        c.fes += 1
        return problem.objective(sol)

    dim = len(problem.random_solution(rng))

    def binarize(cont):
        return [1 if rng.random() <= _sigmoid(v) else 0 for v in cont]

    CONT = [[rng.uniform(CONT_LB, CONT_UB) for _ in range(dim)]
            for _ in range(swarm)]
    X = [binarize(cont) for cont in CONT]
    F = [ev(x) for x in X]
    best = min(F)
    fes_to_target = c.fes if best <= f_target + tol else None

    t = 0
    while c.fes < budget and fes_to_target is None:
        t += 1
        for i in range(swarm):
            if c.fes >= budget:
                break
            # Fase 1 — ataque del predador: hacia un pez estrictamente mejor
            better = [k for k in range(swarm) if k != i and F[k] < F[i]]
            if better:
                sp = rng.choice(better)
                r = rng.random()
                I = rng.choice((1, 2))
                cont_new = [CONT[i][j] + r * (CONT[sp][j] - I * CONT[i][j])
                            for j in range(dim)]
                x_new = binarize(cont_new)
                f_new = ev(x_new)
                if f_new <= F[i]:                     # aceptacion greedy
                    CONT[i], X[i], F[i] = cont_new, x_new, f_new
            if c.fes >= budget:
                break
            # Fase 2 — mecanismo de defensa: amplitud decreciente en 1/t
            r = rng.random()
            amp = (1.0 - 2.0 * r) * (CONT_UB - CONT_LB) / t
            cont_new = [CONT[i][j] + amp for j in range(dim)]
            x_new = binarize(cont_new)
            f_new = ev(x_new)
            if f_new <= F[i]:
                CONT[i], X[i], F[i] = cont_new, x_new, f_new
        if memetic and c.fes < budget:               # LS COMPARTIDA: descenso completo del mejor
            bi = min(range(swarm), key=lambda k: F[k])
            X[bi], F[bi] = _descend(problem, X[bi], F[bi], ev, budget, c)
        cur = min(F)
        if cur < best:
            best = cur
        if fes_to_target is None and best <= f_target + tol:
            fes_to_target = c.fes
    return {"best": best, "fes_to_target": fes_to_target, "fes_used": c.fes}
