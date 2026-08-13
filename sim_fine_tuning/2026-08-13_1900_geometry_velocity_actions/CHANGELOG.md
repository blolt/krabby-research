# Geometry alignment + camshaft velocity actions

Campaign start: 2026-08-13 ~19:00. Supersedes perp-mounts "Arm B" (position-window widening).

## Hardware measurements (user, 2026-08-13)
- Yaw: +-28.5 deg from perpendicular-to-body; cam shaft spins continuously through full sweep.
  Confirms CAD-derived THETA_HIP_MAX = 28.54 deg (K = 0.47778) -- cam mapping unchanged.
- Hip: 35-160 deg from straight-down vertical (90 = femur horizontal).
  Sim convention (verified): zero = horizontal, positive = femur down -> limits [-70, +55] deg.
- Knee: 40-165 deg interior femur-tibia angle (165 = extended, 40 = folded under body).
  Sim zero = 90 deg interior. Left legs [-75, +50]; right legs mirrored [-50, +75]
  (180-deg joint-frame flip on FR/MR/RR, localRot0 = (0,0,1,0)).

## Phase 0: right-leg knee sign probe (PASS)
Extended verify_crab_joint_drive.py (probe by action column -- it had been broken since the
24-DOF cam migration; also footpad world-displacement reporting, --only filter, traceback
flush before Kit close). Gravity ON required: gravity-off floats the robot into per-step
terminations that silently wipe every action (see memory: isaac-headless-launch-quirks).
Result: FL raw +1 -> foot inboard (tuck); FR raw +1 -> foot outboard (extend).
Same commanded sign, opposite fold direction = frame flip confirmed; mirrored knee limits stand.

## Commit 1: USD joint limits (assets/crab_simple.usda)
- Body_Hip: +-50 -> +-32 (soft 0.9x = +-28.8 > 28.54 mechanism sweep; passive joint headroom)
- Hip_Femur: +-75 -> [-70, +55] all legs
- Femur_Tibia: +-100 -> [-75, +50] FL/ML/RL; [-50, +75] FR/MR/RR
- CamShaft: unchanged (limit-free, continuous)
- New test: tests/unit/test_crab_hex_usd_joint_limits.py (pure-text parse pins the table,
  mirroring, defaults-inside-soft-limits, cam-sweep clearance)

## Commit 1 verification (in progress)
- Unit tests: 19/19 pass (new USD-limit pins + existing cam mapping).
- Joint drive (gravity ON, new limits): 18/18 driven. Live soft limits match table:
  hips [-1.113, +0.851] rad, knees L [-1.200, +0.764] / R mirrored, camshafts +-inf.
- Static settle x3 (static_report_geom.json + static_geom_r2/r3.json): pitch [+0.15, -0.53,
  -0.56] deg, roll [-0.38, -0.15, +0.28] deg, A_share [0.64, 0.46, 0.36]. Perp baseline
  (+0.38 / +0.05 / 0.526) sits inside scatter -> no systematic shift from limits; the
  A_share volatility is the known FR+RL floating-feet basin (already on the audit list).
- Ops: two kernel OOM kills traced to Isaac Kit shutdown ballooning to 50+ GB RSS (crashed
  the interactive session twice; results unharmed). All Isaac runs now wrapped in
  systemd-run --user --scope -p MemoryMax=32G. See memory: isaac-headless-launch-quirks.

## Infra: OOM storm root cause (resolved)
The "shutdown balloon" was actually the UJITSO DerivedDataCache (inside isaac_venv) in a
GC death spiral: a legit GC run was OOM-killed mid-migration at 14:25, corrupting the index;
every later boot re-ran a full migration holding ~2.7 GB buckets in RAM (50+ GB RSS) until
killed, corrupting further. Cache had inflated to 101 GB on disk. Additionally, processes
launched from the Claude Code shell live in the app's own cgroup, so the kernel OOM kill
took the whole session down with it (3x). Fixes: DerivedDataCache moved aside
(.corrupt-2026-08-13; regenerable), and all Isaac runs now launch via
`systemd-run --user --scope -p MemoryMax=45G` for cgroup isolation + cap.

## Commit 1 verification (continued)
- Cam mechanism check (new +-32 Body_Hip limits): PASS, hip tracks cam_shaft_to_hip()
  across full sweep on all 6 legs, max err 0.0104 rad (~0.6 deg); no limit contact.
- Canary fine-tune launched: 2000 it, 256 envs, from symmetric reference model_19999.
