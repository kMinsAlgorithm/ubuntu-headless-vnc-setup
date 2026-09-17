#!/usr/bin/python3
"""Reversible x11vnc Korean keyboard profile, with a small desktop chooser."""
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
CLIPBOARD_KEYS = ('setclipboard', 'setprimary')
# Single keystrokes on a Korean two-beolsik keyboard. Do not map compound
# jamo or committed syllables: those cannot be represented by one key event.
JAMO_KEYS = {
    'ㄱ': 'r', 'ㄲ': 'R', 'ㄴ': 's', 'ㄷ': 'e', 'ㄸ': 'E', 'ㄹ': 'f',
    'ㅁ': 'a', 'ㅂ': 'q', 'ㅃ': 'Q', 'ㅅ': 't', 'ㅆ': 'T', 'ㅇ': 'd',
    'ㅈ': 'w', 'ㅉ': 'W', 'ㅊ': 'c', 'ㅋ': 'z', 'ㅌ': 'x', 'ㅍ': 'v', 'ㅎ': 'g',
    'ㅏ': 'k', 'ㅐ': 'o', 'ㅑ': 'i', 'ㅒ': 'O', 'ㅓ': 'j', 'ㅔ': 'p',
    'ㅕ': 'u', 'ㅖ': 'P', 'ㅗ': 'h', 'ㅛ': 'y', 'ㅜ': 'n', 'ㅠ': 'b',
    'ㅡ': 'm', 'ㅣ': 'l',
}


def managed_remaps():
    # Both Command keys in the user's macOS Screen Sharing client send Alt_L.
    # Control remains Control; Option sends a different keysym and is untouched.
    pairs = [('Caps_Lock', 'Hangul'), ('Alt_L', 'Control_L')]
    for jamo, latin in JAMO_KEYS.items():
        # X11 keysymdef.h: legacy Hangul block is contiguous U+3131..U+3163.
        # iPad RVNC software keyboard also sends bare Unicode code points
        # as keysyms (observed 0x3141/0x3160/0x314a). Limit this alias to
        # the same single two-beolsik jamo; do not reinterpret other keys.
        pairs.extend([(f'U{ord(jamo):04X}', latin),
                      (f'0x{0xEA1 + ord(jamo) - 0x3131:x}', latin),
                      (f'0x{ord(jamo):x}', latin)])
    return pairs



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
    mappings = managed_remaps()
    lib = ctypes.CDLL(ctypes.util.find_library('X11') or 'libX11.so.6')
    lib.XStringToKeysym.argtypes = [ctypes.c_char_p]
    lib.XStringToKeysym.restype = ctypes.c_ulong

    def number(name):
        return int(name, 16) if name.lower().startswith('0x') else lib.XStringToKeysym(name.encode('ascii'))

    owned = {number(source) for source, _ in mappings}
    pairs = [pair for pair in pairs if number(pair.split('-', 1)[0]) not in owned]
    return ','.join([*pairs, *(f'{source}-{target}' for source, target in mappings)])


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


def x_cardinal(name, value=None):
    """Read/write our small X11 control properties, never keyboard events."""
    lib = ctypes.CDLL(ctypes.util.find_library('X11') or 'libX11.so.6')
    ptr, ulong = ctypes.c_void_p, ctypes.c_ulong
    lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib.XOpenDisplay.restype = ptr
    lib.XDefaultRootWindow.argtypes = [ptr]
    lib.XDefaultRootWindow.restype = ulong
    lib.XInternAtom.argtypes = [ptr, ctypes.c_char_p, ctypes.c_int]
    lib.XInternAtom.restype = ulong
    lib.XGetWindowProperty.argtypes = [ptr, ulong, ulong, ctypes.c_long, ctypes.c_long,
        ctypes.c_int, ulong, ctypes.POINTER(ulong), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ulong), ctypes.POINTER(ulong), ctypes.POINTER(ptr)]
    lib.XChangeProperty.argtypes = [ptr, ulong, ulong, ulong, ctypes.c_int, ctypes.c_int, ptr, ctypes.c_int]
    lib.XSync.argtypes = [ptr, ctypes.c_int]
    lib.XFree.argtypes = [ptr]
    lib.XCloseDisplay.argtypes = [ptr]
    display = lib.XOpenDisplay(None)
    if not display:
        raise RuntimeError('X11 키보드 보정 상태에 접근하지 못했습니다.')
    data = ptr()
    try:
        root = lib.XDefaultRootWindow(display)
        atom = lib.XInternAtom(display, name.encode(), False)
        if value is not None:
            payload = (ulong * len(value))(*value)
            lib.XChangeProperty(display, root, atom, 6, 32, 0, payload, len(value))
            lib.XSync(display, False)
        kind, count, after, form = ulong(), ulong(), ulong(), ctypes.c_int()
        result = lib.XGetWindowProperty(display, root, atom, 0, 4, False, 6,
            ctypes.byref(kind), ctypes.byref(form), ctypes.byref(count), ctypes.byref(after), ctypes.byref(data))
        if result or kind.value != 6 or form.value != 32 or after.value or not data.value:
            return []
        return list(ctypes.cast(data, ctypes.POINTER(ulong))[:count.value])
    finally:
        if data.value:
            lib.XFree(data)
        lib.XCloseDisplay(display)


def target_server(original, protect_clipboard=False):
    target = {**original, 'remap': remap_for_vnc(original['remap']), 'skip_lockkeys': '0'}
    if 'caps_bridge' in original:
        target['caps_bridge'] = '1'
    if protect_clipboard:
        if not all(key in original for key in CLIPBOARD_KEYS):
            raise RuntimeError('클립보드 수신 설정을 확인하지 못했습니다.')
        target.update({key: '0' for key in CLIPBOARD_KEYS})
    return target


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
        raw = run('/usr/bin/x11vnc', '-Q', 'pid,remap,skip_lockkeys,setclipboard,setprimary')
        values = dict(re.findall(r'(?:ans|aro)=([a-z_]+):(.*?)(?=,(?:ans|aro)=|$)', raw))
        if not {'pid', 'remap', 'skip_lockkeys', *CLIPBOARD_KEYS} <= values.keys():
            raise RuntimeError('x11vnc 원격 제어 상태를 읽지 못했습니다.')
        if any(values[key] not in ('0', '1') for key in ('skip_lockkeys', *CLIPBOARD_KEYS)):
            raise RuntimeError('x11vnc 키·클립보드 설정 값을 확인하지 못했습니다.')
        result = {'identity': server_identity(values['pid']), 'remap': values['remap'],
                  'skip_lockkeys': values['skip_lockkeys'],
                  **{key: values[key] for key in CLIPBOARD_KEYS}}
        if x_cardinal('_VNC_KEYBOARD_CAPS_BRIDGE') == [int(values['pid']), 1]:
            result['caps_bridge'] = '1' if any(x_cardinal('_VNC_KEYBOARD_CAPS_MODE')) else '0'
        return result

    def set_vnc(self, target):
        current = self.vnc()
        if current['identity'] != target['identity']:
            raise RuntimeError('VNC 서버가 변경되었습니다. 다시 상태를 확인하세요.')
        if 'caps_bridge' in target:
            pid = int(target['identity'].split(':')[1])
            if x_cardinal('_VNC_KEYBOARD_CAPS_BRIDGE') != [pid, 1]:
                raise RuntimeError('iPad 보정 모듈의 서버가 변경되었습니다. 다시 상태를 확인하세요.')
            if target['caps_bridge'] == '0' and current.get('caps_bridge') != '0':
                x_cardinal('_VNC_KEYBOARD_CAPS_MODE', [0])
        # skip_lockkeys is evaluated before remap in x11vnc, so it must be off.
        if current['remap'] != target['remap']:
            run('/usr/bin/x11vnc', '-sync', '-R', 'remap:' + target['remap'])
        if current['skip_lockkeys'] != target['skip_lockkeys']:
            run('/usr/bin/x11vnc', '-sync', '-R', 'skip_lockkeys' if target['skip_lockkeys'] == '1' else 'noskip_lockkeys')
        for key in CLIPBOARD_KEYS:
            if key in target and current.get(key) != target[key]:
                run('/usr/bin/x11vnc', '-sync', '-R', key if target[key] == '1' else 'no' + key)
        if target.get('caps_bridge') == '1' and current.get('caps_bridge') != '1':
            x_cardinal('_VNC_KEYBOARD_CAPS_MODE', [(time.monotonic_ns() & 0x7fffffff) | 1])
        if self.vnc() != target:
            raise RuntimeError('VNC 키 매핑 확인에 실패했습니다.')

    def clear_caps(self):
        if caps_lock(clear=True):
            raise RuntimeError('Caps Lock이 아직 켜져 있습니다.')


TARGET_IME = {'value': SWITCH_KEYS, 'user': SWITCH_KEYS}


def assert_compatible(actual, original, target, label):
    if actual != original and actual != target:
        raise RuntimeError(label + ' 설정이 외부에서 변경되었습니다. 다른 설정을 덮어쓰지 않고 중단했습니다.')


def enable_mode(backend, protect_clipboard=None):
    previous = load_state()
    if protect_clipboard is None:
        protect_clipboard = bool(previous and previous.get('protect_clipboard'))
    ime, server = backend.ime(), backend.vnc()
    if not previous or not previous.get('enabled'):
        # Save the complete owned settings before the first mutation.
        state = {'version': 1, 'enabled': True, 'phase': 'applying', 'original_ime': ime,
                 'original_vnc': server, 'created_at': datetime.now(timezone.utc).isoformat()}
        atomic_json(STATE_DIR / ('backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '.json'), state)
    else:
        state = dict(previous)
        state['original_vnc'] = dict(previous['original_vnc'])
        assert_compatible(ime, state['original_ime'], TARGET_IME, '입력기')
        if server['identity'] != state['original_vnc']['identity']:
            # A new server has its own baseline; do not restore another process's options.
            state['original_vnc'] = server
        else:
            # Capture newly owned fields without replacing the key backup.
            for key in CLIPBOARD_KEYS:
                if key in server and key not in state['original_vnc']:
                    state['original_vnc'][key] = server[key]
            target = target_server(state['original_vnc'], protect_clipboard)
            # A process can be interrupted between the two remote commands.
            for key in state['original_vnc'].keys() - {'identity'}:
                # Accept the last target we actually saved when upgrading an
                # enabled older profile, but never arbitrary external edits.
                saved_target = state.get('target_vnc', {})
                if (saved_target.get('identity') == server['identity']
                        and server[key] == saved_target.get(key)):
                    continue
                assert_compatible(server[key], state['original_vnc'][key], target[key], 'VNC ' + key)
    target = target_server(state['original_vnc'], protect_clipboard)
    state.update(phase='applying', target_vnc=target, protect_clipboard=protect_clipboard)
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
    return {'mode': 'vnc', 'caps_lock': False, 'switch_keys': SWITCH_KEYS,
            'clipboard_protection': protect_clipboard}


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
        for key in state['original_vnc'].keys() - {'identity'}:
            assert_compatible(server[key], state['original_vnc'][key], state['target_vnc'][key], 'VNC ' + key)
    if same_server:
        # Older profiles do not own the new clipboard fields until upgraded.
        restore = {**{key: server[key] for key in CLIPBOARD_KEYS if key in server},
                   **state['original_vnc']}
        backend.set_vnc(restore)
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
    saved_target = (state or {}).get('target_vnc', {})
    comparison = {**{key: server[key] for key in CLIPBOARD_KEYS if key in server}, **saved_target}
    effective = requested and server == comparison and ime == TARGET_IME
    return {'mode': 'vnc' if effective else ('needs-apply' if requested else 'local'),
            'enabled': requested, 'caps_lock': caps_lock(), 'switch_keys': ime['value'],
            'vnc_remap': server['remap'], 'skip_lockkeys': server['skip_lockkeys'],
            'caps_bridge': server.get('caps_bridge', 'not-installed'),
            'clipboard_protection_requested': bool(state and state.get('protect_clipboard')),
            'clipboard_protection': bool(effective and state.get('protect_clipboard')
                                         and all(server.get(key) == '0' for key in CLIPBOARD_KEYS)),
            'clipboard_receive': {key: server.get(key) for key in CLIPBOARD_KEYS},
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
            note = Gtk.Label(label='VNC 모드: Caps Lock으로 한/영 전환\n대문자는 Shift와 함께 입력 · 보조키: Shift + Space\nMac Cmd+C/V: 복사·붙여넣기 · 기존 Ctrl도 사용 가능\n직접 사용: 저장해 둔 기존 키 설정으로 복구합니다.', xalign=0)
            box.pack_start(note, False, False, 0)
            actions = Gtk.Box(spacing=12)
            for label, command in [('VNC 모드 켜기', 'on'), ('직접 사용 · 원래 설정', 'off')]:
                button = Gtk.Button(label=label)
                button.connect('clicked', self.change, command)
                actions.pack_start(button, True, True, 0)
            box.pack_start(actions, False, False, 0)
            self.protection = Gtk.CheckButton(label='iPad 복사 보호')
            self.protection.connect('toggled', self.change_clipboard)
            box.pack_start(self.protection, False, False, 0)
            clipboard_note = Gtk.Label(label='Ubuntu 안에서 복사한 원문을 보호합니다.\n켜져 있는 동안 기기 → Ubuntu 붙여넣기는 제한됩니다.\n같은 화면에 연결한 Mac과 iPad 모두에 적용됩니다.', xalign=0)
            box.pack_start(clipboard_note, False, False, 0)
            entry = Gtk.Entry()
            entry.set_placeholder_text('여기서 Caps Lock → abc / 가나다 전환 확인')
            entry.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
            box.pack_start(entry, False, False, 0)
            hint = Gtk.Label(label='Mac·iPad: 두벌식 낱자 입력을 조합하도록 보정합니다.\n한/영이 반대로 나오면 Shift + Space로 한 번 맞추세요.\nUbuntu 터미널의 복사·붙여넣기는 Cmd+Shift+C/V입니다.\n테스트 문장은 저장하지 않습니다. 설정은 Ubuntu 사용자 공통입니다.', xalign=0)
            hint.set_line_wrap(True)
            box.pack_start(hint, False, False, 0)
            close = Gtk.Button(label='닫기')
            close.connect('clicked', lambda _: self.window.close())
            box.pack_end(close, False, False, 0)
            self.refresh()
            self.window.show_all()

        def change_clipboard(self, button):
            if getattr(self, 'refreshing', False):
                return
            try:
                with operation_lock():
                    enable_mode(Backend(), protect_clipboard=button.get_active())
                self.refresh()
            except Exception as exc:
                self.refresh()
                self.label.set_text(str(exc))

        def refresh(self):
            try:
                info = status(Backend())
                name = {'vnc': 'VNC 모드 켜짐', 'local': '직접 사용 · 기존 설정', 'needs-apply': 'VNC 모드 재적용 필요'}[info['mode']]
                self.label.set_text(name + '  /  Caps Lock 잠금: ' + ('켜짐' if info['caps_lock'] else '꺼짐')
                    + '\niPad 보정: ' + {'1': '켜짐', '0': '꺼짐', 'not-installed': '추가 설치 필요'}[info['caps_bridge']])
                self.refreshing = True
                self.protection.set_active(info['clipboard_protection_requested'])
                self.protection.set_sensitive(info['enabled'])
                self.refreshing = False
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
    parser.add_argument('command', choices=('gui', 'status', 'on', 'off', 'watch', 'clipboard-on', 'clipboard-off'), nargs='?', default='gui')
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
                if args.command.startswith('clipboard-'):
                    if not (load_state() or {}).get('enabled'):
                        raise RuntimeError('먼저 VNC 모드를 켜 주세요.')
                    result = enable_mode(Backend(), protect_clipboard=args.command == 'clipboard-on')
                else:
                    result = (enable_mode if args.command == 'on' else disable_mode)(Backend())
            manage_service(args.command != 'off')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
