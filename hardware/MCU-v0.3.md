# Request for Quote: krab v0.3 Per-Leg Controller Board

Krabby Co LLC | July 2026 | Contact: Fletcher

## Overview

We are redesigning the krab robot's motor control electronics from a centralized ATmega + shield stack to a distributed per-leg controller board. This is a redesign of the existing v0.2 power board: the shield board is eliminated entirely, with the microcontroller (STM32G474) moving onto the power board itself. Each of the robot's six legs carries one identical board driving that leg's three brushed actuators.

The six boards communicate over a CAN-FD bus with the bus leader: a Jetson Orin NX on a Seeed reComputer Robotics J4012. The Orin is not a motor controller or carrier for these boards; it is the leader node on the bus, sending motor commands down and receiving position/current telemetry back from each leg board. The chain is daisy-wired leg to leg with the Orin tapping the bus mid-line:

```
+-----------+   +-----------+   +------------+   +--------------+   +-------------+   +------------+   +------------+
| Rear Left |   | Mid Left  |   | Front Left |   | Orin (J4012) |   | Front Right |   | Mid Right  |   | Rear Right |
| leg board |   | leg board |   | leg board  |   |  bus leader  |   |  leg board  |   | leg board  |   | leg board  |
+-----+-----+   +-----+-----+   +-----+------+   +------+-------+   +------+------+   +-----+------+   +-----+------+
      |               |               |                 |                  |                |                |
 =====+===============+===============+=================+==================+================+================+=====
[120R]                                                                                                        [120R]
```

Single CAN-FD bus (CANH / CANL / GND), daisy-chained leg to leg; Orin taps mid-bus; 120R termination at both physical ends (rear legs).

This RFQ covers the design of the leg board: schematic capture, layout, and release to fabrication (JLCPCB). Six boards plus spares will be produced from the single design.

Existing v0.2 design files (redesign baseline):

- Power board: https://github.com/flliver/krabby-research/tree/main/hardware/power-board/v0.2
- Shield (being eliminated): https://github.com/flliver/krabby-research/tree/main/hardware/shield/v0.2
- Motors: https://github.com/flliver/krabby-research/tree/main/hardware/Uno-v0.2/motors

Bus leader hardware: https://www.seeedstudio.com/reComputer-Robotics-J4012-p-6505.html

## Scope of Work

1. Add an STM32G474 (64-pin) directly to the power board, wired to 3x STSPIN9P2x full-bridge drivers (same pin config approach as current board).
2. Replace the BTS7960 half-bridge modules with 3x STSPIN9P2x full bridges, soldered on-board.
3. Add a CAN-FD transceiver off the STM32G474 to receive motor commands and send current sense + hall/pot position over CAN for all three actuators (replacing the 2x20 ribbon cable to the shield). Bus connects via 4-pin JST-GH to the leader. Board must support CAN daisy chain (CAN in and CAN out connectors bussed through).
4. Provide for firmware flashing of the STM32G474 over the CAN bus, using standard practice: bootloader-compatible provisions (BOOT0/option byte handling, board ID readable at boot), suitable for an OpenBLT-style or similar CAN bootloader, so all six boards can be updated in place without SWD access. SWD header retained for initial programming.
5. Swap power connectors to XT series (XT30 per motor, XT60 for incoming power).
6. Upgrade all components to support up to 72V (system pack is 48V max; 72V rating provides headroom).
7. Receive 5V DC logic power via a wide-input (12-72V) buck instead of over the ribbon cable.
8. General cleanup: traces, LEDs, resistors, labels, etc.

## Design Questions

Please answer each of the following in your proposal. These are the core design risks; clear, specific answers here are the main basis for selection.

1. Are you confident that you can properly wire the STM32G474 to the CAN transceiver? What reference design will you use for that?
2. Are you confident you can properly wire the STM32G474 so that its firmware can be updated via CAN? What reference architecture will you use for that? How will you test that it is working correctly prior to printing the board?
3. Do you have confidence in the pin configuration for the STM32G474, CAN transceiver, and STSPIN9P2x, that there are sufficient available pins for all needs?
4. Are you confident that you will be able to pull current sense plus potentiometer and/or hall encoder position from each of the three motors wired to the STSPIN9P2x, and forward those signals to the STM32G474 so they can be sent over CAN? Have you validated the pins are all available and compatible between the chips? Do you have a planned reference design for this?
5. Are you confident you will be able to receive motor command signals for all three motors over the CAN bus, pipe them to the STM32G474, such that firmware can translate those CAN messages into pin outputs to the STSPIN9P2x to change voltage and motor direction for all three motors? Do you have a reference design for this?
6. Are there any features of the STM32G474 or STSPIN9P2x that require additional pinout, header, or other interface on the board that need to be brought out so they can be optionally used? If so, what?
7. Are you confident you will be able to upgrade voltage on the board from 24V to 72V-rated across the entire board? Any concerns or risks to highlight that you will address during the project?
8. Any concerns or questions about connector changes?
9. Any concerns or questions about electromagnetic interference between PWM control signals and high-voltage motor power on the same board?
10. What is your heat management solution for the board?
11. What circuit protection do you plan to implement on the board to prevent burnout due to miswiring of motor or power wires?
12. What status indicators are required for the STM32/STSPIN beyond what is already brought out on the existing board? (PWM EN, PWM L/R, 24V power, 5V power)
13. Are you confident you will be able to properly wire CAN daisy chain support through the CAN transceiver? Which transceiver will you select for this?
14. Do you foresee any issues with JLCPCB part selection for the board? Any issues with a drastically increased BOM? (Expectation is BOM will be lower or neutral for this single board versus the two current boards.)
15. Do you have any other concerns, issues, or questions you would like to highlight before we start?

## Proposal Requirements

Please respond with a clear 1-3 page proposal that includes:

- Answers to the design questions above, numbered to match.
- Your proposed approach and any reference designs you intend to draw from.
- Timeline with estimated dates for schematic, layout, and gerber release.
- Anything you consider out of scope or requiring additional cost.

## Payment Structure

Fixed price, paid by milestone:

| Milestone | Payment |
|---|---|
| Project kickoff | $600 |
| Schematic complete and reviewed | $300 |
| Gerbers complete and released to fab | $1,300 |
| Final bug fixes and closeout | $800 |
| **Total** | **$3,000** |

## Next Steps

Send your proposal by email. Happy to walk through the existing boards, the architecture, or any of the questions on a call before you submit. Looking forward to working with you on this.
