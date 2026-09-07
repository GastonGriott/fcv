# Experimental record

Every result reported in the paper, one row per (problem, method, seed). **50 778 runs** across
five campaigns. Files ending in `_perseed` hold the raw runs; `_agg` holds the per-cell aggregates
derived from them.

Columns of a `_perseed` file: `family, tag, n, idx, decoder, method, dim, budget, f_opt, exact,
seed, best, ftt, fes` — where `best` is the best objective value found, `ftt` the evaluations to
target (empty when the target was never reached) and `fes` the evaluations spent.

## Which file backs which section

| File | Runs | What it is | Paper |
|---|---:|---|---|
| `fcv_v2_perseed.csv` | 20 088 | **The factorial study.** 81 problems × 8 methods × 31 seeds, three families with planted instances | §4, main results and admission verdicts |
| `fcv_v2_decoder_perseed.csv` | 8 370 | **Decoder control.** Same problems and seeds, penalty vs. repair decoder | §6 |
| `fcv_v2_floor_ils_ga_mga_orlib_scp_perseed.csv` | 1 860 | **Set covering, OR-Library.** 15 instances (classes `scp4` and `scp6`) × 4 methods × 31 seeds | §5, Table 3 |
| `fcv_v2_floor_ils_ga_mga_bpso_mbpso_bde_mbde_orlib_uflp_perseed.csv` | 2 976 | **Facility location, OR-Library.** 12 `cap*` files × 8 methods × 31 seeds | §5 |
| `fcv_v2_floor_ils_perseed.csv` | 8 370 | Both floors over the 135 generated instances | §5, floor-triviality counts |
| `fcv_v2_poa_perseed.csv` | 8 370 | An in-protocol run of a published 2024 metaheuristic and its memetic variant, over the same 135 | Referenced as an application of the protocol |
| `fcv_v2_floor_ils_mpoa_orlib_perseed.csv` | 744 | ⚠️ **Superseded for set covering — see below** | — |

## ⚠️ Superseded data, and why it is still here

**`fcv_v2_floor_ils_mpoa_orlib_perseed.csv` covers `scp41`–`scp48` only (8 instances).** The
set-covering campaign was later extended to **15** instances, and
`fcv_v2_floor_ils_ga_mga_orlib_scp_perseed.csv` is the authoritative file for every set-covering
number in the paper. The 8-instance file is kept because it is the independent replication that
backs the reproducibility claim: the 16 cells the two campaigns share came out **identical seed by
seed**, on different days and different machines. Do not read paper figures off it — its
denominator is 8 where the paper says 15.

**Not included, deliberately:** an earlier version of the factorial file dated 2026-06-01 with
16 368 rows. It shares its keys with `fcv_v2_perseed.csv` but **11 652 of those cells hold
different values**, because the engine changed between the two runs. It is not a partial version of
the current file, it is a different experiment, and no number in the paper comes from it.

## Reproducing a verdict

From this directory, with Python 3.12+ and SciPy:

```bash
python ../analysis/analyze_admision.py --perseed <file> --methods <candidates>
```

`analysis/check_reproducibilidad.py` compares two campaigns cell by cell, which is how the
identical-seed-by-seed claim above was verified.
