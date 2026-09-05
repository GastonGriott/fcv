# FCV — Floor–Ceiling Validation

An admission test for metaheuristics: a new method is accepted on a problem only if it
beats a **floor** — a parameter-free local search — in reliability, on instances that are
not trivially solved by that floor, with quality measured against an exact **ceiling**.

The point of the protocol is that its verdict can come out **negative**, and that the
negative verdict is informative: it separates "this method is not needed here" from "this
instance was easy all along".

This repository is the reference implementation and the complete experimental record of
the paper *A Local-Search Floor for Honest Metaheuristic Benchmarking: a Large Search
Space Is Not a Hard One*.

## The three criteria

| | Criterion | Measured as |
|---|---|---|
| **C1** | The candidate beats the strong floor in **reliability** | Paired McNemar per seed, Holm-corrected within the family. When neither reaches the ceiling within budget the regime becomes *budget-bound* and the bar is the floor's own median — an empty verdict is reported as *absence of evidence*, not as rejection |
| **C2** | The instance is not **floor-trivial** | NR = median(FES-to-optimum of the floor) / budget; instances with NR < τ are excluded. Reported under **both** floors, because which floor measures triviality changes the answer |
| **C3** | Quality as **distance to the exact ceiling** | Ceilings are *solved*, not cited (see below) |

## What is in here

```
fcv/            the package: instance families, decoders, floors, candidates,
                exact solvers, the parallel runner and the statistics
analysis/       the scripts that turn a run into a verdict
results/        every per-seed result reported in the paper, plus run logs
notebooks/      Colab notebooks for running the study without a local setup
vm/             scripts to run the large campaigns on a GCE instance
```

**Problem families.** 0/1 knapsack (Pisinger's hard classes), set covering and
uncapacitated facility location — each with planted instances and with the corresponding
OR-Library benchmark.

**Methods.** Two floors (random-restart local search, and a stronger ILS) and six
candidates: GA, binary PSO and binary DE, each in a vanilla and a memetic variant that
shares the floor's own local search.

**Ceilings are solved, not copied.** Optima come from dynamic programming (knapsack),
construction (planted), subset enumeration, or a MILP solved with HiGHS. For OR-Library
instances the loader **aborts** if the solved value disagrees with the published one. A
number copied from a table is a citation nobody downstream can check, and in a protocol
where everything is measured against the ceiling, a wrong ceiling is wrong everywhere at
once.

## Requirements

Python **3.12** or newer with SciPy. This is not optional: the statistics and the MILP
ceilings both need it, and the package is written to **fail** rather than fall back —
a Friedman statistic without tie correction, or a penalty constant returned as a ceiling,
would be a plausible number rather than an error.

```bash
pip install -r requirements.txt
python -c "import sys, scipy; print(sys.executable, scipy.__version__)"
```

## Reproducing the paper

Every verdict in the paper comes out of `analysis/analyze_admision.py` applied to the
per-seed files in `results/`. From the repository root:

```bash
cd results

# Set covering, OR-Library: 15 instances, classes scp4 (2% density) and scp6 (5%)
python ../analysis/analyze_admision.py \
    --perseed fcv_v2_floor_ils_ga_mga_orlib_scp_perseed.csv --methods ga,mga

# Facility location, OR-Library: 12 capacitated-warehouse files read as uncapacitated
python ../analysis/analyze_admision.py \
    --perseed fcv_v2_floor_ils_ga_mga_bpso_mbpso_bde_mbde_orlib_uflp_perseed.csv \
    --methods ga,mga,bpso,mbpso,bde,mbde

# The two set-covering density classes separately (Table 3 of the paper)
python ../analysis/split_clases_scp.py
python ../analysis/analyze_admision.py --perseed _tmp_scp4_perseed.csv --methods ga,mga
python ../analysis/analyze_admision.py --perseed _tmp_scp6_perseed.csv --methods ga,mga
```

`check_reproducibilidad.py` compares two runs seed by seed. The 5 022 comparable floor
runs of the factorial study came out **identical** between Windows and Debian on GCE, and
so did the 16 cells shared by the two OR-Library set-covering campaigns.

## Running a new study

```python
from fcv import run_v2
run_v2.run(metodos="floor,ils,ga,mga", specs="orlib_scp", jobs=-1)
```

Results are cached per cell, so an interrupted campaign resumes instead of restarting.
`analysis/cache_to_csv.py` rebuilds the per-seed CSV from a partial cache, which lets you
analyse a campaign before it finishes.

Large campaigns are expensive and the cost is **not** proportional across methods: at
dimension 1000, binary PSO and binary DE evaluate about ten times slower than the floor.
Measure the slowest method on the largest instance with a reduced budget before sizing a
run — extrapolating from one method understated one campaign by a factor of ten.

## Citing

If you use this, please cite the paper and the software release — see `CITATION.cff`.

## License

MIT. See `LICENSE`.

The OR-Library instances are redistributed from their original source (Beasley, 1990,
*Journal of the Operational Research Society* 41(11), 1069–1072) and remain under their
original terms.
