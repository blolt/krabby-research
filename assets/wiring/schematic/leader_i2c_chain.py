from pathlib import Path

import schemdraw
import schemdraw.elements as elm

from diagram import Diagram
from theme import MUTED, add_title, drawing


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
                        elm.IcPin(name="VBUS", side="B", slot="1/3" if sense else "1/1",
                                  anchorname="VBUS", lblsize=11),
                    ] + ([
                        elm.IcPin(name="VIN−", side="B", slot="2/3",
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

        def battery(y: float, name: str) -> elm.Ic:
            return diagram.add(
                elm.Ic(
                    size=(4.0, 3.0),
                    pins=[
                        elm.IcPin(name="+", side="T", slot="1/1", anchorname="POS"),
                        elm.IcPin(name="−", side="B", slot="1/1", anchorname="NEG"),
                    ],
                ).at((34.0, y)).theta(0).label(f"Battery {name}\n12 V")
            )

        battery_b = battery(-9.0, "B")
        battery_a = battery(-15.0, "A")
        junction = (battery_a.POS.x, -10.5)
        diagram.add(elm.Line().at(battery_a.POS).to(battery_b.NEG).hold())
        diagram.add(elm.Dot().at(junction).hold())
        diagram.add(elm.Wire("|-").at(pack.VBUS).to(battery_b.POS).hold())
        diagram.add(elm.Wire("|-").at(midpoint.VBUS).to(junction).hold())
        # Separate sense and fused-feed wires meet at the battery positive terminal.
        diagram.add(elm.Dot().at(battery_b.POS).hold())
        fuse_input = (battery_b.POS.x, -3.5)
        diagram.add(elm.Line().at(battery_b.POS).to(fuse_input).hold())
        fuse = diagram.add(
            elm.Fuse().at(fuse_input).right().length(3.0).label("F1 · 150 A").hold()
        )
        shunt = diagram.add(
            elm.Resistor().at(fuse.end).down().length(2.0)
            .hold()
        )
        sense_color = "#167b83"
        def sense_wire(points: list[tuple[float, float]]) -> None:
            for start, end in zip(points, points[1:]):
                diagram.add(elm.Line().at(start).to(end).color(sense_color).hold())

        sense_wire([pack.VIN_PLUS, (pack.VIN_PLUS.x, -1.5),
                    (shunt.start.x, -1.5), shunt.start])
        # Bridge the VIN− wire over VIN+ without an electrical junction.
        crossing_x = shunt.start.x
        sense_wire([pack.VIN_MINUS, (pack.VIN_MINUS.x, -2.5),
                    (crossing_x - 0.3, -2.5)])
        diagram.add(elm.Arc2(k=0.8).at((crossing_x - 0.3, -2.5))
                    .to((crossing_x + 0.3, -2.5)).color(sense_color).hold())
        sense_wire([(crossing_x + 0.3, -2.5), (40.0, -2.5),
                    (40.0, shunt.end.y), shunt.end])
        for terminal in [shunt.start, shunt.end]:
            diagram.add(elm.Dot().at(terminal).hold())
        diagram.add(elm.Line().at(shunt.end).down().length(0.7).hold())
        diagram.add(elm.Dot(open=True).at((shunt.end.x, shunt.end.y - 0.7)).hold())
        diagram.add(elm.Label().at((32.6, 6.2))
                    .label("U3: SHUNT open · VBUS open", fontsize=10))
        diagram.add(elm.Label().at((38.6, -4.5)).label("Shunt", halign="right"))
        diagram.add(elm.Label().at((34.0, -5.9))
                    .label("Pack + (24 V nominal)", halign="right"))
        diagram.add(elm.Label().at((35.0, -10.5))
                    .label("Midpoint", halign="right"))
        diagram.add(elm.Label().at((36.0, -16.5))
                    .label("Pack −"))

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
