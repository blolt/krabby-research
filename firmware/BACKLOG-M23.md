# Milestone 23 — Combined improvement backlog

**Status:** Ordered and packed. Work top-down from the cut line; do not start below it unless a departure is recorded (see `TASK-2-IMPROVEMENT-BUCKET.md`).

**Sources**

| Source | Path | Role here |
| --- | --- | --- |
| Friction log | [`FRICTION-LOG.md`](FRICTION-LOG.md) | Task 1 cold-start / bench deviations (`F*`) |
| Known issues | [`KNOWN-ISSUES.md`](../../patina-foundation-grants/grants/Krabby-Uno/Milestone23-FleetReliability-QOL/KNOWN-ISSUES.md) | Pre-M23 inventory (`K*`) |
| M21 hand-offs | Overview “Looking ahead” | Scored as candidates, same rubric (`M21-*`) |

**Scoring rubric (same as Task 1 friction log)**

| Field | Meaning |
| --- | --- |
| Blocking | Stops bring-up / release / CI vs only slows it |
| Cost | Minutes or hours lost, and how often it recurs |
| Effort | Hours to fix properly (½-hour grain) — estimate used for packing |
| Actual | Hours really spent (incl. returned items); fill when the item closes |
| Who | AI-suited / Human / Hardware |
| Priority | Impact over effort; impact = frequency × per-hit cost; **blockers above slowdowns** |

Friction-log `F*` rows keep the effort numbers from `FRICTION-LOG.md` unless noted. `K*` / `M21-*` rows were scored at Task 2 start so they can sit on the same list.

**Overlap notes (avoid double-counting hours)**

- `F1` + `F2` are the concrete quick-start install failures; `K27` is the broader README audience split. Bucket counts `F1`/`F2` in full and `K27` at **4 h residual** (not a second full rewrite of the install steps).
- `K29` docs fix (loud mismatch) is in-bucket; PEP 541 rename request is a separate below-line item.
- `M21-A` ≡ `K4`; `M21-D` ≡ `K21` (listed once).
- `K36` guided Task 1 (extend `krabby-bench`); marked done / out of scope as a fix item.
- `F4` is **done** and sits at priority 1 inside the 60 h bucket (effort already spent during Task 1 bring-up).

---

## 60-hour cut line

Packed total above the line: **60.0 h** estimated (within 10% of 60). **Actual logged so far: 4.0 h** (`F4`). Remaining open estimate above the line: **56.0 h**.

Hardware-access items above the line are clustered near the end of the bucket (`F10`, `F9`) so one bench session can cover them. `F11` (runner registration) is pulled high because it blocks commit-triggered hardware CI even though it is not kit cold-start friction.

| | |
| --- | --- |
| **Above** | Priority 1–26 in the ordered table (through `F9`) |
| **Below** | Everything after the cut marker; retain scores for the next milestone |
| **Out of scope / done** | See bottom section (`F4` is in the ordered table, not here) |

---

## Ordered list (work top-down)

Status values: `open` · `in progress` · `done` · `returned` · `out of scope`

`Actual` = hours spent (fill on close, including returned items). `—` means not started / not logged yet. `Cumul` is estimated effort only.

| Pri | ID | Source | Summary | Blocking | Cost (with recurrence) | Effort (h) | Actual (h) | Who | Cumul (h) | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F4 | friction | Leader `J` forward / follower parse: LEFT/RIGHT H-bridges silent under GUI jog | was yes for GUI jog | ~1–2 h misdiagnosing UART; every 3-board GUI session on unpatched FW | 4 | 4 | Hardware + Human diagnose; AI assisted fix; Human verify reflash | 4.0 | done |
| 2 | F1 | friction | README `pip install` needs venv on Orin | yes | ~5 min; every fresh Orin | 1 | — | AI docs; Human verify Orin | 5.0 | open |
| 3 | F2 | friction | `sudo krabby install` hits wrong/`No such command` binary | yes | ~10 min; every venv + sudo | 1 | — | AI docs; Human verify sudo PATH | 6.0 | open |
| 4 | K28 | known | No top-level “read this for your intent” routing | yes (findability) | every new reader; cheapest high-impact doc fix | 2 | — | AI | 8.0 | open |
| 5 | K29 | known | Spoken `pip install krabby` ≠ `krabby-launcher` | yes (trap) | every new user who guesses the spoken name | 1 | — | AI (docs loud) | 9.0 | open |
| 6 | K5 | known | Isaac `contacvt_sensor` typo; contact never assigned | yes (sim contact path) | every contact/current read through Isaac HAL | 0.5 | — | AI | 9.5 | open |
| 7 | F11 | friction | Bench Orin not a self-hosted Actions runner yet | yes (commit→hardware bench) | until admin token + register; Appendix C | 3 | — | Human (admin + operator) | 12.5 | open |
| 8 | F13 | friction | Artifact-health **locomotion-image** stage FAIL | yes (green artifact-health) | ~15–60 min once Actions log read | 3 | — | AI workflow; Human Discord PASS | 15.5 | open |
| 9 | F6 | friction | Boot unit owns `/krabby`; manual `krabby run` conflicts | yes (fresh manual run) | ~2–5 min; every boot + manual run | 2 | — | AI docs/code; Human verify | 17.5 | open |
| 10 | K1 | known | Default branch `main` publishes nothing; workflows watch `mainline`/`release/**` | yes (silent no-ship) | every merge to `main`; hours of false confidence | 3 | — | Human decision + AI change/docs | 20.5 | open |
| 11 | F5 | friction | Pro Controller `Paired: no` / Sync vs cache; warn blames `hid_nintendo` | yes (gamepad drive) | ~15–30 min; every first BT pair / bad reconnect | 3 | — | AI warn/docs; Human+HW verify | 23.5 | open |
| 12 | K2 | known | No test suite on push/PR (only on package version tags) | no (until release) | every breaking commit until someone tags | 3 | — | AI | 26.5 | open |
| 13 | F8 | friction | `XDG_RUNTIME_DIR` error on `krabby run` (cosmetic) | no | ~0–1 min; every `krabby run` | 1 | — | AI container env; Human verify | 27.5 | open |
| 14 | K33 | known | Two competing host-setup paths (manual Jetson doc vs `krabby install`) | yes (wrong path) | hours if reader follows the stale guide | 2 | — | Human decide + AI mark/doc | 29.5 | open |
| 15 | K31 | known | Enrollment documented in `ENROLL.md` and `SETUP-FLEET.md` | yes (which is current?) | drift; Task 1 had to pick one | 2 | — | AI | 31.5 | open |
| 16 | T1a-ZED | friction App. D | Front teleop video needs USB 3 SuperSpeed ZED cable | yes (1a front video) | until correct cable + 5000M path | 1 | — | Hardware + Human | 32.5 | open |
| 17 | K19 | known | Gamepad launch hard-codes Jetson HAL backend | yes (non-Jetson gamepad) | cannot launch other backends via that path | 2 | — | AI | 34.5 | open |
| 18 | F3 | friction | GUI + Pro pair script not on PyPI; kit path needs clone | yes without clone (GUI/pair) | ~15–30 min; every kit-only bring-up | 4 | — | AI package/docs; Human PyPI/kit | 38.5 | open |
| 19 | K27 | known | Root README interleaves user / developer / infra | yes (cold-start clarity) | every new user; residual after F1/F2 line fixes | 4 | — | AI + Human | 42.5 | open |
| 20 | K13 | known | Firmware error branch silently swallowed (`arduino.ino`) | yes when hit | can burn a bring-up afternoon | 2 | — | AI + Hardware verify | 44.5 | open |
| 21 | F7 | friction | `KRABBY_MCU_PORT` not forwarded by `gamepad_cmd` / `krabby run` | no if auto-detect works; yes if operator trusts warn | ~5–15 min; every CH340/`ttyUSB*` | 4 | — | AI forward env; Human+HW | 48.5 | open |
| 22 | F12 | friction | `docker/setup-qemu-action@v3` Node 20 deprecation warn | no until Node 20 removal | ~5 min when editing workflow | 1 | — | AI bump; Human CI green | 49.5 | open |
| 23 | K26 | known | M21 contract says merge to `main` (follow K1 decision) | tied to K1 | contract/docs wrong until aligned | 0.5 | — | AI (after K1) | 50.0 | open |
| 24 | K3 | known | Publish workflows still silent (bench Discord ≠ publish notify) | no | Actions tab or try-to-use only signal | 2 | — | AI | 52.0 | open |
| 25 | F10 | friction | `firmware show` sometimes only FRONT until USB replug | yes (3-role flash/bring-up) | ~1–2 min; intermittent | 4 | — | Hardware + Human; AI docs/retry | 56.0 | open |
| 26 | F9 | friction | Mid-upload interrupt / hub enum: board “vanishes” | yes until reappears | ~15–45 min per stuck board | 4 | — | Hardware recover; AI docs (App. B exists) | **60.0** | open |

### ——— 60-hour cut line (packed total 60.0 h estimated) ———

| Pri | ID | Source | Summary | Blocking | Cost (with recurrence) | Effort (h) | Actual (h) | Who | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 27 | K16 | known | Observation timestamps not propagated (`None`) | no | incomplete teleop latency accounting | 2 | — | AI | open |
| 28 | K17 | known | Gamepad mapper assumes start joints; does not read state | no | wrong start-pose assumptions | 2 | — | AI + Hardware | open |
| 29 | K30 | known | `firmware/SETUP.md` milestone title + four audiences | no | confusion every firmware reader | 4 | — | AI | open |
| 30 | K34 | known | `DEVELOPER.md` untitled; sim-only half of development | no | real-robot dev path undocumented | 4 | — | AI | open |
| 31 | K32 | known | `SETUP-FLEET.md` mixes account setup and per-robot ops | no | infra vs operator confusion | 4 | — | AI | open |
| 32 | K35 | known | Image/package READMEs mix consumer and maintainer | no | wrong audience sections | 2 | — | AI | open |
| 33 | K10 | known | John’s OLED simulator referenced, not in repo | yes for M21 T4 | blocks until located/vendored | 4 | — | Human | open |
| 34 | K12 | known | Actuators instantiated before role election finishes | intermittent | wrong first wiring until corrected | 4 | — | Hardware + AI | open |
| 35 | K18 | known | Gamepad path tested on macOS only (Orin partly covered in T1) | partial | Linux/Windows still thin | 4 | — | Hardware | open |
| 36 | K22 | known | Windows `play.py` needs three undocumented fixes | Windows only | hours on first Windows setup | 4 | — | AI | open |
| 37 | M21-C | M21 | GPU capability validation before launch | no | failed launches on wrong GPU | 4 | — | AI + Human | open |
| 38 | K4 / M21-A | known / M21 | IsaacSim image built locally, never published | no for hardware path | every sim adopter rebuilds (hours) | 8 | — | AI + Human | open |
| 39 | K21 / M21-D | known / M21 | Stopped simulator stays offline; no IoT resume | yes for sim recovery | manual CLI restart each time | 8 | — | AI + Human | open |
| 40 | K11 | known | Actuator identity / pin config hardcoded in several places | no | hours whenever roles/names change | 8 | — | AI + Hardware | open |
| 41 | K29-PEP541 | known | Request PyPI `krabby` name under PEP 541 | no (docs fix is above) | process time; discretionary transfer | 8 | — | Human | open |
| 42 | M21-B | M21 | Absent MCU → detect and offer simulator | yes for no-MCU machines | cannot soft-fail to sim today | 12 | — | AI + Human | open |
| 43 | K6 | known | Real MCU position commands disabled; jog fallback | architectural | closed-loop path not what robot runs | 12 | — | Human + Hardware | open |
| 44 | K8 | known | HAL has no abstract backend contract | no | days of reading to add a backend | 12 | — | AI + Human | open |
| 45 | K7 | known | Jetson observations partly unimplemented | no | incomplete real sensor obs | 16 | — | Human + Hardware | open |
| 46 | K15 | known | `MODEL_CONTROLLER_KRABBY` unimplemented stub | feature | blocks model-controller mode | 20 | — | Human | open |
| 47 | K20 | known | Updates require SSH (`krabby update`); no cloud rollout | scope decision | every update needs an operator | 20 | — | Human | open |
| 48 | K9 | known | M16 sensors specified, not in `firmware/arduino/` | yes for M21 T4 sim | large cross-milestone gap | 40 | — | Human + Hardware | open |
| 49 | K14 | known | Actuator lookup linear/quadratic (OK at six) | no | none until actuator count grows | 2 | — | AI | open |
| 50 | K23 | known | Kit non-fatal sensor extension DLL errors on Windows | no | minutes of false alarm | 1 | — | AI docs | open |
| 51 | K24 | known | Grants README describes `T1-` / `AUDIT-LOG` nobody uses | no (meta) | contributor naming mismatch | 0.5 | — | AI | open |
| 52 | K25 | known | Grant time-estimate drift (checked in M21; others unchecked) | no (meta) | estimate inconsistency | 1 | — | Human | open |

---

## Out of scope / done (explicit)

| ID | Reason |
| --- | --- |
| K36 | **Done as guidance** — Task 1 extended `krabby-bench` rather than building a second bench; not a remaining fix |
| K20 (as “reverse M10”) | **Out of scope** unless reducing SSH friction *without* adding cloud-driven rollout; full remote update is a product decision |
| Local `firmware/.venv`, `firmware/arduino/Downloads/` | **Not issues** — untracked local artifacts (KNOWN-ISSUES closing note) |

---

## How to work this list

1. Take the next `open` row above the cut line (or a recorded hardware-batch exception).
2. Fill **Actual (h)** when the item closes (including returned ones); on overrun: finish, split, or return with revised effort (`TASK-2` §4). Update the “Actual logged so far” total in the cut-line section.
3. Verify against the friction symptom or known-issue behavior (`TASK-2` §5); update this row’s **Status** and the matching `FRICTION-LOG.md` entry.
4. Do not silently skip a top item — mark **out of scope** with a reason instead.
5. Closing measurement (after the bucket): cold-start command sequence vs Task 1 baseline + green Task 1 bench (`TASK-2` §6).

---

## Packing sanity check

| Check | Result |
| --- | --- |
| Every `F1`–`F13` represented | Yes (`F4` priority 1 / done in-bucket; others in ordered table) |
| Every `KNOWN-ISSUES` 1–36 represented | Yes (`K36` done; others scored; `K29` split docs vs PEP 541) |
| M21 hand-offs scored | Yes (`M21-A`=`K4`, `M21-B`, `M21-C`, `M21-D`=`K21`) |
| Cut within 10% of 60 h | **60.0 h** estimated packed; **Actual logged: 4.0 h** (`F4`); 56.0 open estimate |
| Hardware clustered | `F11` early (CI unblock); `F10`/`F9`/`K13`/`T1a-ZED` grouped toward end of bucket |
| Prerequisites same side of line | `K26` after `K1` (both above); `K27` after `F1`/`F2` |
