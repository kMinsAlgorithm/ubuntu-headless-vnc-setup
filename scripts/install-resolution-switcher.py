#!/usr/bin/python3
"""Install the chooser for the current desktop user without changing resolution."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parent.parent


def profile_cli():
    spec = importlib.util.spec_from_file_location("display_profile", REPO / "scripts/display-profile.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_dependencies():
    required = ("xrandr", "xprop", "x11vnc", "systemctl", "gdbus", "gio", "xdg-user-dir")
    missing = [name for name in required if shutil.which(name) is None]
    result = subprocess.run(["/usr/bin/python3", "-c",
        "import gi; gi.require_version('Gtk','3.0'); gi.require_version('Wnck','3.0'); from gi.repository import Gtk, Wnck; gi.require_foreign('cairo'); import cairo"],
        capture_output=True, text=True, timeout=10)
    if result.returncode:
        missing.append("system python3-gi + GTK3/Wnck3 + python3-cairo/python3-gi-cairo")
    return missing


def desktop_directory(home):
    result = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, check=True, timeout=5)
    path = Path(result.stdout.strip())
    if not path.is_absolute() or path == home:
        raise RuntimeError("Desktop folder is disabled or unknown; specify --desktop-dir")
    return path


def desktop_quote(value):
    if any(c in value for c in "\n\r\0"):
        raise ValueError("Unsupported control character in installation path")
    value = value.replace("%", "%%").replace("\\", "\\\\\\\\")
    for char in ('"', '`', '$'):
        value = value.replace(char, "\\\\" + char)
    return '"' + value + '"'


def install_files(home, desktop):
    """Only files under the selected user directories; return backup receipt."""
    app = home / ".local/share/vnc-resolution-switcher"
    launcher = ("[Desktop Entry]\nVersion=1.0\nType=Application\nName=화면 해상도 선택\n"
                "Name[en]=Screen Resolution\nComment=Mac과 iPad 화면 크기 선택\n"
                f"Exec=/usr/bin/python3 {desktop_quote(str(app / 'resolution_switcher.py'))}\n"
                f"Icon={app / 'display.svg'}\nTerminal=false\nCategories=Settings;HardwareSettings;\nStartupNotify=true\n")
    payload = {
        app / "resolution_switcher.py": (REPO / "resolution-switcher/resolution_switcher.py").read_bytes(),
        app / "display.svg": (REPO / "resolution-switcher/display.svg").read_bytes(),
        app / "display_profile.py": (REPO / "scripts/display-profile.py").read_bytes(),
        home / ".local/share/applications/vnc-resolution-switcher.desktop": launcher.encode(),
        desktop / "화면 해상도 선택.desktop": launcher.encode(),
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup = home / ".local/state/vnc-resolution-switcher/install-backups" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    receipt = {"created_at_utc": stamp, "backup_directory": str(backup), "files": []}
    # Back up all destinations before writing any payload.
    for index, destination in enumerate(payload):
        previous = backup / f"{index:02d}-{destination.name}"
        existed = destination.exists()
        if destination.is_symlink():
            raise RuntimeError("Refusing to overwrite a symlink: " + str(destination))
        if existed:
            shutil.copy2(destination, previous)
        receipt["files"].append({"destination": str(destination), "existed": existed,
                                 "backup": str(previous) if existed else None})
    (backup / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    for destination, data in payload.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + f".install-{os.getpid()}")
        try:
            temporary.write_bytes(data)
            temporary.chmod(0o755 if destination.parent == desktop else 0o644)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    receipt["sha256"] = {str(path): hashlib.sha256(data).hexdigest() for path, data in payload.items()}
    (backup / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="Check dependencies and source files only")
    action.add_argument("--install", action="store_true", help="Install files with a timestamped backup")
    parser.add_argument("--desktop-dir", type=Path, help="Override desktop directory")
    parser.add_argument("--disable-adaptive", action="store_true", help="Also disable the conflicting automatic display watcher")
    args = parser.parse_args(argv)
    try:
        if args.disable_adaptive and not args.install:
            raise RuntimeError("--disable-adaptive requires --install")
        missing = check_dependencies()
        missing_sources = [str(path.relative_to(REPO)) for path in (
            REPO / "resolution-switcher/resolution_switcher.py", REPO / "resolution-switcher/display.svg",
            REPO / "scripts/display-profile.py") if not path.is_file()]
        if missing_sources:
            raise RuntimeError("Missing source files: " + ", ".join(missing_sources))
        if args.check:
            print(json.dumps({"missing_dependencies": missing, "source": str(REPO), "changes": False}, ensure_ascii=False, indent=2))
            return 1 if missing else 0
        if os.geteuid() == 0:
            raise RuntimeError("Run as the desktop user, not root")
        if missing:
            raise RuntimeError("Missing dependencies: " + ", ".join(missing))
        cli = profile_cli()
        cli.assert_chooser_closed()
        before = cli.adaptive_state()
        if not args.disable_adaptive:
            cli.assert_manual_policy(before)
        home = Path.home()
        if any(c in str(home) for c in "\n\r\0"):
            raise RuntimeError("Unsupported control character in home path")
        desktop = args.desktop_dir.expanduser().resolve() if args.desktop_dir else desktop_directory(home)
        receipt = install_files(home, desktop)
        receipt["adaptive_before"] = before
        receipt_path = Path(receipt["backup_directory"]) / "receipt.json"
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        if args.disable_adaptive and before.get("LoadState") != "not-found":
            subprocess.run(["systemctl", "--user", "disable", "--now", "adaptive-display-mode.service"], check=True, timeout=15)
        receipt["adaptive_after"] = cli.adaptive_state()
        cli.assert_manual_policy(receipt["adaptive_after"])
        trusted = subprocess.run(["gio", "set", str(desktop / "화면 해상도 선택.desktop"), "metadata::trusted", "true"],
                                 capture_output=True, text=True, timeout=5)
        receipt["desktop_trusted"] = trusted.returncode == 0
        receipt["display_changed"] = False
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
