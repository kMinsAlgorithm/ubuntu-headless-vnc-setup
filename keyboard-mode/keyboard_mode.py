#!/usr/bin/python3
"""Reversible x11vnc Caps Lock -> Hangul profile, with a small desktop chooser."""
import argparse
from contextlib import contextmanager, nullcontext
import ctypes
import ctypes.util
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

STATE_DIR = Path.home() / '.local/state/vnc-keyboard-mode'
STATE_FILE = STATE_DIR / 'state.json'
UNIT = 'vnc-keyboard-mode.service'
SWITCH_KEYS = 'Hangul,Shift+space,Control+space'



@contextmanager
def vnc_control_lock():
    """x11vnc uses one X property for all requests; serialize our tools."""
    path = Path.home() / '.local/state/vnc-control.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        deadline = time.monotonic() + 12
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('VNC 설정 조회가 진행 중입니다. 잠시 뒤 다시 시도하세요.')
                time.sleep(0.02)
        yield


def run(*args, timeout=8):
    with vnc_control_lock() if Path(args[0]).name == 'x11vnc' else nullcontext():
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                                env={**os.environ, 'LC_ALL': 'C'})
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or '명령 실패: ' + args[0])
    return result.stdout.strip()


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as stream:
        os.chmod(temporary, 0o600)
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def load_state():
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else None


@contextmanager
def operation_lock():
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (STATE_DIR / 'operation.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('다른 키보드 설정 작업이 진행 중입니다. 잠시 뒤 다시 눌러 주세요.')
        yield


def remap_for_vnc(original):
    """Keep unrelated mappings; refuse opaque mapping files/macros."""
    pairs = original.split(',') if original else []
    if any(not re.fullmatch(r'[A-Za-z0-9_]+-[A-Za-z0-9_]+', pair) for pair in pairs):
        raise RuntimeError('기존 VNC remap이 파일 또는 특수 형식입니다. 기존 매핑 검토가 필요합니다.')
    pairs = [pair for pair in pairs if pair.split('-', 1)[0] not in ('Caps_Lock', '0xffe5', '0xFFE5')]
    return ','.join([*pairs, 'Caps_Lock-Hangul'])


class XkbState(ctypes.Structure):
    _fields_ = [('group', ctypes.c_ubyte), ('locked_group', ctypes.c_ubyte),
                ('base_group', ctypes.c_ushort), ('latched_group', ctypes.c_ushort),
                *[(name, ctypes.c_ubyte) for name in ('mods', 'base_mods', 'latched_mods', 'locked_mods',
                  'compat_state', 'grab_mods', 'compat_grab_mods', 'lookup_mods', 'compat_lookup_mods')],
                ('ptr_buttons', ctypes.c_ushort)]


def caps_lock(clear=False):
    """Query/clear only LockMask; never send keys or alter NumLock/held modifiers."""
    lib = ctypes.CDLL(ctypes.util.find_library('X11') or 'libX11.so.6')
    lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib.XOpenDisplay.restype = ctypes.c_void_p
    lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    lib.XkbGetState.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(XkbState)]
    lib.XkbLockModifiers.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
    lib.XkbLatchModifiers.argtypes = lib.XkbLockModifiers.argtypes
    lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    display = lib.XOpenDisplay(None)
    if not display:
        raise RuntimeError('대상 X11 화면에 접근하지 못했습니다. DISPLAY/XAUTHORITY를 확인하세요.')
    try:
        if clear:
            if not lib.XkbLockModifiers(display, 0x100, 2, 0) or not lib.XkbLatchModifiers(display, 0x100, 2, 0):
                raise RuntimeError('Caps Lock 잠금을 해제하지 못했습니다.')
            lib.XSync(display, 0)
        state = XkbState()
        if lib.XkbGetState(display, 0x100, ctypes.byref(state)) != 0:
            raise RuntimeError('키보드 잠금 상태를 읽지 못했습니다.')
        return bool((state.locked_mods | state.latched_mods) & 2)
    finally:
        lib.XCloseDisplay(display)


def server_identity(pid):
    stat = Path(f'/proc/{int(pid)}/stat').read_text().rsplit(')', 1)[1].split()
    return f"{Path('/proc/sys/kernel/random/boot_id').read_text().strip()}:{pid}:{stat[19]}"


class Backend:
    def __init__(self):
        if os.geteuid() == 0:
            raise RuntimeError('root가 아닌 대상 데스크톱 사용자로 실행하세요.')
        if os.environ.get('XDG_SESSION_TYPE') == 'wayland':
            raise RuntimeError('이 도구는 Xorg/x11vnc용입니다. Wayland 세션에는 적용하지 않습니다.')
        import gi
        from gi.repository import Gio, GLib
        context = GLib.MainContext.default()
        for _ in range(50):
            if not context.pending():
                break
            context.iteration(False)
        self.Gio = Gio
        schemas = Gio.SettingsSchemaSource.get_default()
        if schemas is None or schemas.lookup('org.freedesktop.ibus.engine.hangul', True) is None:
            raise RuntimeError('IBus 한글 설정을 찾지 못했습니다. ibus-hangul 설치를 확인하세요.')
        self.settings = Gio.Settings.new('org.freedesktop.ibus.engine.hangul')

    def ime(self):
        user = self.settings.get_user_value('switch-keys')
        return {'value': self.settings.get_string('switch-keys'), 'user': user.unpack() if user is not None else None}

    def set_ime(self, snapshot):
        if not self.settings.is_writable('switch-keys'):
            raise RuntimeError('한/영 전환 설정을 쓸 수 없습니다.')
        if snapshot['user'] is None:
            self.settings.reset('switch-keys')
        elif not self.settings.set_string('switch-keys', snapshot['user']):
            raise RuntimeError('한/영 전환키 설정에 실패했습니다.')
        self.Gio.Settings.sync()
        if self.ime() != snapshot:
            raise RuntimeError('입력기 설정 확인에 실패했습니다.')

    def vnc(self):
        raw = run('/usr/bin/x11vnc', '-Q', 'pid,remap,skip_lockkeys')
        values = dict(re.findall(r'(?:ans|aro)=([a-z_]+):(.*?)(?=,(?:ans|aro)=|$)', raw))
        if not {'pid', 'remap', 'skip_lockkeys'} <= values.keys():
            raise RuntimeError('x11vnc 원격 제어 상태를 읽지 못했습니다.')
        if values['skip_lockkeys'] not in ('0', '1'):
            raise RuntimeError('x11vnc 잠금 키 처리 값을 확인하지 못했습니다.')
        return {'identity': server_identity(values['pid']), 'remap': values['remap'],
                'skip_lockkeys': values['skip_lockkeys']}

    def set_vnc(self, target):
        # skip_lockkeys is evaluated before remap in x11vnc, so it must be off.
        run('/usr/bin/x11vnc', '-sync', '-R', 'remap:' + target['remap'])
        run('/usr/bin/x11vnc', '-sync', '-R', 'skip_lockkeys' if target['skip_lockkeys'] == '1' else 'noskip_lockkeys')
        if self.vnc() != target:
            raise RuntimeError('VNC 키 매핑 확인에 실패했습니다.')

    def clear_caps(self):
        if caps_lock(clear=True):
            raise RuntimeError('Caps Lock이 아직 켜져 있습니다.')


TARGET_IME = {'value': SWITCH_KEYS, 'user': SWITCH_KEYS}


def assert_compatible(actual, original, target, label):
    if actual != original and actual != target:
        raise RuntimeError(label + ' 설정이 외부에서 변경되었습니다. 다른 설정을 덮어쓰지 않고 중단했습니다.')


def enable_mode(backend):
    previous = load_state()
    ime, server = backend.ime(), backend.vnc()
    if not previous or not previous.get('enabled'):
        # Save the complete owned settings before the first mutation.
        state = {'version': 1, 'enabled': True, 'phase': 'applying', 'original_ime': ime,
                 'original_vnc': server, 'created_at': datetime.now(timezone.utc).isoformat()}
        atomic_json(STATE_DIR / ('backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '.json'), state)
    else:
        state = dict(previous)
        assert_compatible(ime, state['original_ime'], TARGET_IME, '입력기')
        if server['identity'] != state['original_vnc']['identity']:
            # A new server has its own baseline; do not restore another process's options.
            state['original_vnc'] = server
        else:
            target = {**state['original_vnc'], 'remap': remap_for_vnc(state['original_vnc']['remap']), 'skip_lockkeys': '0'}
            # A process can be interrupted between the two remote commands.
            for key in ('remap', 'skip_lockkeys'):
                assert_compatible(server[key], state['original_vnc'][key], target[key], 'VNC ' + key)
    target = {**state['original_vnc'], 'remap': remap_for_vnc(state['original_vnc']['remap']), 'skip_lockkeys': '0'}
    state.update(phase='applying', target_vnc=target)
    atomic_json(STATE_FILE, state)
    try:
        backend.set_vnc(target)
        backend.set_ime(TARGET_IME)
        backend.clear_caps()
    except Exception as exc:
        errors = []
        for restore in (lambda: backend.set_ime(ime), lambda: backend.set_vnc(server)):
            try:
                restore()
            except Exception as failure:
                errors.append(str(failure))
        if not errors:
            atomic_json(STATE_FILE, previous or {**state, 'enabled': False, 'phase': 'off'})
        else:
            state.update(phase='recovery-needed', error=' / '.join(errors))
            atomic_json(STATE_FILE, state)
        raise RuntimeError(str(exc) + (' · 복구 확인 필요: ' + ' / '.join(errors) if errors else ' · 적용 전 설정으로 복구했습니다.'))
    state.update(phase='on', error=None)
    atomic_json(STATE_FILE, state)
    return {'mode': 'vnc', 'caps_lock': False, 'switch_keys': SWITCH_KEYS}


def disable_mode(backend):
    state = load_state()
    if not state or not state.get('enabled'):
        return {'mode': 'local', 'changed': False}
    ime = backend.ime()
    assert_compatible(ime, state['original_ime'], TARGET_IME, '입력기')
    try:
        server = backend.vnc()
    except (RuntimeError, OSError, subprocess.SubprocessError):
        # Local keyboard recovery must remain possible after the VNC server stops.
        _, pid, _ = state['original_vnc']['identity'].split(':')
        try:
            still_alive = server_identity(pid) == state['original_vnc']['identity']
        except (FileNotFoundError, ProcessLookupError):
            still_alive = False
        if still_alive:
            raise RuntimeError('VNC 서버는 실행 중이지만 접근할 수 없습니다. 같은 DISPLAY에서 다시 시도하세요.')
        server = None
    same_server = server and server['identity'] == state['original_vnc']['identity']
    if same_server:
        for key in ('remap', 'skip_lockkeys'):
            assert_compatible(server[key], state['original_vnc'][key], state['target_vnc'][key], 'VNC ' + key)
    if same_server:
        backend.set_vnc(state['original_vnc'])
    backend.set_ime(state['original_ime'])
    backend.clear_caps()
    state.update(enabled=False, phase='off', error=None)
    atomic_json(STATE_FILE, state)
    return {'mode': 'local', 'changed': True, 'switch_keys': state['original_ime']['value']}


def status(backend):
    state = load_state()
    server = backend.vnc()
    ime = backend.ime()
    requested = bool(state and state.get('enabled'))
    effective = requested and server == state.get('target_vnc') and ime == TARGET_IME
    return {'mode': 'vnc' if effective else ('needs-apply' if requested else 'local'),
            'enabled': requested, 'caps_lock': caps_lock(), 'switch_keys': ime['value'],
            'vnc_remap': server['remap'], 'skip_lockkeys': server['skip_lockkeys'],
            'backup_directory': str(STATE_DIR)}


def manage_service(enable):
    unit = Path.home() / '.config/systemd/user' / UNIT
    if unit.exists():
        run('systemctl', '--user', 'enable' if enable else 'disable', '--now', UNIT, timeout=15)


def watch():
    """Reapply only after a new x11vnc process; never continually overwrite key settings."""
    last_identity = None
    last_error = None
    while True:
        state = load_state()
        if not state or not state.get('enabled'):
            return
        try:
            # Checking the known process is enough while it is alive. Do not
            # poll the single X11VNC_REMOTE property on the user's display.
            if last_identity:
                try:
                    _, pid, _ = last_identity.split(':')
                    if server_identity(pid) == last_identity:
                        time.sleep(5)
                        continue
                except (FileNotFoundError, ProcessLookupError):
                    pass
            backend = Backend()
            server = backend.vnc()
            if last_identity != server['identity']:
                with operation_lock():
                    # off may have completed while this watcher was querying the server.
                    if not (load_state() or {}).get('enabled'):
                        return
                    enable_mode(backend)
                last_identity = server['identity']
            last_error = None
        except Exception as exc:
            error = str(exc)
            if error != last_error:
                print(error, file=sys.stderr, flush=True)
                last_error = error
        time.sleep(5)


def gui():
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gio, Gtk

    class Chooser(Gtk.Application):
        def __init__(self):
            super().__init__(application_id='local.vnc.KeyboardMode', flags=Gio.ApplicationFlags.FLAGS_NONE)
            self.window = None

        def do_activate(self):
            if self.window:
                self.window.present()
                return
            self.window = Gtk.ApplicationWindow(application=self, title='VNC 키보드 모드')
            self.window.set_default_size(540, 480)
            self.window.set_position(Gtk.WindowPosition.CENTER)
            self.window.set_icon_name('input-keyboard')
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=22)
            self.window.add(box)
            title = Gtk.Label(xalign=0)
            title.set_markup('<span size="x-large" weight="bold">Mac · iPad 한/영 전환</span>')
            box.pack_start(title, False, False, 0)
            self.label = Gtk.Label(xalign=0)
            self.label.set_line_wrap(True)
            box.pack_start(self.label, False, False, 0)
            note = Gtk.Label(label='VNC 모드: Caps Lock으로 한/영 전환\n대문자는 Shift와 함께 입력 · 보조키: Shift + Space\nCmd·Alt 단독 한/영 전환은 잠시 해제합니다.\n직접 사용: 저장해 둔 기존 키 설정으로 복구합니다.', xalign=0)
            box.pack_start(note, False, False, 0)
            actions = Gtk.Box(spacing=12)
            for label, command in [('VNC 모드 켜기', 'on'), ('직접 사용 · 원래 설정', 'off')]:
                button = Gtk.Button(label=label)
                button.connect('clicked', self.change, command)
                actions.pack_start(button, True, True, 0)
            box.pack_start(actions, False, False, 0)
            entry = Gtk.Entry()
            entry.set_placeholder_text('여기서 Caps Lock → abc / 가나다 전환 확인')
            entry.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
            box.pack_start(entry, False, False, 0)
            hint = Gtk.Label(label='Mac/iPad 입력 언어는 ABC/영문으로 두세요.\nCaps Lock이 기기 언어까지 바꾸면 Shift + Space를 사용하세요.\n테스트 문장은 파일이나 로그에 저장하지 않습니다.\n이 모드의 입력기 설정은 같은 Ubuntu 사용자에게 적용됩니다.', xalign=0)
            hint.set_line_wrap(True)
            box.pack_start(hint, False, False, 0)
            close = Gtk.Button(label='닫기')
            close.connect('clicked', lambda _: self.window.close())
            box.pack_end(close, False, False, 0)
            self.refresh()
            self.window.show_all()

        def refresh(self):
            try:
                info = status(Backend())
                name = {'vnc': 'VNC 모드 켜짐', 'local': '직접 사용 · 기존 설정', 'needs-apply': 'VNC 모드 재적용 필요'}[info['mode']]
                self.label.set_text(name + '  /  Caps Lock 잠금: ' + ('켜짐' if info['caps_lock'] else '꺼짐'))
            except Exception as exc:
                self.label.set_text(str(exc))

        def change(self, _, command):
            try:
                with operation_lock():
                    (enable_mode if command == 'on' else disable_mode)(Backend())
                manage_service(command == 'on')
                self.refresh()
            except Exception as exc:
                self.label.set_text(str(exc))

    return Chooser().run([sys.argv[0]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('gui', 'status', 'on', 'off', 'watch'), nargs='?', default='gui')
    args = parser.parse_args()
    try:
        if args.command == 'gui':
            return gui()
        if args.command == 'watch':
            watch()
            return 0
        if args.command == 'status':
            result = status(Backend())
        else:
            with operation_lock():
                result = (enable_mode if args.command == 'on' else disable_mode)(Backend())
            manage_service(args.command == 'on')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
