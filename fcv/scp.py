"""fcv.scp — Set Covering (unicost) como familia FCV, con OPTIMO PLANTADO.

Para evitar depender de un solver ILP (scipy.milp cuelga en Windows local),
construimos instancias con optimo conocido por diseno:

  - Las filas se particionan en k BLOQUES disjuntos.
  - Hay k columnas "solucion", cada una cubre exactamente un bloque completo.
  - Las columnas "filler" cubren solo un SUBCONJUNTO ESTRICTO de un unico bloque.

Asi, cubrir un bloque requiere su columna solucion O >=2 fillers => el minimo
numero de columnas para cubrir todo es exactamente k (unicost). Optimo = k.

Representacion: vector binario sobre columnas. Objetivo a MINIMIZAR:
    f(x) = #columnas_seleccionadas + P * #filas_no_cubiertas
Vecindario: add/drop una columna (1-flip)."""
import random
from .core import Problem


class SetCover(Problem):
    def __init__(self, columns, n_rows, k_opt, name="scp"):
        self.columns = [frozenset(c) for c in columns]  # cada col = set de filas
        self.n_rows = n_rows
        self.n_cols = len(columns)
        self.k_opt = k_opt
        self.name = name
        self.P = self.n_cols + 1            # penalizacion > cualquier nº de columnas

    def random_solution(self, rng):
        return [rng.randint(0, 1) for _ in range(self.n_cols)]

    def neighbors(self, sol):
        for i in range(self.n_cols):
            nb = list(sol)
            nb[i] ^= 1
            yield nb

    def objective(self, sol):
        chosen = [i for i, x in enumerate(sol) if x]
        covered = set()
        for i in chosen:
            covered |= self.columns[i]
        uncovered = self.n_rows - len(covered)
        return len(chosen) + self.P * uncovered

    def ceiling(self):
        return self.k_opt, True            # plantado, optimo por construccion

    def space_size(self):
        return 2 ** self.n_cols


def make_instance(n_cols, seed, k=None, rows_per_block=5, fillers_per_block=None):
    """Instancia SCP unicost con optimo plantado = k bloques.
    n_cols ~ k + k*fillers_per_block (aprox). dimension = n_cols."""
    rng = random.Random(seed)
    if k is None:
        k = max(3, n_cols // 6)
    n_rows = k * rows_per_block
    blocks = [list(range(b * rows_per_block, (b + 1) * rows_per_block)) for b in range(k)]
    columns = [list(bl) for bl in blocks]      # k columnas solucion (bloque completo)
    if fillers_per_block is None:
        fillers_per_block = max(1, (n_cols - k) // k)
    for b in range(k):
        bl = blocks[b]
        for _ in range(fillers_per_block):
            # subconjunto ESTRICTO del bloque (tamano 1..len-1) => no cubre el bloque solo
            size = rng.randint(1, max(1, len(bl) - 1))
            columns.append(rng.sample(bl, size))
    rng.shuffle(columns)
    return SetCover(columns, n_rows, k, name=f"scp_c{len(columns)}_s{seed}")
