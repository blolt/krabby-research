"""The forward-walk POLICY OF RECORD (``crab_hex_forward_task/policy/``) stays consistent.

``policy/manifest.yaml`` declares the shipped head (``current``) and the stage heads it was trained through
(1a -> 2a -> 2b -> 2c -> 3a) plus the shared training assets it depends on (``assets:``, e.g. the RSI bank).
Every declared file must be present, tracked by git, sha-pinned to the manifest, and (for stages) be the only
checkpoint in its folder; the README is generated from the manifest by ``experiments/tools/bundle_policy.py
--sync`` and must mention every stage and asset.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
PKG = REPO / "parkour" / "parkour_tasks" / "parkour_tasks" / "crab_hex_forward_task"
POLICY = PKG / "policy"
TOOL = PKG / "experiments" / "tools" / "bundle_policy.py"


def _tool():
    spec = importlib.util.spec_from_file_location("bundle_policy", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bundle_policy"] = mod
    spec.loader.exec_module(mod)
    return mod


def _tracked() -> set[str]:
    out = subprocess.run(["git", "ls-files", "--", str(POLICY.relative_to(REPO))], cwd=REPO,
                         capture_output=True, text=True, check=True)
    return {l for l in out.stdout.splitlines() if l}


def test_manifest_and_files_are_consistent():
    tool = _tool()
    m = tool.load_manifest()
    assert m["task"] == "crab_hex_forward_task" and m["plant"] == "A15+B"
    problems = tool.check(m)
    assert not problems, problems


def test_stage_order_and_chain():
    m = yaml.safe_load((POLICY / "manifest.yaml").read_text())
    phases = [s["phase"] for s in m["stages"]]
    assert phases == ["1a", "2a", "2b", "2c", "3a"], phases
    assert m["stages"][0]["resume_from"] == "scratch"
    for prev, s in zip(m["stages"], m["stages"][1:]):
        assert prev["dir"] in s["resume_from"], f"{s['dir']} must resume from {prev['dir']}"
    assert m["current"] == m["stages"][-1]["dir"]


def test_every_policy_file_is_tracked_and_nothing_else():
    m = yaml.safe_load((POLICY / "manifest.yaml").read_text())
    tracked = _tracked()
    rel = POLICY.relative_to(REPO)
    expected = ({f"{rel}/{s['dir']}/{s['file']}" for s in m["stages"]}
                | {f"{rel}/{a['dir']}/{a['file']}" for a in m.get("assets", [])}
                | {f"{rel}/manifest.yaml", f"{rel}/README.md"})
    assert expected <= tracked, sorted(expected - tracked)
    on_disk = {str(p.relative_to(REPO)) for p in POLICY.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    assert on_disk == expected, sorted(on_disk ^ expected)


def test_readme_is_generated_from_the_manifest():
    tool = _tool()
    m = tool.load_manifest()
    assert (POLICY / "README.md").read_text() == tool.readme_text(m), "policy/README.md drifted: run bundle_policy.py --sync"
    text = (POLICY / "README.md").read_text()
    for s in m["stages"]:
        assert f"`{s['dir']}/`" in text and s["sha256"] in text
    for a in m.get("assets", []):
        assert f"`{a['dir']}/{a['file']}`" in text and a["sha256"] in text


def test_rsi_bank_asset_is_the_bank_the_presets_use():
    """The bundled RSI bank is byte-identical to the bank every KRABBY_PHASE preset seeds resets from."""
    sys.path.insert(0, str(PKG / "config" / "crab_hex"))
    import crab_hex_phases as ph  # noqa: E402

    tool = _tool()
    m = tool.load_manifest()
    banks = [a for a in m.get("assets", []) if a["file"].startswith("rsi_bank")]
    assert banks, "policy manifest declares no RSI bank asset"
    preset_bank = Path(ph.FORMATION["KRABBY_RSI_BANK"])
    assert preset_bank.exists(), preset_bank
    assert tool.sha256_of(preset_bank) == banks[0]["sha256"]
    for name in ("1a", "2a", "2b", "2c", "3a"):
        assert ph.PHASES[name].env.get("KRABBY_RSI_BANK") == str(preset_bank), name
        assert ph.PHASES[name].env.get("KRABBY_RSI_FRAC") == "0.2", name
