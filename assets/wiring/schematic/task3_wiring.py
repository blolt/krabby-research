from pathlib import Path

import schemdraw.elements as elm

from diagram import Diagram
from theme import drawing

POWER = "#b33b32"
SENSE = "#9a6900"
QWIIC = "#167b83"
SIGNAL = "#325fa2"


def build(svg_path: Path) -> None:
    with drawing(svg_path) as d:
        def label(x, y, text, size=11, color="#172033", align="center"):
            d.add(elm.Label().at((x, y)).label(text, fontsize=size,
                  color=color, halign=align))

        def box(x, y, w, h, text):
            d.add(elm.Ic(size=(w, h)).at((x, y)).label(text).theta(0))

        def wire(points, color=SIGNAL, width=1.8):
            for a, b in zip(points, points[1:]):
                d.add(elm.Line().at(a).to(b).color(color).linewidth(width).hold())

        def net(x, y, text, color=SENSE):
            d.add(elm.Dot().at((x, y)).color(color))
            label(x, y + .55, text, 10, color)

        label(0, 28, "KRABBY M16 / TASK 3 — POWER, SENSORS / CONTROLLERS", 18, align="left")
        label(0, 26.7, "Connection overview · matching net names are electrically connected", 11, align="left")

        # Series batteries and the only high-current positive feed.
        box(0, 21, 5, 3, "BATTERY B\n12 V LiFePO4")
        box(0, 16, 5, 3, "BATTERY A\n12 V LiFePO4")
        for y in (22.5, 17.5):
            label(.35, y, "−", 14)
            label(4.65, y, "+", 14)
        wire([(0, 22.5), (-1, 22.5), (-1, 20), (6, 20), (6, 17.5), (5, 17.5)], POWER, 3)
        net(6, 20, "MIDPOINT")
        wire([(0, 17.5), (-2, 17.5), (-2, 15), (6, 15)], POWER, 3)
        net(6, 15, "PACK− / GND", POWER)
        wire([(5, 22.5), (8, 22.5)], POWER, 3)
        d.add(elm.Fuse().at((8, 22.5)).to((11, 22.5)).color(POWER).label("F1 · 150 A"))
        label(9.5, 24.5, "First element at Pack+", 10)
        wire([(11, 22.5), (14, 22.5)], POWER, 3)
        d.add(elm.Resistor().at((14, 22.5)).to((18, 22.5)).color(POWER)
              .label("EXTERNAL SHUNT\n200 A / 75 mV · 0.375 mΩ"))
        wire([(18, 22.5), (25, 22.5)], POWER, 3)
        box(25, 21, 9, 3, "OCTOPUS / 24 V DISTRIBUTION\nMotor power and MCU supply branches")
        wire([(14, 22.5), (14, 20)], SENSE)
        wire([(18, 22.5), (18, 20)], SENSE)
        net(14, 20, "KELVIN+")
        net(18, 20, "KELVIN−")
        wire([(22, 22.5), (22, 18)], SENSE)
        net(22, 18, "LOAD+ / VBUS")
        label(16, 17, "Kelvin leads: small sense screws\nVBUS: load-side power stud", 10)
        wire([(29.5, 21), (29.5, 19)], POWER, 3)
        net(29.5, 19, "PACK− / GND", POWER)
        wire([(34, 22.5), (37, 22.5)], POWER, 3)
        box(37, 20, 8, 5, "MCU SUPPLY REGULATION\n\nFrom octopus LOAD+ / GND\nConverter arrangement, voltage\nand connectors to be confirmed")
        for x, name, end_y in ((38, "LEADER_PWR", 18),
                               (41, "LEFT_PWR", 16.5),
                               (44, "RIGHT_PWR", 15)):
            wire([(x, 20), (x, end_y)], POWER, 2.5)
            net(x, end_y, name, POWER)

        # Qwiic cables contain 3V3, GND, SDA and SCL; power sense uses named nets.
        box(0, 6, 6, 7, "A1\n\nLEADER MEGA\nFront · FL / FR")
        box(8, 9, 3, 3, "A2\nQwiic\nadapter")
        wire([(6, 10.5), (8, 10.5)], QWIIC, 3)
        label(7, 13.5, "3V3 / GND\nD20 SDA / D21 SCL", 10)
        box(13, 9, 5, 3, "LSM6DSO IMU\n0x6B")
        box(20, 9, 5, 3, "SSD1306 OLED\n0x3D · 128 × 64")
        box(27, 9, 5, 3, "PACK INA228\nSparkFun · 0x40")
        box(34, 9, 5, 3, "MIDPOINT INA228\nSparkFun · 0x41")
        for start, end in ((11, 13), (18, 20), (25, 27), (32, 34)):
            wire([(start, 10.5), (end, 10.5)], QWIIC, 3)
        for x, text in ((27.5, "IN+\nKELVIN+"), (29.5, "IN−\nKELVIN−"), (31.5, "VBUS\nLOAD+"),
                        (34.5, "IN+ / IN−\nPACK−"), (38, "VBUS\nMIDPOINT")):
            wire([(x, 12), (x, 13.2)], SENSE)
            label(x, 14.2, text, 10, SENSE)
        label(21, 7.9, "QWIIC: 3.3 V + GND + SDA + SCL", 11, QWIIC)
        label(32.5, 6.5, "Both INA boards: SHUNT open; VBUS open\nPack: A0/A1 closed · Midpoint: A0 open, A1 closed", 10)
        wire([(-3, 9.5), (0, 9.5)], POWER, 2.5)
        net(-3, 9.5, "LEADER_PWR", POWER)
        label(3, 7.5, "Power return: PACK− / GND", 10)

        # Signal bundles show the repeated actuator channels without pin fan-out.
        box(13, 1, 8, 3, "FRONT H-BRIDGE BOARDS\n6 motor channels · LOAD+ / GND")
        box(25, 1, 9, 3, "FRONT ACTUATORS\nFL + FR · 3 per leg\nMotor pair + potentiometer feedback")
        wire([(6, 7), (10, 7), (10, 2.5), (13, 2.5)])
        label(10, 0, "PWM / enable → drivers\nCurrent sense → MCU", 10)
        wire([(21, 2.5), (25, 2.5)])
        label(23, 3.4, "Motor pairs", 10)
        wire([(29.5, 1), (29.5, -1.8), (7, -1.8), (7, 6), (6, 6)])
        label(21, -1.3, "Potentiometer supply / GND / position → MCU ADC", 10)

        box(0, -8, 10, 3, "LEFT FOLLOWER MEGA\nML + RL · 6 actuator channels\nLocal H-bridges + motor / pot wiring")
        box(15, -8, 10, 3, "RIGHT FOLLOWER MEGA\nMR + RR · 6 actuator channels\nLocal H-bridges + motor / pot wiring")
        wire([(2, 6), (2, -3.5), (5, -3.5), (5, -5)])
        wire([(4, 6), (4, -2.8), (20, -2.8), (20, -5)])
        label(1, -2, "Serial1\nTX1 D18\nRX1 D19", 10, align="right")
        label(21, -4, "Serial2 · TX2 D16 / RX2 D17", 10, align="left")
        label(12.5, -9.3, "UART bundles: leader TX → follower RX; leader RX ← follower TX; common GND\nFollower uplink: Serial1 or Serial2 as detected by firmware. All controllers share PACK− reference.", 11)
        wire([(-3, -6.5), (0, -6.5)], POWER, 2.5)
        net(-3, -6.5, "LEFT_PWR", POWER)
        wire([(28, -6.5), (25, -6.5)], POWER, 2.5)
        net(28, -6.5, "RIGHT_PWR", POWER)
        label(31, -5.5, "Local H-bridges: octopus LOAD+\nMCU power: regulated octopus branches\nAll returns → PACK− / GND", 10, align="left")
        label(0, -11, "Sense leads require suitable branch protection at the battery taps. Do not apply pack voltage to MCU or Qwiic power pins.", 10, align="left")


DIAGRAM = Diagram(
    name=Path(__file__).stem,
    title="Krabby M16 — Task 3 wiring",
    hint="Power path, SparkFun INA228 sense connections, Qwiic chain and controller/actuator links. Zoom to inspect labels.",
    build=build,
)
