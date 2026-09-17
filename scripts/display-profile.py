#!/usr/bin/python3
"""Read display state or apply a reviewed profile without automating GUI clicks."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

PROFILES = {"mac": "1920x1080", "ipad": "1600x1050", "ipad-landscape": "1184x824", "ipad-large-text": "1024x768"}
UNIT = "adaptive-display-mode.service"


def backend():
    base = Path(__file__).resolve().parent
    source = base / "resolution_switcher.py"
    if not source.exists():
        source = base.parent / "resolution-switcher/resolution_switcher.py"
    spec = importlib.util.spec_from_file_location("resolution_switcher", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def adaptive_state():
    result = subprocess.run(
        ["systemctl", "--user", "show", UNIT, "--property=LoadState,ActiveState,UnitFileState"],
        capture_output=True, text=True, timeout=5,
    )
    state = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if result.returncode and state.get("LoadState") != "not-found":
        raise RuntimeError(result.stderr.strip() or "Cannot query the target user's systemd session")
    return state


def assert_manual_policy(state):
    if state.get("LoadState") == "not-found":
        return
    if state.get("ActiveState") not in ("inactive", "failed"):
        raise RuntimeError("Automatic display watcher is active. Disable it before selecting a manual profile.")
    if state.get("UnitFileState") not in ("disabled", "masked", "masked-runtime", "static"):
        raise RuntimeError("Automatic display watcher may start again. Disable its automatic start first.")


def assert_chooser_closed():
    result = subprocess.run(
        ["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus", "--object-path", "/org/freedesktop/DBus",
         "--method", "org.freedesktop.DBus.NameHasOwner", "local.kmg.VncResolutionSwitcher"],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode:
        raise RuntimeError("Cannot inspect the desktop session bus; set the target session environment first.")
    if "true" in result.stdout:
        raise RuntimeError("Close the Screen Resolution chooser before applying a profile from the CLI.")


def status(module):
    state = module.query()
    scale = module.vnc_scale()
    return {"desktop": state["framebuffer"], "output": state["output"], "rate": state["rate"],
            "vnc_scale": scale, "native_pixels": scale == "1", "adaptive_service": adaptive_state(),
            "profile": next((key for key, mode in PROFILES.items() if mode == state["mode"] and scale == "1"), None)}


def apply_profile(module, profile, keep):
    assert_manual_policy(adaptive_state())
    assert_chooser_closed()
    old = module.query()
    mode = PROFILES[profile]
    if old["mode"] == mode and old["framebuffer"] == mode and module.vnc_scale() == "1":
        return {"status": "unchanged", "profile": profile, "desktop": mode, "vnc_scale": "1"}
    state, unavailable = module.ensure_ipad_modes()
    if mode not in state["modes"] or mode in unavailable:
        raise RuntimeError("Requested profile is not supported by this output: " + mode)
    windows = module.capture_windows()
    guard = module.start_guard(old, windows=windows)
    try:
        rate = min(state["modes"][mode], key=lambda value: abs(float(value) - 60))
        module.apply_mode(state["output"], mode, rate)
        module.set_vnc_scale("1")
        module.fit_windows(windows, mode)
        # Let the window manager publish the new work area, then clamp windows again.
        module.time.sleep(0.35)
        module.fit_windows(windows, mode)
        actual = module.query()
        if actual["framebuffer"] != mode or actual["mode"] != mode or module.vnc_scale() != "1":
            raise RuntimeError("Profile verification failed; restoring the previous screen")
        module.log_event({"status": "cli-preview", "profile": profile, "from": old["mode"], "to": mode, "vnc_scale": "1"})
        if not keep:
            print(json.dumps({"status": "preview", "desktop": mode, "revert_after_seconds": module.TIMEOUT}), flush=True)
            guard.wait(timeout=module.TIMEOUT + 15)
        result = module.finish_guard(guard, keep=keep)
        guard = None
        if keep and result["status"] != "kept":
            raise RuntimeError("Confirmation deadline expired; the previous screen was restored")
        return {**result, "profile": profile, "desktop": module.query()["framebuffer"], "vnc_scale": module.vnc_scale()}
    finally:
        if guard is not None:
            module.finish_guard(guard, keep=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Read current screen/VNC/service state; no display changes")
    sub.add_parser("profiles", help="List supported profile names; no X session needed")
    apply_parser = sub.add_parser("apply", help="Preview and restore unless --keep is supplied")
    apply_parser.add_argument("profile", choices=PROFILES)
    apply_parser.add_argument("--keep", action="store_true", help="Keep the change after verification")
    args = parser.parse_args(argv)
    try:
        if args.command == "profiles":
            result = {key: {"desktop": mode, "vnc_scale": "1"} for key, mode in PROFILES.items()}
        elif args.command == "status":
            result = status(backend())
        else:
            if os.geteuid() == 0:
                raise RuntimeError("Run as the desktop user, not root")
            folder = Path.home() / ".local/state/vnc-resolution-switcher"
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / "cli-operation.lock").open("w") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError("Another CLI profile operation is running")
                result = apply_profile(backend(), args.profile, args.keep)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
