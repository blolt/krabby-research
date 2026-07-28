# M16 power-bus wiring artifacts

- `M16-power-bus-wiring.svg` is the legible review diagram required by AC 3j.
- `M16-power-bus-wiring.dot` is its editable Graphviz source.
- `M16-power-bus-wiring.bom.tsv` is a generated connectivity/material list from
  `../docs/M16-POWER-BUS-WIRING.yml`.

Render the review diagram:

```sh
dot -Tsvg assets/M16-power-bus-wiring.dot \
  -o assets/M16-power-bus-wiring.svg
```

Validate the detailed WireViz source and regenerate the material list:

```sh
wireviz -f gst -o /tmp -O M16-power-bus-wiring-detailed \
  docs/M16-POWER-BUS-WIRING.yml
```

WireViz reports unspecified cable lengths as `0 m`. Those entries identify
gauge, conductor count, and connected segments; they are not cut lengths.
Measure routing on the assembled robot, record the cut lengths with the harness
evidence, and update the source before treating the TSV as a construction BOM.
