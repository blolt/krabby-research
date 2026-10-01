# Cold-start friction log

**Work in progress**(Milestone 23) — entries and open items will keep changing; this file may be
removed or relocated later.

## Open items (not done yet)

- **1d / F11:** Orin runner blocked on repo **admin** registration token → Appendix C.
- **1a front video:** ZED needs USB 3 SuperSpeed cable → Appendix D (control already works).


| ID  | Stage                | Symptom                                                                                                                                                                                                                                                                                                                                                                          | Workaround                                                                                                                                                                                                                                | Component                                                                                                                               | Cause                                                                                                                                                                                                                                                                                                                                                                                                                    | Blocking                                                              | Cost                                                                 | Effort (h) | Who                                                                                |
| --- | -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------- | -------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------- |
| F1  | package-install      | README step 1 `pip install krabby-launcher` on the Orin fails: `PermissionError: [Errno 13] Permission denied:` (install into system Python).                                                                                                                                                                                                                                    | `python3 -m venv ~/.venv-krabby && source ~/.venv-krabby/bin/activate && pip install -U pip && pip install krabby-launcher`. Later `sudo krabby install` may need `sudo -E env PATH="$PATH" krabby install` so sudo sees the venv binary. | README software quick-start; `krabby-launcher`                                                                                          | pip tried to write a system site-packages path the user cannot write. **Docs to correct:** `README.md` (§ Software quick-start / Install the CLI — add venv). Good pattern already in `fleet/ENROLL.md`.                                                                                                                                                                                                                 | yes                                                                   | ~5 min; every fresh Orin                                             | 1          | AI can draft docs; Human/Person verify on Orin                                     |
| F2  | package-install      | After F1 venv, `sudo krabby install` prints `No such command 'install'`.                                                                                                                                                                                                                                                                                                         | `which krabby`; `sudo which krabby`; `sudo krabby --help`. Use the venv binary: `sudo -E env PATH="$PATH" "$(which krabby)" install`.                                                                                                     | README `sudo krabby install`; sudo secure_path                                                                                          | `krabby-launcher` has `install` (argparse). That error is Click, so sudo is a different `krabby` on root PATH (venv not in secure_path), often the unrelated PyPI project `krabby`. **Docs to correct:** `README.md` (§2 Pull the locomotion image — `sudo krabby install`); `krabby/README.md` (install / Start on boot examples that use bare `sudo krabby`). Mirror `fleet/ENROLL.md` (`sudo -E env PATH="$PATH" …`). | yes                                                                   | ~10 min; every venv + sudo                                           | 1          | AI can draft docs; Human/Person verify sudo path on Orin                           |
| F3  | firmware             | After `krabby install` / flash, no way to run the joint GUI from published packages alone. `pip install krabby-firmware` has no `firmware.gui` (pyproject only ships `firmware` + `firmware.interfaces`). Pro Controller pairing script also lives only in the git tree (`scripts/jetson/pair_pro_controller.sh`; doc at `controller/scripts/jetson/CONNECT_PRO_CONTROLLER.md`). | Clone `krabby-research` on the Orin for `python -m firmware.gui` / pairing, or use `python -m firmware` (keyboard) from the PyPI package.                                                                                                 | `krabby-firmware` packaging; docs that assume `python -m firmware.gui` / repo scripts                                                   | GUI and pairing are repo-only; kit path is pip-only. **Docs to correct:** `firmware/SETUP.md` (assumes repo / `python -m firmware` from tree); `README.md` (§6 → CONNECT_PRO_CONTROLLER without saying clone/repo required); `controller/scripts/jetson/CONNECT_PRO_CONTROLLER.md` and `scripts/jetson/README.md` (pairing is repo-only, not on PyPI).                                                                   | no (keyboard works); yes for GUI/pairing without clone                | ~15–30 min finding this; every kit-only bring-up                     | 4          | AI can package/docs; Human/Person for PyPI publish, kit decision, Orin verify      |
| F4  | firmware / jog       | With only FRONT USB connected, `krabby firmware show` lists front/left/right and FRONT motors jog from the GUI, but LEFT/RIGHT H-bridges do not move. Same LEFT/RIGHT motors work when USB is plugged directly into those boards.                                                                                                                                                |                                                                                                                                                                                                                                           | `firmware/arduino/arduino.ino` leader `J` forward; GUI `send_command_jog`                                                               | **Fixed:** leader forwarded `J <name> <pwm>` (space after `J`); followers parse `J` without skipping spaces → empty name / pwm 0. Host and forward now use `J<name> <pwm>`; parser also skips leading spaces so both forms work. Reflash all three with the patched sketch (`PIN_REV=2` on when this was identified).                                                                                                    | was yes for GUI jog                                                   | ~1–2 h misdiagnosing UART; every 3-board GUI session on unpatched FW | 4          | hardware + Human/Person diagnose; AI assisted fix (done); Human verify reflash     |
| F5  | controller           | `pair_pro_controller.sh` ends `Connected: yes` / `Paired: no` / `[warn] no js device (hid_nintendo may not be loaded)` even when `hid_nintendo` is loaded; often also "Found too quickly" when the pad rejoins from cache instead of Sync.                                                                                                                                       | Power off (Home ~10s); `bluetoothctl remove <MAC>`; hold Sync until all 4 LEDs flash; re-run `sudo bash scripts/jetson/pair_pro_controller.sh` → `Paired: yes` + `/dev/input/js0`.                                                        | `scripts/jetson/pair_pro_controller.sh`                                                                                                 | Incomplete BT bond (Sync vs cache reconnect). Warn blames `hid_nintendo` when the usual failure is `Paired: no`. **Docs to correct:** `controller/scripts/jetson/CONNECT_PRO_CONTROLLER.md` (Troubleshooting — cover Sync / `Paired: no` / "Found too quickly", not only `hid_nintendo`).                                                                                                                                | yes for gamepad drive                                                 | ~15–30 min; every first BT pair / bad reconnect                      | 3          | AI can draft warn/docs; Human/Person + hardware verify pair                        |
| F6  | controller / run     | After `krabby install` (boot autostart on), `krabby run` fails: `Conflict. The container name "/krabby" is already in use`.                                                                                                                                                                                                                                                      | `docker rm -f krabby` then `krabby run`, or `sudo systemctl restart krabby-locomotion`.                                                                                                                                                   | `krabby run` / `gamepad_cmd`; `krabby-locomotion.service`                                                                               | Install enables systemd unit that already started `--name krabby`. Unit has `ExecStartPre=docker rm -f krabby`; manual `krabby run` does not. **Docs to correct:** `README.md` (§6 Drive with a gamepad); `krabby/README.md` (`krabby run` + Start on boot).                                                                                                                                                             | yes for a fresh manual run                                            | ~2–5 min; every boot+manual `krabby run`                             | 2          | AI can draft docs/code; Human/Person verify boot + manual run                      |
| F7  | controller / run     | Docs / script warn say set `KRABBY_MCU_PORT` when not on `/dev/ttyACM0`. `KRABBY_MCU_PORT=/dev/ttyUSB1 krabby run` still prints `MCU device not found at /dev/ttyACM0`. HAL may still auto-connect to `ttyUSB*` and drive fine.                                                                                                                                                  | Ignore the warning if logs show `Connected to /dev/ttyUSB…` / `MCU connected successfully`.                                                                                                                                               | `krabby/_docker.py` `gamepad_cmd` vs `firmware_cmd`; `_gamepad_launch_script`                                                           | `firmware_cmd` passes `-e KRABBY_MCU_PORT`; `gamepad_cmd` does not, so the in-container check always defaults to `/dev/ttyACM0`. HAL uses `default_port()` and can still find CH340 boards. **Docs to correct:** `controller/scripts/jetson/E2E_GAMEPAD_KRABBY.md` (says set `KRABBY_MCU_PORT` for non-`ttyACM0`, but `krabby run` / `gamepad_cmd` does not forward that env).                                           | no (auto-detect worked); yes if operator trusts the warning and stops | ~5–15 min confusion; every CH340/`ttyUSB`* bring-up                  | 4          | AI can forward env; Human/Person + hardware verify CH340 path                      |
| F8  | controller / run     | `krabby run` prints `error: XDG_RUNTIME_DIR is invalid or not set in the environment` before pygame/controller init.                                                                                                                                                                                                                                                             | Ignore; stack still starts and the Pro Controller enumerates.                                                                                                                                                                             | locomotion container / SDL-pygame                                                                                                       | Missing runtime dir inside the container; cosmetic for gamepad path.                                                                                                                                                                                                                                                                                                                                                     | no                                                                    | ~0–1 min; every `krabby run`                                         | 1          | AI can patch container env; Human/Person verify in locomotion container            |
| F9  | firmware / flash     | Mid-upload Ctrl+C (or port vanish): `cannot open port /dev/ttyACM0`; then `krabby firmware show` → “No attached Mega”; kernel keeps `usb … device descriptor read/64, error -110` / `error -71` on the hub port; no `/dev/ttyACM*`/`ttyUSB*`. Feels like a bricked/corrupt board.                                                                                                | Full power-cycle Mega (+ Orin reboot if still wedged); bypass hub → direct Orin USB; known-good data cable; never interrupt upload; press Mega RESET if upload hangs. Swap cable/port vs second Mega to isolate USB-serial vs sketch.     | `arduino-cli upload` / CH340–ACM enum; powered hub                                                                                      | Interrupted avrdude + flaky full-speed enum on hub; sketch may still be fine while USB-serial won’t enumerate. **Docs:** Appendix B recover note.                                                                                                                                                                                                                                                                        | yes until board reappears                                             | ~15–45 min per stuck board; after local PIN_REV=2 flash / hub        | 4          | hardware + Human/Person recover; AI can draft docs; Human verify                   |
| F10 | firmware / show      | `krabby firmware show` sometimes lists only the FRONT (leader) board even though LEFT/RIGHT are powered and UART-wired; left/right roles missing until the **FRONT USB cable** is unplugged and plugged back in.                                                                                                                                                                 | Unplug FRONT USB → wait a few seconds → replug; re-run `krabby firmware show` until front/left/right all appear.                                                                                                                          | Leader USB / 3-board role election; `krabby firmware show`                                                                              | Likely leader missed SYNC / role election after power or serial reopen (DTR-safe open still leaves a stuck election until USB reset). Not the same as F9 (no tty) — port is up, followers just invisible.                                                                                                                                                                                                                | yes for flash/bringup that require 3 roles                            | ~1–2 min; intermittent after flash, harness, or long session         | 4          | hardware + Human/Person diagnose election; AI can draft docs/retry; Human verify   |
| F11 | bench / CI           | Four-stage harness exists, but the Orin is **not** a GitHub Actions self-hosted runner yet. `bench-harness.yml` would queue forever without a gate. Discord secret **is** set (local + artifact-health proven).                                                                                                                                                                  | Manual harness on Orin; leave `BENCH_RUNNER_ENABLED` false until registered. Procedure: Appendix C.                                                                                                                                       | `.github/workflows/bench-harness.yml`; Appendix C                                                                                       | Runner registration deferred (admin token); not a code gap. Discord secret already set.                                                                                                                                                                                                                                                                                                                                  | yes for commit-triggered hardware bench                               | until runner registered                                              | 3          | Human/Person (admin + operator register runner + enable var); AI docs already      |
| F12 | CI / Actions         | Artifact health locomotion-image annotates: `Node.js 20 is deprecated` — `docker/setup-qemu-action@v3` targets Node 20 but runners force Node 24 ([changelog](https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/)). Warning only; not the cause of a job failure by itself.                                                              | Ignore until Node 20 removal (~2026-09), or bump the action.                                                                                                                                                                              | `.github/workflows/artifact-health.yml` (`uses: docker/setup-qemu-action@v3`)                                                           | Action major still on Node 20; GitHub is migrating JS actions to Node 24. **Fix:** change to `docker/setup-qemu-action@v4` (Node 24 runtime). Re-check any other workflows that pin `@v3`.                                                                                                                                                                                                                               | no (warn); yes after Node 20 removal if still on v3                   | ~5 min when editing workflow                                         | 4          | AI can bump action; Human/Person review CI + confirm workflow green                |
| F13 | CI / artifact-health | Manual **Artifact health** run (Discord): `FAIL — artifact-health` / Failed stage: **locomotion-image**; `packages=success; locomotion-image=failure; firmware-artifact=success`. Node 20 note (F12) is unrelated.                                                                                                                                                               | Open the red **Locomotion image** job → **Pull and smoke-start channel tags** log; fix or relax the check once root cause is known.                                                                                                       | `.github/workflows/artifact-health.yml` (`locomotion-image`); ECR `public.ecr.aws/t7t7b3i3/krabby-locomotion:{mainline,release}-latest` | Job pulls both tags under QEMU `linux/arm64` and requires `docker run … --help` to contain `--teleop-ip`. Failure is pull, run-under-QEMU, or help-text mismatch — **diagnose from Actions log before changing published images**. **Fix:** address whatever the log shows (tag/ECR, QEMU/`docker run`, or update grep / entrypoint expectations); re-run workflow_dispatch to confirm Discord PASS.                     | yes for green artifact-health                                         | ~15–60 min once log is read                                          | 3          | AI can patch workflow; Human/Person confirm Discord PASS / image publish if broken |




## Working command sequence (bring-up baseline)

Documented “few commands” goal (`README.md` Software quick-start): **~6 steps**
(`pip install` → `sudo krabby install` → `firmware show` → `firmware update` → wire hub → pair + `krabby run`).

**Proven path as of 2026-09-29** (front video still open — Appendix D). Tags:
`[doc]` = in quick-start; `[undoc]` = required but not there; `[manual]` = hands-on;
`[blocked]` = not run yet (later stages).

```text
# --- Orin host (assume imaged, networked, SSHable) ---
# [undoc] Python usable for venv (system pip alone is not enough — F1)

python3 -m venv ~/.venv-krabby                          # [undoc] F1
source ~/.venv-krabby/bin/activate                      # [undoc] F1
pip install -U pip                                      # [undoc]
pip install krabby-launcher                             # [doc] (must be inside venv)

sudo -E env PATH="$PATH" "$(which krabby)" install      # [doc] says `sudo krabby install`; [undoc] F2 form required
# (optional) sudo -E env PATH="$PATH" "$(which krabby)" install --no-launch-on-startup
# Replug USB after install.                                 # [doc]

# --- Firmware (three Megas) ---
# Flash one board at a time if first bring-up; then wire all three to powered hub.
krabby firmware show                                    # [doc]
krabby firmware update                                  # [doc] once per board; replug between # [manual]
# Wire FRONT/LEFT/RIGHT Megas → powered hub → Orin          # [doc] [manual]
krabby firmware show                                    # [doc] expect three roles + versions

# Optional GUI jog (repo-only — F3):
#   git clone …/krabby-research && cd … && python -m firmware.gui   # [undoc]

# --- Pro Controller ---
# Clone/repo required for pairing script (F3); not on PyPI.
cd /path/to/krabby-research                             # [undoc] F3
# Power off pad (Home ~10s); if stale: bluetoothctl remove <MAC>   # [undoc] F5 [manual]
# Hold Sync until all 4 LEDs flash rapidly                         # [doc]/manual] easy to miss → F5
sudo bash scripts/jetson/pair_pro_controller.sh         # [doc] via CONNECT_PRO_CONTROLLER.md
ls /dev/input/js*                                       # [doc] expect js0 (and often js1)

# --- Drive (gamepad stack) ---
docker rm -f krabby                                     # [undoc] F6 — boot unit may already own the name
source ~/.venv-krabby/bin/activate                      # if new shell
krabby run                                              # [doc]
# Ignore: MCU not found at /dev/ttyACM0 (F7) if logs show Connected to /dev/ttyUSB*
# Ignore: XDG_RUNTIME_DIR … (F8)
# Drive: hold RT = FR, left stick Y = FRHL, etc.               # [manual]

# --- Fleet (proven for orin1 — enroll + live portal telemetry) ---
# export AWS_ACCESS_KEY_ID=… AWS_SECRET_ACCESS_KEY=… AWS_DEFAULT_REGION=…   # [undoc] ENROLL.md
# python -c "import boto3; print(boto3.client('sts').get_caller_identity())"
# sudo -E env PATH="$PATH" krabby enroll --thing-name orin1                 # [undoc]
# sudo systemctl start krabby-agent                                         # [undoc]
# source ~/.venv-krabby/bin/activate && krabby get telemetry                # [undoc] needs launcher w/ agent cmds
# Confirm portal fleet.krabbyco.com: orin1 online; detail timestamp advances  # [manual]
# Agent-only health may show locomotion inactive / mcu_missing — OK until HAL up
# Fleet HAL (enrolled): sudo -E env PATH="$PATH" "$(which krabby)" run      # [undoc]
#   (krabby-locomotion.service may be missing until `krabby install` — recreate if needed)
# Portal Open teleop: signaling + control proven; front video → Appendix D
```



### Gap to few-commands goal


|                                                                                  | Count                                                                                 |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Documented quick-start steps                                                     | **6**                                                                                 |
| Operator steps in proven path above (commands + required manuals, excl. blocked) | **~18**                                                                               |
| Extra vs doc (undoc commands + pairing caveats + `docker rm`)                    | **~12**                                                                               |
| Manual interventions that are not a single CLI line                              | **~5** (replug/flash cycle, wire hub, Sync hold, drive check; remove-stale as needed) |
| Still blocked for full cold-start                                                | see **Open items**                                                                    |


**Headline:** goal ≈ **6** commands; working path ≈ **18** steps (**~12** undoc). Remaining gaps: Open items.

### Milestone 23 Items Task 1 list


| ID    | Item                                                | Status                                                                                                  |
| ----- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| 1a    | Portal live telemetry, teleop, cameras, gamepad     | **Partial:** telemetry + gamepad + teleop **control** OK; front video → Appendix D                      |
| 1b–1c | Friction log + small items                          | **Done** (this file)                                                                                    |
| 1d    | Bench Orin as CI self-hosted runner                 | **Open** — see Open items / Appendix C                                                                  |
| 1e    | Harness reset + pip install from public index       | **Done** (manual harness / `bench-reset.sh`)                                                            |
| 1f    | Reflash from **published** S3 artifact              | **Waived on this Orin** — PIN_REV=2 local-only (Appendix B); harness skips S3 overwrite for `dev-local` |
| 1g    | Bringup + motion assert                             | **Done** (manual harness motion PASS)                                                                   |
| 1h    | Discord notify (result, commit, stage, run link)    | **Done** locally; CI injects secret when runner enabled                                                 |
| 1i    | Artifact health (packages / image / firmware)       | **Workflows + Discord notify exist;** green image check / F12–F13 → **Task 2**                          |
| 1j    | Watch `mainline` / `release/**`                     | **Done**                                                                                                |
| 1k    | Repro from notification / harness command in output | **Done** (harness logs stage + command)                                                                 |
| 1l    | Ordered command sequence + gap count                | **Done** (this section)                                                                                 |


Remaining Task 1 work is under **Open items**. F12–F13 / Artifact health green → Task 2.

---



## Appendix A — Dual-use Orin: cold-start vs bench venvs

**Constraint:** One Orin is used for both cold-start bring-up and the
bench harness (no second machine). Modes must not share a disposable venv.

### Two venvs (plan)


|                                | Cold-start (manual)                                                | Bench (CI / Install stage)                                     |
| ------------------------------ | ------------------------------------------------------------------ | -------------------------------------------------------------- |
| Path                           | `~/.venv-krabby`                                                   | `~/.venv-krabby-bench`                                         |
| Purpose                        | Day-to-day bring-up, Pro Controller, friction logging              | Fresh `pip install krabby-launcher` from PyPI each harness run |
| Created                        | Once during cold-start (F1)                                        | After each `bench-reset.sh`, or first bench Install            |
| Destroyed by `bench-reset.sh`? | **Never**                                                          | **Always** (when present)                                      |
| Typical packages               | `krabby-launcher`, optionally `krabby-bench` for harness inventory | `krabby-launcher` only (public index; no editable `./krabby`)  |
| Activate                       | `source ~/.venv-krabby/bin/activate`                               | `source ~/.venv-krabby-bench/bin/activate`                     |


**Shared (not per-venv):** `~/.config/krabby/state.json` (image ref/digest from
`krabby install`). Light reset **clears this file** so Install re-pulls and
rewrites state. After a bench cycle, cold-start mode may need
`krabby install` again (or restore from a known digest) before `krabby run` /
`krabby firmware` resolve the image via state.

**Also shared:** Docker images, udev, dialout, `hid_nintendo`, BT controller
bond, repo clone, SSH. Light reset leaves these (gap vs bare Orin).

### Modes on this Orin


| Mode     | Venv                   | Autostart                     | Actions runner (when present)     |
| -------- | ---------------------- | ----------------------------- | --------------------------------- |
| Bring-up | `~/.venv-krabby`       | `krabby-locomotion` optional  | Offline                           |
| Bench    | `~/.venv-krabby-bench` | **Disabled** (avoids F6 race) | Online only while running harness |


Do not leave bring-up and a live bench job overlapping on this host.

### Light reset vs full reset


| Script                           | Use                                                                                                                                                                         |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/jetson/bench-reset.sh`  | Between bench runs (default). Stops containers + locomotion unit, clears `state.json`, removes **only** `~/.venv-krabby-bench`. Optional `--rmi` removes locomotion images. |
| `scripts/jetson/jetson-reset.sh` | Rare “closer to bare” wipe (packages, udev, all krabby images). Does **not** know about the two-venv split — use carefully on dual-use.                                     |




### First-time bench Install after reset

```bash
./scripts/jetson/bench-reset.sh
python3 -m venv ~/.venv-krabby-bench
source ~/.venv-krabby-bench/bin/activate
pip install -U pip && pip install krabby-launcher
sudo -E env PATH="$PATH" "$(which krabby)" install --no-launch-on-startup
krabby firmware show
```

Return to cold-start:

```bash
source ~/.venv-krabby/bin/activate
# if state.json was cleared by bench-reset, re-install (boot unit optional):
# sudo -E env PATH="$PATH" "$(which krabby)" install
```



### Gap vs bare Orin (record for bring-up)

Light reset does **not** re-image the Orin, purge Docker, remove udev/`hid_nintendo`,
unpair the Pro Controller, or delete `~/.venv-krabby` / the git clone. Install bugs
that only appear on a truly bare machine can still hide in that gap.

### Four-stage harness CLI

```bash
cd /path/to/krabby-research
source ~/.venv-krabby/bin/activate
pip install -e ./bench
# Full: reset + install + flash + bringup + motion
krabby-bench harness --repo-root "$(pwd)"
# Or continue after a proven Install without wiping again:
krabby-bench harness --skip-install --no-reset --repo-root "$(pwd)"
```

Implementation: `bench/krabby_bench/_harness.py` (`krabby-bench harness`).
Flash reuses `_smoke.py`. Motion jogs RLKL/RRKL/FLKL/FRHL/FRKL and asserts pot/hall
change on the MCU after stopping the container (HAL obs do not expose pot/hall —
KNOWN-ISSUES #6/#7).

---



## Appendix B — Flash / update firmware for PIN_REV=2 (local `dev-local` only)

`PIN_REV=2` **is for local Uno v0.1 testing only and will not be used going
forward.** Do **not** take the published S3 / `krabby firmware update` artifact
on these boards (different pin map — wrong EN / Hall mapping). Flash from the
**repo tree** with `arduino-cli` so the sketch reports `dev-local`.

**Harness:** when all attached roles are `dev-local`, the flash stage **skips S3
overwrite**. Motion should use **host** repo `firmware/` parsers (`PYTHONPATH` /
`--repo-root`), not the ECR image’s bundled copy. Until boards move off rev 2,
treat published-firmware flash (Milestone item 1f) as waived on this bench.

Ensure `~/.local/bin` is on `PATH`. Install a real `arduino-cli` (not the snap):

```bash
source ~/.venv-krabby/bin/activate
curl -fsSL https://github.com/arduino/arduino-cli/releases/download/v1.1.1/arduino-cli_1.1.1_Linux_ARM64.tar.gz \
  | tar -xz -C ~/.local/bin arduino-cli

# confirm it's the new one, not snap
which arduino-cli   # should be ~/.local/bin/arduino-cli
arduino-cli version

make -C firmware upload-firmware PIN_REV=2
```

Flash **one Mega at a time** (replug USB between boards) if the hub/leader path
is not used for upload. Pass `PORT=` explicitly when the default is wrong
(e.g. `PORT=/dev/ttyUSB0`). **Do not Ctrl+C mid-upload** (F9). If the board
vanishes (`error -110` / no tty): power-cycle, try a direct Orin port, then
re-run upload once `/dev/ttyUSB*` or `/dev/ttyACM*` is back.

After all three are updated:

```bash
krabby firmware show
# expect front/left/right … dev-local
```

Then continue harness motion with `--skip-install --no-reset --repo-root` (Appendix A).

---



## Appendix C — Self-hosted Orin runner (bench CI)

**Status:** `~/actions-runner` (linux-**arm64**) unpacked on the Orin; blocked on a
fresh GitHub **admin** registration token (~1h; stale → `404`). Then `config.sh` +
`svc` + `BENCH_RUNNER_ENABLED=true`. Wrong arch (`linux-x64`) → `Exec format error`.

**Do not** paste tokens into chat/logs. Full procedure (admin + operator + failures):
`[bench/SELF-HOSTED-RUNNER.md](../bench/SELF-HOSTED-RUNNER.md)`.

---



## Appendix D — ZED 2i USB 3 cable (front teleop video)

Teleop **signaling and control** on `orin1` work. Front **video** does not until the
ZED is on a real USB 3 path.

**Symptom:** `lsusb` shows Stereolabs ZED 2i, but HAL logs
`Failed to create ZED camera: CAMERA STREAM FAILED TO START`. Portal Open teleop
sends black frames for `front_rgbd`. `lsusb -t` may show ZED video under a **480M**
(USB 2) hub chain (e.g. Bus 01), not Bus 02/04 SuperSpeed. A wrong USB-C cable
can fail to enumerate at all.

**Resolution:** use a Stereolabs (or known-good) **USB 3 SuperSpeed** cable; plug so
`lsusb -t` shows ZED video at **5000M**. Then restart fleet HAL (`krabby run`) and
confirm `ZED camera initialized` / `front_rgbd ready`, then portal Open teleop with
real front video. Side MaixSense cameras are optional for 1a front video.

**Check before chasing HAL bugs:**

```bash
lsusb | grep -i stereolabs
lsusb -t   # ZED video line must be 5000M, not 480M
```

