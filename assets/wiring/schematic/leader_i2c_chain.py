from pathlib import Path

import schemdraw
import schemdraw.elements as elm

from diagram import Diagram
from theme import add_title, drawing


NETS = (
    ("+3V3", "VCC", "4/4"),
    ("GND", "GND", "3/4"),
    ("I2C_SDA", "SDA", "2/4"),
    ("I2C_SCL", "SCL", "1/4"),
)
MEGA_PIN_LABELS = ("3V3", "GND", "D20 / SDA", "D21 / SCL")
ADAPTER_PIN_LABELS = ("VCC", "GND", "SDA", "SCL")


def module_pins(
    side: str,
    labels: tuple[str, ...],
    suffix: str = "",
) -> list[elm.IcPin]:
    return [
        elm.IcPin(
            name=label,
            side=side,
            slot=slot,
            anchorname=f"{anchor}{suffix}",
            lblsize=11,
        )
        for label, (_, anchor, slot) in zip(labels, NETS)
    ]


def connect_nets(
    diagram: schemdraw.Drawing,
    source: elm.Ic,
    source_suffix: str,
    destination: elm.Ic,
    destination_suffix: str,
) -> None:
    for _, anchor, _ in NETS:
        diagram.add(
            elm.Wire("-")
            .at(getattr(source, f"{anchor}{source_suffix}"))
            .to(getattr(destination, f"{anchor}{destination_suffix}"))
            .hold()
        )


def build(svg_path: Path) -> None:
    with drawing(svg_path) as diagram:
        add_title(diagram, "LEADER I²C Chain")

        leader = diagram.add(
            elm.Ic(
                size=(4.8, 5.6),
                pins=module_pins("R", MEGA_PIN_LABELS),
            )
            .side("R", spacing=1.0)
            .at((0, 0))
            .theta(0)
            .label("A1\n\nI²C host\n(Leader Mega)")
        )

        adapter = diagram.add(
            elm.Ic(
                size=(4.0, 4.0),
                pins=module_pins("L", ADAPTER_PIN_LABELS, "_IN")
                + [
                    elm.IcPin(
                        name="QWIIC",
                        side="R",
                        slot="1/1",
                        anchorname="QWIIC",
                        lblsize=11,
                    )
                ],
            )
            .at((6.8, 0.8))
            .theta(0)
            .label("A2\n\nQWIIC\nADAPTER")
        )

        imu = diagram.add(
            elm.Ic(
                size=(5.6, 5.6),
                pins=[
                    elm.IcPin(
                        name="QWIIC",
                        side="L",
                        slot="1/1",
                        anchorname="QWIIC_IN",
                        lblsize=11,
                    ),
                    elm.IcPin(
                        name="QWIIC",
                        side="R",
                        slot="1/1",
                        anchorname="QWIIC_OUT",
                        lblsize=11,
                    )
                ],
            )
            .at((13.4, 0))
            .theta(0)
            .label("U1\n\nLSM6DSO IMU\n0x6B")
        )

        oled = diagram.add(
            elm.Ic(
                size=(5.6, 5.6),
                pins=[
                    elm.IcPin(
                        name="QWIIC",
                        side="L",
                        slot="1/1",
                        anchorname="QWIIC_IN",
                        lblsize=11,
                    ),
                    elm.IcPin(name="QWIIC", side="R", slot="1/1",
                              anchorname="QWIIC_OUT", lblsize=11),
                ],
            )
            .at((21.6, 0))
            .theta(0)
            .label("U2\n\nSSD1306 OLED\n0x3D\n128 × 64")
        )

        connect_nets(diagram, leader, "", adapter, "_IN")
        diagram.add(elm.BusLine().at(adapter.QWIIC).to(imu.QWIIC_IN).hold())
        diagram.add(elm.BusLine().at(imu.QWIIC_OUT).to(oled.QWIIC_IN).hold())

        def ina(x: float, reference: str, role: str, address: str, sense: bool = False) -> elm.Ic:
            return diagram.add(
                elm.Ic(
                    size=(5.6, 5.6),
                    pins=[
                        elm.IcPin(name="QWIIC", side="L", slot="1/1",
                                  anchorname="QWIIC_IN", lblsize=11),
                        elm.IcPin(name="QWIIC", side="R", slot="1/1",
                                  anchorname="QWIIC_OUT", lblsize=11),
                        elm.IcPin(name="VBUS", side="B", slot="2/3" if sense else "1/1",
                                  anchorname="VBUS", lblsize=11),
                    ] + ([
                        elm.IcPin(name="VIN−", side="B", slot="1/3",
                                  anchorname="VIN_MINUS", lblsize=11),
                        elm.IcPin(name="VIN+", side="B", slot="3/3",
                                  anchorname="VIN_PLUS", lblsize=11),
                    ] if sense else []),
                ).at((x, 0)).theta(0)
                .label(f"{reference}\n\n{role} INA228\n{address}")
            )

        pack = ina(29.8, "U3", "Pack", "0x40", sense=True)
        midpoint = ina(38.0, "U4", "Midpoint", "0x41")
        diagram.add(elm.BusLine().at(oled.QWIIC_OUT).to(pack.QWIIC_IN).hold())
        diagram.add(elm.BusLine().at(pack.QWIIC_OUT).to(midpoint.QWIIC_IN).hold())

        # Keep both series batteries, fuse and shunt on the same power-path row.
        power_y = -6.5

        def battery(x: float, name: str) -> elm.Ic:
            return diagram.add(
                elm.Ic(
                    size=(4.0, 3.0),
                    pins=[
                        elm.IcPin(name="+", side="L", slot="1/1", anchorname="POS"),
                        elm.IcPin(name="−", side="R", slot="1/1", anchorname="NEG"),
                    ],
                ).at((x, power_y - 1.5)).theta(0).label(f"Battery {name}\n12 V")
            )

        # The left terminal extends 0.5 units beyond each battery body.
        battery_a = battery(midpoint.VBUS.x + 0.5, "A")
        battery_b = battery(pack.VBUS.x + 0.5, "B")
        junction = battery_a.POS
        diagram.add(elm.Line().at(battery_a.POS).to(battery_b.NEG).hold())
        diagram.add(elm.Dot().at(junction).hold())

        def wire(points: list[tuple[float, float]], color: str = "#172033") -> None:
            for start, end in zip(points, points[1:]):
                diagram.add(elm.Line().at(start).to(end).color(color).hold())

        # Direct battery-positive voltage taps, independent of the fused feed.
        wire([pack.VBUS, battery_b.POS])
        wire([midpoint.VBUS, junction])
        diagram.add(elm.Dot().at(battery_b.POS).hold())
        fuse = diagram.add(
            elm.Fuse().at(battery_b.POS).left().length(3.0)
            .label("F1 · 150 A").hold()
        )
        shunt = diagram.add(
            elm.Resistor().at(fuse.end).left().length(3.0).label("Shunt").hold()
        )
        sense_color = "#167b83"
        wire([pack.VIN_MINUS, (pack.VIN_MINUS.x, -2.0),
              (shunt.end.x, -2.0), shunt.end], sense_color)
        # VIN+ crosses the direct VBUS wire with a bridge, not a junction.
        crossing_x = pack.VBUS.x
        wire([pack.VIN_PLUS, (pack.VIN_PLUS.x, -3.0),
              (crossing_x + 0.3, -3.0)], sense_color)
        diagram.add(elm.Arc2(k=0.8).at((crossing_x + 0.3, -3.0))
                    .to((crossing_x - 0.3, -3.0)).color(sense_color).hold())
        wire([(crossing_x - 0.3, -3.0), (shunt.start.x, -3.0),
              shunt.start], sense_color)
        for terminal in [shunt.start, shunt.end]:
            diagram.add(elm.Dot().at(terminal).hold())
        output = (shunt.end.x - 0.7, power_y)
        wire([shunt.end, output])
        diagram.add(elm.Dot(open=True).at(output).hold())
        diagram.add(elm.Label().at((32.6, 6.2))
                    .label("U3: SHUNT open · VBUS open", fontsize=10))
        diagram.add(elm.Label().at((battery_b.POS.x, -8.7))
                    .label("Pack + (24 V nominal)", halign="right"))
        diagram.add(elm.Label().at((junction.x, -8.7)).label("Midpoint"))
        diagram.add(elm.Label().at((battery_a.NEG.x, -8.7)).label("Pack −"))

        diagram.add(
            elm.Label()
            .at((0, -2.4))
            .label(
                "CAUTION: Ensure +3V3 is never accidentally connected to Mega 5V.",
                halign="left",
            )
        )


DIAGRAM = Diagram(
    name=Path(__file__).stem,
    title="Krabby M16 — Leader I²C chain and battery voltage sensing",
    hint="Leader Mega → Qwiic adapter → IMU → OLED → pack INA228 → midpoint INA228. Two 12 V batteries in series; direct battery VBUS taps and a separate pack-positive feed through the 150 A fuse and shunt. Pack VIN+ senses the fuse side; VIN− senses the outgoing side.",
    build=build,
)
