#!/usr/bin/python3
"""Build against headers matching the installed libvncserver; no system edits."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def versions():
    return {
        package: subprocess.check_output(
            ["dpkg-query", "-W", "-f=${Version}", package], text=True
        )
        for package in ("x11vnc", "libvncserver1")
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headers", type=Path, default=Path("/usr/include"))
    parser.add_argument(
        "--header-version",
        required=True,
        help="Version of libvncserver-dev providing these headers",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / ".local/state/vnc-keyboard-mode/build/caps-bridge.so",
    )
    args = parser.parse_args()
    installed = versions()
    if args.header_version != installed["libvncserver1"]:
        raise RuntimeError("Headers must exactly match installed libvncserver1")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    source = ROOT / "keyboard-mode/caps-bridge/bridge.c"
    subprocess.run(
        [
            "gcc",
            "-shared",
            "-fPIC",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-O2",
            "-Wl,-z,relro,-z,now",
            "-I" + str(args.headers),
            str(source),
            "-o",
            str(args.output),
            "-lX11",
            "-ldl",
            "-lpthread",
        ],
        check=True,
    )
    receipt = {
        "architecture": platform.machine(),
        "packages": installed,
        "header_version": args.header_version,
        "binary_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "sources": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, source.with_name("normalize.h"))
        },
    }
    args.output.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"built": str(args.output), **receipt}, indent=2))


if __name__ == "__main__":
    main()
