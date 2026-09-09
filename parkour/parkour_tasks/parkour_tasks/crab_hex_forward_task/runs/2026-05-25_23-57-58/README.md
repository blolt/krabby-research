# Crab Hex Teacher 2b1 Baseline: 2026-05-25_23-57-58

Stage 2b phase 1: Appendix D `model_6099.pt` → **100** iters (`KRABBY_HEX_TEACHER_MODE=2b1`) → **`model_6198.pt`**.

Log: `logs/rsl_rl/crab_hex_teacher/2026-05-25_23-57-58/`. USD: `runs/2026-05-23_10-15-21/crab_simple_2026-05-23_10-15-21.usda`.

Play: `../play_crab_hex_2b1_baseline.sh` with Appendix C USD + `model_6198.pt`. See task README Appendix E.

Plant: the pre-generator snapshot USD bundled in `runs/2026-05-23_10-15-21/` (`KRABBY_HEX_USD_PATH` to it); `KRABBY_HEX_SPAWN_Z=1.05` was the setting of record then (current default 1.085, main asset `assets/crab.usda` = A15+B).
