#!/usr/bin/python3
"""Opt-in admin install for the audited x11vnc-physical launcher; restarts VNC once.
Default is read-only check. Does not edit GDM, the framebuffer, auth, or ports.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time
from importlib.util import spec_from_file_location, module_from_spec

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = Path("/usr/local/sbin/x11vnc-physical.sh")
LIBRARY = Path("/usr/local/lib/vnc-keyboard-mode/caps-bridge.so")
STATE = Path("/var/lib/vnc-keyboard-mode/bridge-install.json")
UNIT = "x11vnc-physical.service"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".install-tmp")
    if path.is_symlink() or temporary.is_symlink():
        raise RuntimeError("Refusing symlink: " + str(path))
    with temporary.open("wb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def restart(verify_bridge):
    subprocess.run(["systemctl", "restart", UNIT], check=True, timeout=20)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        pid = subprocess.check_output(
            ["systemctl", "show", UNIT, "-p", "MainPID", "--value"], text=True
        ).strip()
        if pid != "0":
            if not verify_bridge:
                time.sleep(1)
                subprocess.run(["systemctl", "is-active", "--quiet", UNIT], check=True)
                return
            try:
                entries = Path("/proc", pid, "environ").read_bytes().split(b"\0")
                env = {
                    **os.environ,
                    **{
                        k.decode(): v.decode()
                        for part in entries
                        if b"=" in part
                        for k, v in [part.split(b"=", 1)]
                        if k in (b"DISPLAY", b"XAUTHORITY")
                    },
                }
                reply = subprocess.check_output(
                    ["xprop", "-root", "_VNC_KEYBOARD_CAPS_BRIDGE"],
                    env=env,
                    text=True,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                )
                if f"= {pid}, 1" in reply:
                    return
            except (OSError, subprocess.SubprocessError):
                pass
        time.sleep(0.3)
    raise RuntimeError("VNC bridge did not report ready")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument("--install", action="store_true")
    flags.add_argument("--restore", action="store_true")
    parser.add_argument("--artifact", type=Path)
    args = parser.parse_args()
    if args.install or args.restore:
        if os.geteuid() != 0:
            raise RuntimeError(
                "관리자 인증이 필요합니다. sudo로 이 설치기만 실행하세요."
            )
    if args.restore:
        state = json.loads(STATE.read_text())
        if digest(LAUNCHER.read_bytes()) != state["installed_launcher_sha256"]:
            raise RuntimeError("Launcher changed externally; review before restoring")
        atomic(
            LAUNCHER,
            Path(state["original_launcher"]).read_bytes(),
            state["original_mode"],
        )
        restart(False)
        STATE.unlink()
        print(
            "Original launcher restored. Inactive bridge library retained for review."
        )
        return
    if args.artifact is None:
        parser.error("--artifact is required for check/install")
    artifact = args.artifact.resolve()
    receipt = json.loads(artifact.with_suffix(".json").read_text())
    spec = spec_from_file_location(
        "bridge_build", ROOT / "scripts/build-caps-bridge.py"
    )
    build = module_from_spec(spec)
    spec.loader.exec_module(build)
    if (
        receipt["packages"] != build.versions()
        or receipt["architecture"] != platform.machine()
    ):
        raise RuntimeError(
            "Installed library versions/architecture differ from the tested build"
        )
    payload = artifact.read_bytes()
    if digest(payload) != receipt["binary_sha256"]:
        raise RuntimeError("Artifact checksum mismatch")
    for path, sha in receipt["sources"].items():
        if digest((ROOT / path).read_bytes()) != sha:
            raise RuntimeError("Source changed since build; rebuild and test first")
    old = LAUNCHER.read_bytes()
    text = old.decode()
    if f"exec env LD_PRELOAD={LIBRARY} DISPLAY=" in text:
        if LIBRARY.exists() and digest(LIBRARY.read_bytes()) == receipt["binary_sha256"]:
            print(json.dumps({"already_installed": True, "changes": False, "library": str(LIBRARY)}, indent=2))
            return
        raise RuntimeError("Existing bridge differs; restore/review before replacing it")
    anchor = "exec /usr/bin/x11vnc \\\n"
    if text.count(anchor) != 1 or "LD_PRELOAD" in text or '-auth "$AUTH"' not in text:
        raise RuntimeError(
            "Launcher differs from the audited layout; manual review required"
        )
    displays = re.findall(r"-display\s+(:\d+(?:\.\d+)?)\s", text)
    if len(displays) != 1:
        raise RuntimeError("Cannot identify one X11 display")
    patched = text.replace(
        anchor,
        f'exec env LD_PRELOAD={LIBRARY} DISPLAY={displays[0]} XAUTHORITY="$AUTH" /usr/bin/x11vnc \\\n',
    ).encode()
    subprocess.run(["sh", "-n"], input=patched, check=True)
    print(
        json.dumps(
            {
                "ready": True,
                "launcher": str(LAUNCHER),
                "library": str(LIBRARY),
                "vnc_reconnect_required": True,
                "gdm_restart": False,
            },
            indent=2,
        )
    )
    if not args.install:
        return
    if STATE.exists():
        raise RuntimeError(
            "Existing bridge installation receipt found; restore/review before reinstalling"
        )
    backup = Path("/var/backups/vnc-keyboard-mode") / datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%S.%fZ")
    backup.mkdir(parents=True, mode=0o700)
    original = backup / LAUNCHER.name
    shutil.copy2(LAUNCHER, original)
    previous_library = LIBRARY.read_bytes() if LIBRARY.exists() else None
    state = {
        "original_launcher": str(original),
        "original_mode": LAUNCHER.stat().st_mode & 0o777,
        "original_sha256": digest(old),
        "installed_launcher_sha256": digest(patched),
        "build": receipt,
    }
    atomic(STATE, (json.dumps(state, indent=2) + "\n").encode(), 0o600)
    try:
        atomic(LIBRARY, payload)
        atomic(LAUNCHER, patched, state["original_mode"])
        restart(True)
    except Exception:
        atomic(LAUNCHER, old, state["original_mode"])
        if previous_library is not None:
            atomic(LIBRARY, previous_library)
        restart(False)
        STATE.unlink()
        raise
    print(
        json.dumps(
            {"installed": True, "backup": str(backup), "vnc_bridge_ready": True},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
