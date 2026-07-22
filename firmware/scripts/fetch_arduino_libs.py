#!/usr/bin/env python3
"""Materialize the patched Arduino libraries into firmware/arduino/libraries/.

The repo does not commit third-party library source; it commits only the pin
(URL + ref + SHA-256) here and the Krabby delta as a unified diff under
firmware/arduino/patches/. This script downloads each pinned upstream release
archive, verifies its SHA-256, unpacks it into firmware/arduino/libraries/
(gitignored), and applies the committed patch with `git apply`. Design and
alternatives: docs/M16-DESIGN-DECISIONS.md section 2.1.

Idempotent and offline-safe after the first run: a per-library stamp file
records the exact spec (pin + patch content hash) that produced the tree, and
a matching stamp short-circuits before any network I/O. A pin bump or patch
edit invalidates the stamp and re-materializes from scratch (network needed
again for that one run).

Stdlib-only (urllib/hashlib/tarfile/subprocess) so it runs unchanged on the
Makefile's Windows_NT branch; `git` is the only external tool, and it is
already a prerequisite of working in this repo.

Adding a library (e.g. the Task 3 INA228 driver): add one LibSpec row to
LIBRARIES and one patch file under firmware/arduino/patches/ (patch=None if
upstream needs no changes). No new mechanism.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

FIRMWARE_DIR = Path(__file__).resolve().parents[1]
LIBRARIES_DIR = FIRMWARE_DIR / "arduino" / "libraries"
PATCHES_DIR = FIRMWARE_DIR / "arduino" / "patches"


@dataclass(frozen=True)
class LibSpec:
    """One pinned upstream Arduino library."""

    name: str          # directory name under libraries/ (and patch -p1 root)
    url: str           # release archive (tar.gz) for the pinned ref
    ref: str           # human-readable pin: tag = commit SHA
    sha256: str        # of the archive bytes; never a branch, never unpinned
    tar_root: str      # top-level directory inside the archive
    patch: str | None  # filename under firmware/arduino/patches/, or None


LIBRARIES = [
    LibSpec(
        name="SparkFun_Qwiic_6DoF_LSM6DSO_Arduino_Library",
        url=(
            "https://github.com/sparkfun/SparkFun_Qwiic_6DoF_LSM6DSO_Arduino_Library"
            "/archive/refs/tags/v1.0.4.tar.gz"
        ),
        ref="v1.0.4 = 4addc5ffd7cb71a0481aee259ab85c232aa92afe",
        sha256="26df0dc241cea6713d3f53dee542321ceb9e755fdefc5dbb34fbf004ac24ad62",
        tar_root="SparkFun_Qwiic_6DoF_LSM6DSO_Arduino_Library-1.0.4",
        # No patch: unlike the BMI270 (whose 8 KB config file had to be moved to
        # PROGMEM and whose config upload overran the AVR 32-byte Wire TX buffer),
        # the LSM6DSO driver is plain per-register I2C reads with no bulk upload,
        # so it builds unmodified for arduino:avr:mega. patch=None keeps the
        # existing no-patch codepath in _apply_patch.
        patch=None,
    ),
    # Task 2/3: SparkFun Qwiic OLED driver for the krab status render on the
    # 1.3" panel. Pinned to 1.0.9 — >= 1.0.14 adds a driver that includes C++
    # <map> and no longer compiles on AVR (upstream architectures=* overclaim).
    LibSpec(
        name="SparkFun_Qwiic_OLED_Arduino_Library",
        url="https://github.com/sparkfun/SparkFun_Qwiic_OLED_Arduino_Library/archive/refs/tags/v1.0.9.tar.gz",
        ref="v1.0.9 (tag)",
        sha256="245eccce3898ae0b2804d93932e1392fa0df6412bc70ec3710ca483ac2d76a74",
        tar_root="SparkFun_Qwiic_OLED_Arduino_Library-1.0.9",
        patch=None,
    ),
]


def _spec_digest(spec: LibSpec) -> str:
    """Digest of everything that determines the materialized tree.

    Covers the pin and the *content* of the patch file, so editing the patch
    (not just renaming it) re-materializes on the next build.
    """
    h = hashlib.sha256()
    for part in (spec.name, spec.url, spec.ref, spec.sha256, spec.tar_root):
        h.update(part.encode())
        h.update(b"\0")
    if spec.patch is not None:
        h.update((PATCHES_DIR / spec.patch).read_bytes())
    return h.hexdigest()


def _stamp_path(spec: LibSpec) -> Path:
    return LIBRARIES_DIR / f".{spec.name}.stamp"


def _download(spec: LibSpec, dest: Path) -> None:
    try:
        with urllib.request.urlopen(spec.url, timeout=60) as resp:
            dest.write_bytes(resp.read())
    except (urllib.error.URLError, OSError) as exc:
        sys.exit(
            f"ERROR: could not download {spec.name} from {spec.url}\n"
            f"  ({exc})\n"
            f"This one-time fetch needs network access; after it succeeds once,\n"
            f"builds are fully offline (stamp-guarded). Retry with network, or\n"
            f"run this script once on a connected machine and copy the whole\n"
            f"{LIBRARIES_DIR} directory (including its .stamp files) across."
        )
    got = hashlib.sha256(dest.read_bytes()).hexdigest()
    if got != spec.sha256:
        sys.exit(
            f"ERROR: SHA-256 mismatch for {spec.name} archive {spec.url}\n"
            f"  expected {spec.sha256}\n"
            f"  got      {got}\n"
            f"Refusing to build from unverified bytes. GitHub tag archives can be\n"
            f"regenerated (see docs/M16-DESIGN-DECISIONS.md section 2.1 failure\n"
            f"modes (PR #3)); if upstream content is unchanged, escalate to a shallow\n"
            f"clone pinned to the commit SHA in this library's `ref` and re-pin."
        )


def _extract(archive: Path, spec: LibSpec, staging: Path) -> Path:
    with tarfile.open(archive, "r:gz") as tar:
        try:
            tar.extractall(staging, filter="data")  # no links/devices/abs paths
        except TypeError:  # Python < 3.11.4: no filter= (trusted, checksummed bytes)
            tar.extractall(staging)
    root = staging / spec.tar_root
    if not root.is_dir():
        sys.exit(f"ERROR: archive for {spec.name} lacks top-level {spec.tar_root}/")
    return root


def _apply_patch(spec: LibSpec, staging: Path, tree: Path) -> None:
    """Apply the committed delta to the pristine tree.

    `git apply` (not `patch`) for exact, all-or-nothing semantics and Windows
    availability. The patch's paths are rooted at the library name, so the
    tree is renamed to spec.name first and git runs with cwd=staging.

    Two guards against a nasty git behavior: when cwd is inside a git
    repository, `git apply` resolves patch paths against the repo root and
    *silently skips* ("Skipped patch ...", exit 0) any path outside cwd's
    repo-relative prefix — the patch "succeeds" while changing nothing. So
    (a) staging lives in the system temp dir, outside the repo, where git
    falls back to plain cwd-relative `patch -p1` semantics, and (b) any
    "Skipped patch" in the verbose output is treated as failure anyway.
    """
    if spec.patch is None:
        return
    patch_file = PATCHES_DIR / spec.patch
    for step in ("--check", "--apply"):
        result = subprocess.run(
            ["git", "apply", "-v", step, "-p1", str(patch_file)],
            cwd=staging,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or "Skipped patch" in result.stderr:
            sys.exit(
                f"ERROR: git apply {step} failed for {patch_file.name} on the\n"
                f"pristine {spec.name} {spec.ref} tree:\n{result.stderr}\n"
                f"The committed patch must always apply cleanly to the pinned\n"
                f"ref; this means patch and pin have drifted apart (or paths\n"
                f"were skipped). Fix the patch (or the pin) before building."
            )
    assert tree == staging / spec.name


def _materialize(spec: LibSpec) -> str:
    """Fetch + verify + patch one library. Returns 'cached' or 'fetched'."""
    stamp = _stamp_path(spec)
    digest = _spec_digest(spec)
    target = LIBRARIES_DIR / spec.name
    if target.is_dir() and stamp.is_file() and stamp.read_text().strip() == digest:
        return "cached"

    LIBRARIES_DIR.mkdir(parents=True, exist_ok=True)
    # Stage in the system temp dir — deliberately OUTSIDE this git repo; see
    # the `git apply` path-resolution note in _apply_patch.
    with tempfile.TemporaryDirectory(prefix="krabby-arduino-lib-") as tmp:
        staging = Path(tmp)
        archive = staging / "archive.tar.gz"
        _download(spec, archive)
        root = _extract(archive, spec, staging)
        tree = staging / spec.name
        root.rename(tree)
        _apply_patch(spec, staging, tree)
        if stamp.exists():
            stamp.unlink()
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(tree), str(target))
    stamp.write_text(digest + "\n")
    return "fetched"


def main() -> None:
    for spec in LIBRARIES:
        status = _materialize(spec)
        print(f"{spec.name} {spec.ref.split()[0]}: {status} -> "
              f"{LIBRARIES_DIR / spec.name}")


if __name__ == "__main__":
    main()
