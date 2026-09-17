#!/usr/bin/python3
"""Install keyboard chooser and an initially disabled per-user resume service."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true', help='Install files; does not turn VNC keyboard mode on')
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise RuntimeError('대상 데스크톱 사용자로 실행하세요.')
    required = ['x11vnc', 'gsettings', 'gdbus', 'systemctl', 'xdg-user-dir', 'gio', 'ibus']
    missing = [command for command in required if not shutil.which(command)]
    check = subprocess.run(['/usr/bin/python3', '-c', "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk, Gio; assert Gio.SettingsSchemaSource.get_default().lookup('org.freedesktop.ibus.engine.hangul', True) is not None"], capture_output=True)
    if check.returncode:
        missing.append('python3-gi + gir1.2-gtk-3.0 + ibus-hangul')
    print(json.dumps({'missing_dependencies': missing, 'install_requested': args.install}))
    if missing:
        return 1
    if not args.install:
        return 0
    spec = importlib.util.spec_from_file_location('display_installer', ROOT / 'scripts/install-resolution-switcher.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    app = Path.home() / '.local/share/vnc-keyboard-mode/keyboard_mode.py'
    desktop = helper.desktop_directory(Path.home())
    # Same quote/percent escaping rules used by the existing desktop installer.
    quoted = helper.desktop_quote(str(app))
    if any(char in str(app) for char in ('\n', '\r', '\\', '"')):
        raise RuntimeError('사용자 서비스 설치 경로에 지원하지 않는 문자가 있습니다.')
    unit_exec = str(app).replace('%', '%%')
    unit = ('[Unit]\nDescription=Restore selected VNC keyboard mode after x11vnc starts\n'
            'PartOf=graphical-session.target\nAfter=graphical-session-pre.target\n\n'
            '[Service]\nType=simple\n'
            f'ExecStart=/usr/bin/python3 "{unit_exec}" watch\n'
            'Restart=on-failure\nRestartSec=5\n\n[Install]\nWantedBy=graphical-session.target\n')
    launcher = ('[Desktop Entry]\nVersion=1.0\nType=Application\nName=VNC 키보드 모드\n'
                'Name[en]=VNC Keyboard Mode\nComment=Caps Lock 한영 전환 또는 기존 키 설정 복구\n'
                f'Exec=/usr/bin/python3 {quoted} gui\n'
                'Icon=input-keyboard\nTerminal=false\nCategories=Settings;HardwareSettings;\nStartupNotify=true\n')
    payload = {app: (ROOT / 'keyboard-mode/keyboard_mode.py').read_bytes(),
               Path.home() / '.local/share/applications/vnc-keyboard-mode.desktop': launcher.encode(),
               desktop / 'VNC 키보드 모드.desktop': launcher.encode(),
               Path.home() / '.config/systemd/user/vnc-keyboard-mode.service': unit.encode()}
    backup = Path.home() / '.local/state/vnc-keyboard-mode/install-backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    backup.mkdir(parents=True, mode=0o700)
    records = []
    for i, path in enumerate(payload):
        if path.is_symlink():
            raise RuntimeError('심볼릭 링크는 덮어쓰지 않습니다: ' + str(path))
        previous = backup / f'{i:02d}-{path.name}'
        if path.exists():
            shutil.copy2(path, previous)
        records.append({'destination': str(path), 'backup': str(previous) if path.exists() else None})
    receipt = {'files': records, 'keyboard_settings_changed': False, 'service_started': False}
    (backup / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    for path, data in payload.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.install-tmp')
        temporary.write_bytes(data)
        temporary.chmod(0o755 if path.parent == desktop else 0o644)
        temporary.replace(path)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True, timeout=10)
    trust = subprocess.run(['gio', 'set', str(desktop / 'VNC 키보드 모드.desktop'), 'metadata::trusted', 'true'], capture_output=True, timeout=5)
    receipt.update(backup_directory=str(backup), desktop_trusted=trust.returncode == 0,
                   sha256={str(path): hashlib.sha256(data).hexdigest() for path, data in payload.items()})
    (backup / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
