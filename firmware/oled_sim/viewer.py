"""Render KrabState scenes to a self-contained HTML gallery (scaled, pixel-perfect).

Both John (on claude.ai) and Claude (fetching the artifact) view the exact 128x64
1-bit output. Grouped by scenario; add render variants to VARIANTS to compare styles
side by side. What you see here is what the panel shows.
"""
from __future__ import annotations

from krab import KrabState, render

L = lambda h, k="hold": (h, k)  # leg = (hip, knee)


def _canvas(name, tag, caption, frame, scale=4):
    w, h = 128, 64
    pts = ",".join(f"[{x},{y}]" for y, row in enumerate(frame.to_rows())
                   for x, c in enumerate(row) if c == "#")
    cid = name.replace(" ", "_")
    return f"""
    <figure class="module">
      <div class="bezel"><canvas id="c_{cid}" width="{w*scale}" height="{h*scale}"></canvas></div>
      <figcaption><span class="tag">{tag}</span>{caption}</figcaption>
    </figure>
    <script>(function(){{const s={scale},g=document.getElementById("c_{cid}").getContext("2d");
      g.fillStyle="#05080b";g.fillRect(0,0,{w*scale},{h*scale});
      g.shadowColor="#86e8ff";g.shadowBlur={max(1,scale-2)};g.fillStyle="#86e8ff";
      for(const[x,y]of[{pts}])g.fillRect(x*s,y*s,s,s);}})();</script>"""


def build(scenes):
    mods = "".join(_canvas(n, t, c, render(st)) for n, t, c, st in scenes)
    return f"""<header>
      <h1>Krab status screen &mdash; render bring-up</h1>
      <p class="meta">SparkFun Qwiic OLED 1.3&Prime; &middot; 128&times;64 &middot; 1-bit &middot; pixel-accurate sim (library fonts) &middot; 4&times;</p>
      <p class="note">Body solid when healthy (no dark ⊥ seam / beetle line); the split reveals itself only when a board goes dark. Yaw+hip+knee = 18 glyphs.</p>
    </header>
    <main class="grid">{mods}</main>
    <style>
      :root{{--ground:#05080b;--bezel:#161d24;--hair:#1e2a33;--ink:#c3d2dd;--mute:#63747f;--phosphor:#86e8ff;--warn:#e6a545}}
      *{{box-sizing:border-box}}
      body{{background:var(--ground);color:var(--ink);margin:0;padding:28px 24px 40px;font-family:ui-monospace,"SF Mono",Menlo,monospace;-webkit-font-smoothing:antialiased}}
      header{{max-width:960px;margin:0 auto 24px}}
      h1{{font-family:ui-sans-serif,system-ui,sans-serif;font-size:19px;font-weight:650;letter-spacing:-.01em;margin:0 0 6px;text-wrap:balance}}
      .meta{{color:var(--mute);font-size:11.5px;letter-spacing:.02em;margin:0 0 12px}}
      .note{{color:var(--warn);font-size:11.5px;line-height:1.5;margin:0;border-left:2px solid var(--warn);padding:2px 0 2px 10px}}
      .grid{{max-width:960px;margin:0 auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(272px,1fr));gap:18px}}
      .module{{margin:0}}
      .bezel{{background:var(--bezel);border:1px solid var(--hair);border-radius:9px;padding:11px;box-shadow:inset 0 1px 0 #232f38,0 1px 3px rgba(0,0,0,.5)}}
      canvas{{width:100%;height:auto;image-rendering:pixelated;border-radius:3px;display:block;background:var(--ground)}}
      figcaption{{color:var(--mute);font-size:11.5px;line-height:1.5;margin-top:10px;display:flex;gap:8px;align-items:baseline}}
      .tag{{color:var(--phosphor);font-size:10px;letter-spacing:.08em;text-transform:uppercase;border:1px solid var(--hair);border-radius:4px;padding:1px 6px;flex:none}}
    </style>"""


def default_scenes():
    H = ("hold", "hold", "hold")                     # yaw, hip, knee
    return [
        ("nominal", "⊥-body", "all boards present, all joints holding",
         KrabState(legs=[H] * 6)),
        ("walking", "⊥-body", "yaw hold, hips extend, knees retract",
         KrabState(legs=[("hold", "extend", "retract")] * 6, roll=3, pitch=-1, pack_v=24.0)),
        ("left-down", "⊥-body", "LEFT board missing (top-left region dark)",
         KrabState(controllers={"FRONT": True, "LEFT": False, "RIGHT": True},
                   legs=[("retract", "extend", "retract"), H, H,
                         ("hold", "disc", "hold"), H, H],
                   role="FRONT", roll=5, pitch=-2, pack_v=24.1)),
        ("degraded", "⊥-body", "only FRONT present; several joints disc; low batt",
         KrabState(controllers={"FRONT": True, "LEFT": False, "RIGHT": False},
                   legs=[H, ("hold", "hold", "disc"), ("disc", "disc", "disc"),
                         ("disc", "disc", "disc"), ("disc", "hold", "hold"), ("disc", "disc", "disc")],
                   batt=(0.3, 0.15), roll=-12, pitch=8, pack_v=22.6)),
        ("unknown", "⊥-body", "role election failed: UNKWN",
         KrabState(role="UNKWN", controllers={"FRONT": True, "LEFT": False, "RIGHT": False},
                   legs=[H] * 6, pack_v=24.0)),
    ]


if __name__ == "__main__":
    import sys
    out = build(default_scenes())
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/krab.html"
    with open(path, "w") as f:
        f.write(out)
    print(f"wrote {path}")
