"""
Krabby MCU test GUI — tkinter app for jogging joints and viewing live telemetry.
Run: python -m firmware.gui [--port COM5]
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from typing import Dict, Optional

from firmware.krabby_mcu import DEFAULT_BAUD, KrabbyMCUSDK, JOINT_GROUP_NAMES
from firmware.interfaces.joint_telemetry import JointTelemetry

JOG_PWM = 200               # jog magnitude sent while a Retract/Extend button is held
TELEMETRY_REFRESH_MS = 100  # GUI poll period; decoupled from the firmware's telemetry tick

# Sensor readouts (IMU, Task 3 BATT) keep the three-state model documented in
# docs/M16-ERROR-HANDLING.md (PR #3): absent (em dash, "no segment seen yet" —
# normal for follower-only traffic or firmware predating the segment, not an
# error) / stale (sensor-level STALE from the IMU valid bit, or link-level when
# no fresh sample within SENSOR_STALE_S) / fresh. The three states now live in
# the ImuRow/BattRow classes below rather than in flat label strings.
SENSOR_STALE_S = 1.0        # readout is "stale" if no fresh sample within this window

# Placeholder for a joint cell before its first telemetry arrives.
NO_VALUE_TEXT = "---"

# Fonts: (family, size[, style]).
FONT_STATUS = ("Segoe UI", 10)             # connection status line
FONT_TABLE_HEADER = ("Segoe UI", 9, "bold")
FONT_GROUP_LABEL = ("Segoe UI", 9, "italic")   # FRONT/LEFT/RIGHT dividers
FONT_JOINT_NAME = ("Consolas", 11, "bold")     # monospace so names align
GROUP_LABEL_COLOR = "#666"                 # muted gray for the dividers

# Sensor block styling: reuse the joint grid's fonts so the IMU/BATT blocks read
# as peer tables. Value cells get a monospace font (the joint grid's own
# "monospace so it aligns" rationale, applied to the dense signed-decimal tuples
# that the scalar joint cells didn't need).
FONT_SENSOR_LABEL = FONT_JOINT_NAME        # Consolas 11 bold, col-0 entity label
FONT_SENSOR_HEADER = FONT_TABLE_HEADER     # Segoe 9 bold caption row
FONT_SENSOR_VALUE = ("Consolas", 10)       # monospace tabular numbers, anchor e
STATE_COLOR_OK = "#2e7d32"
STATE_COLOR_STALE = "#c0392b"


def resolve_imu_state(imu, age_s: Optional[float]) -> tuple[str, str]:
    """Three-state IMU readout decision, as a pure function (no Tk, unit-testable).

    Returns (text, color). Sensor-level STALE (the wire ``valid`` bit is 0)
    beats link-level ``stale`` (no fresh *sample* within SENSOR_STALE_S, measured
    by ``age_s`` — the seconds since the last identity-distinct sample was
    latched). ``age_s`` is None before the first sample (treated as fresh); a
    None ``imu`` is the absent state (em dash, no color).
    """
    if imu is None:
        return "—", ""
    if not imu.valid:
        return "STALE", STATE_COLOR_STALE
    if age_s is not None and age_s > SENSOR_STALE_S:
        return "stale", STATE_COLOR_STALE
    return "fresh", STATE_COLOR_OK


def latch_imu(prev_obj, prev_ts, imu, now):
    """Latch the last-seen IMU sample by object identity (pure, Tk-free).

    Returns the (object, timestamp) to store. The timestamp advances only when a
    genuinely new sample arrives — a distinct object, since each poll builds a
    fresh ImuTelemetry. A dead link keeps handing back the *same* object, so its
    timestamp is left untouched and its age grows past SENSOR_STALE_S. The SDK
    only clears ``.imu`` on connect(), never nulls it between ticks, so identity
    (not a None transition) is the correct freshness signal. ``imu`` may be None
    before the first sample.
    """
    if imu is not None and imu is not prev_obj:
        return imu, now
    return prev_obj, prev_ts


class JointRow:
    """One row in the telemetry grid: name, jog buttons, live values."""

    def __init__(self, parent: tk.Widget, name: str, row: int, jog_cb):
        self.name = name
        self._jog_cb = jog_cb
        self._active_dir = 0

        self.lbl_name = ttk.Label(parent, text=name, font=FONT_JOINT_NAME, width=6)
        self.lbl_name.grid(row=row, column=0, padx=4, pady=2, sticky="w")

        self.btn_retract = ttk.Button(parent, text="\u25C0 Retract", width=10)
        self.btn_retract.grid(row=row, column=1, padx=2, pady=2)
        self.btn_retract.bind("<ButtonPress-1>", lambda e: self._start_jog(1))
        self.btn_retract.bind("<ButtonRelease-1>", lambda e: self._stop_jog())

        self.btn_extend = ttk.Button(parent, text="Extend \u25B6", width=10)
        self.btn_extend.grid(row=row, column=2, padx=2, pady=2)
        self.btn_extend.bind("<ButtonPress-1>", lambda e: self._start_jog(-1))
        self.btn_extend.bind("<ButtonRelease-1>", lambda e: self._stop_jog())

        self.var_pot = tk.StringVar(value=NO_VALUE_TEXT)
        self.var_cur = tk.StringVar(value=NO_VALUE_TEXT)
        self.var_pwm = tk.StringVar(value=NO_VALUE_TEXT)
        self.var_hall = tk.StringVar(value=NO_VALUE_TEXT)

        ttk.Label(parent, textvariable=self.var_pot, width=6, anchor="e").grid(row=row, column=3, padx=4)
        ttk.Label(parent, textvariable=self.var_cur, width=6, anchor="e").grid(row=row, column=4, padx=4)
        ttk.Label(parent, textvariable=self.var_pwm, width=10, anchor="e").grid(row=row, column=5, padx=4)
        ttk.Label(parent, textvariable=self.var_hall, width=6, anchor="e").grid(row=row, column=6, padx=4)

    def _start_jog(self, direction: int):
        self._active_dir = direction
        self._jog_cb(self.name, direction * JOG_PWM)

    def _stop_jog(self):
        self._active_dir = 0
        self._jog_cb(self.name, 0)

    def update_from_telemetry(self, jt: Optional[JointTelemetry]):
        if jt is None:
            return
        self.var_pot.set(str(jt.pot))
        self.var_cur.set(str(jt.current))
        self.var_pwm.set(f"L{jt.pwm[0]} R{jt.pwm[1]}")
        self.var_hall.set(str(jt.saf))


class ImuRow:
    """Global IMU readout in the joint-grid idiom (one per leader board, not per
    joint -> its own block, not a joint column). Caption row above, monospace
    anchor-east value cells below, matching the joint table's fonts/alignment."""

    COLS = ["", "roll°", "pitch°", "aX g", "aY", "aZ",
            "gX °/s", "gY", "gZ", "die°C", "state"]

    def __init__(self, parent: tk.Widget):
        ttk.Label(parent, text="IMU", font=FONT_SENSOR_LABEL, width=6,
                  anchor="w").grid(row=1, column=0, padx=4, pady=2, sticky="w")
        for c, h in enumerate(self.COLS):
            if not h:
                continue
            ttk.Label(parent, text=h, font=FONT_SENSOR_HEADER,
                      anchor="e").grid(row=0, column=c, padx=4, sticky="e")
        self._vars = [tk.StringVar(value="—") for _ in self.COLS]
        for c in range(1, len(self.COLS)):
            ttk.Label(parent, textvariable=self._vars[c], font=FONT_SENSOR_VALUE,
                      width=7, anchor="e").grid(row=1, column=c, padx=4)
        self._state_lbl = parent.grid_slaves(row=1, column=len(self.COLS) - 1)[0]

    def update(self, imu, age_s: Optional[float]):
        if imu is None:
            for v in self._vars[1:]:
                v.set("—")
            self._state_lbl.configure(foreground="")
            return
        ag, gd = imu.accel_g, imu.gyro_dps
        fmt = [None, f"{imu.roll_deg:+.1f}", f"{imu.pitch_deg:+.1f}",
               f"{ag[0]:+.2f}", f"{ag[1]:+.2f}", f"{ag[2]:+.2f}",
               f"{gd[0]:+.1f}", f"{gd[1]:+.1f}", f"{gd[2]:+.1f}",
               f"{imu.temp_c:.1f}"]
        for c in range(1, 10):
            self._vars[c].set(fmt[c])
        # Three-state decision (sensor STALE beats link stale) lives in the
        # module-level pure function so it is unit-testable without a window.
        s, col = resolve_imu_state(imu, age_s)
        self._vars[10].set(s)
        self._state_lbl.configure(foreground=col)


class KrabbyTestGUI(tk.Tk):
    def __init__(self, port: Optional[str] = None, baud: int = DEFAULT_BAUD):
        super().__init__()
        self.title("Krabby MCU Test")
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._mcu = KrabbyMCUSDK(port=port, baud=baud)
        self._joint_rows: Dict[str, JointRow] = {}
        self._connected = False

        # Last-seen sensor sample + timestamp for the link-age "stale" state.
        # KrabbyMCUSDK.imu is only cleared on connect(), never nulled between
        # ticks, so a genuinely new sample is detected by object identity (each
        # poll builds a fresh ImuTelemetry) — a dead link keeps returning the
        # same object, whose age then grows past SENSOR_STALE_S. See latch_imu.
        self._imu_obj = None
        self._imu_ts: Optional[float] = None

        self._build_ui()
        self._connect()

    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        self._status_var = tk.StringVar(value="Connecting...")
        ttk.Label(top, textvariable=self._status_var, font=FONT_STATUS).pack(side="left")

        btn_frame = ttk.Frame(top)
        btn_frame.pack(side="right")
        ttk.Button(btn_frame, text="Hold All", command=self._hold_all).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Neutral (0.5)", command=self._neutral).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Calibrate", command=self._calibrate).pack(side="left", padx=4)

        # IMU + battery-pack readouts (leader board only). These are singletons
        # — one IMU and one pack per board, not per joint — so they render as
        # their own labeled blocks above the joint table (reusing the joint
        # grid's fonts/alignment), not as columns in it. They stay outside the
        # scrolled joint canvas so the globals don't scroll away.
        imu_frame = ttk.Frame(self, padding=(8, 0))
        imu_frame.pack(fill="x")
        self._imu_row = ImuRow(imu_frame)


        sep = ttk.Separator(self, orient="horizontal")
        sep.pack(fill="x", pady=4)

        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self._grid_frame = ttk.Frame(canvas, padding=8)

        self._grid_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._grid_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        headers = ["Joint", "Retract", "Extend", "Pot", "Cur", "PWM", "Hall"]
        for c, h in enumerate(headers):
            ttk.Label(self._grid_frame, text=h, font=FONT_TABLE_HEADER, anchor="center").grid(
                row=0, column=c, padx=4, pady=(0, 4), sticky="ew"
            )

        row = 1
        for group_name, joint_names in JOINT_GROUP_NAMES:
            ttk.Label(
                self._grid_frame, text=f"── {group_name} ──",
                font=FONT_GROUP_LABEL, foreground=GROUP_LABEL_COLOR
            ).grid(row=row, column=0, columnspan=7, sticky="w", pady=(6, 2))
            row += 1
            for jname in joint_names:
                jr = JointRow(self._grid_frame, jname, row, self._jog_joint)
                self._joint_rows[jname] = jr
                row += 1

    def _connect(self):
        def _do():
            ok = self._mcu.connect()
            self.after(0, self._on_connected, ok)

        threading.Thread(target=_do, daemon=True).start()

    def _on_connected(self, ok: bool):
        if ok:
            self._connected = True
            self._status_var.set(f"Connected: {self._mcu.port}")
            self._poll_telemetry()
        else:
            self._status_var.set("Connection failed")
            messagebox.showerror("Connection Error", f"Could not connect to {self._mcu.port}")

    def _poll_telemetry(self):
        if not self._connected:
            return
        for name, jr in self._joint_rows.items():
            jt = self._mcu.joints.get(name)
            jr.update_from_telemetry(jt)

        # Latch the last-seen sample by object identity: the SDK never nulls
        # .imu between ticks (only connect() clears it), so a distinct object —
        # each poll builds a new ImuTelemetry — is the only signal of a live
        # link. A dead link keeps returning the same object, whose age then
        # grows past SENSOR_STALE_S and flips the row to "stale".
        imu = self._mcu.imu
        self._imu_obj, self._imu_ts = latch_imu(
            self._imu_obj, self._imu_ts, imu, time.time()
        )
        age = None if self._imu_ts is None else (time.time() - self._imu_ts)
        self._imu_row.update(self._imu_obj, age)

        if self._mcu.last_error:
            self._status_var.set(f"Error: {self._mcu.last_error}")
        elif self._mcu.last_feedback_ts:
            age = time.time() - self._mcu.last_feedback_ts
            if age < 1.0:
                self._status_var.set(f"Connected: {self._mcu.port}")
            else:
                self._status_var.set(f"Connected: {self._mcu.port} (stale {age:.0f}s)")

        self.after(TELEMETRY_REFRESH_MS, self._poll_telemetry)

    def _jog_joint(self, name: str, pwm: int):
        if not self._connected:
            return
        self._mcu.send_command_jog(name, pwm)

    def _hold_all(self):
        if self._connected:
            self._mcu.send_command_joints_hold()

    def _neutral(self):
        if not self._connected:
            return
        cmds = {}
        for _, names in JOINT_GROUP_NAMES:
            for n in names:
                cmds[n] = 0.5
        self._mcu.send_command_joints(cmds)

    def _calibrate(self):
        if not self._connected:
            return
        if messagebox.askyesno("Calibrate", "This will move ALL limbs to find limits. Continue?"):
            self._mcu.send_command_calibrate()

    def _on_close(self):
        self._connected = False
        try:
            self._mcu.send_command_joints_hold()
        except Exception:
            pass
        self._mcu.close()
        self.destroy()
