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

# IMU readout states (three-state model, see docs/M16-ERROR-HANDLING.md, PR #3):
# absent (placeholder below) / STALE (sensor present, not responding — the
# "STALE" suffix comes from ImuTelemetry.format_compact) / fresh.
# The em dash means "no IMU segment seen yet" — normal for follower-only
# traffic or firmware predating the IMU segment, so it is not styled as an error.
IMU_READOUT_ABSENT = "IMU: —"
IMU_READOUT_PREFIX = "IMU: "

# Placeholder for a joint cell before its first telemetry arrives.
NO_VALUE_TEXT = "---"

# Fonts: (family, size[, style]).
FONT_STATUS = ("Segoe UI", 10)             # connection status line
FONT_READOUT = ("Segoe UI", 9)             # secondary readouts (IMU row)
FONT_TABLE_HEADER = ("Segoe UI", 9, "bold")
FONT_GROUP_LABEL = ("Segoe UI", 9, "italic")   # FRONT/LEFT/RIGHT dividers
FONT_JOINT_NAME = ("Consolas", 11, "bold")     # monospace so names align
GROUP_LABEL_COLOR = "#666"                 # muted gray for the dividers


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


class KrabbyTestGUI(tk.Tk):
    def __init__(self, port: Optional[str] = None, baud: int = DEFAULT_BAUD):
        super().__init__()
        self.title("Krabby MCU Test")
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._mcu = KrabbyMCUSDK(port=port, baud=baud)
        self._joint_rows: Dict[str, JointRow] = {}
        self._connected = False

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

        # IMU readout (leader board only; shows the absent placeholder until
        # an IMU segment arrives, then fresh values or a STALE suffix).
        imu_row = ttk.Frame(self, padding=(8, 0))
        imu_row.pack(fill="x")
        self._imu_var = tk.StringVar(value=IMU_READOUT_ABSENT)
        ttk.Label(imu_row, textvariable=self._imu_var, font=FONT_READOUT).pack(side="left")

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

        # Read the reader-thread-owned attribute once (it may be reset to None
        # between the guard and the use otherwise).
        imu = self._mcu.imu
        if imu is not None:
            self._imu_var.set(IMU_READOUT_PREFIX + imu.format_compact())

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
