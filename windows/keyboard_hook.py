"""Opt-in injected-key remapping. No keyboard text or clipboard content is stored."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

MARKER = 0x564E4354


class KeyboardMapper:
    def __init__(self, command_as_control=False):
        self.mapping = {0x14: 0x15}  # Caps Lock -> VK_HANGUL (Korean IME required).
        if command_as_control:
            self.mapping.update({0x12: 0xA2, 0xA4: 0xA2})  # Left Alt only; preserve AltGr.
        self.held = {}

    def handle(self, vk, flags, extra, send):
        if not flags & 0x10 or extra == MARKER or vk not in self.mapping:
            return False
        up = bool(flags & 0x80)
        if up:
            if vk not in self.held:
                return False
            if send(self.held[vk], True):
                del self.held[vk]
                return True
            return False
        if vk in self.held:
            return True  # Suppress repeats; a held Caps key must not toggle repeatedly.
        target = self.mapping[vk]
        if send(target, False):
            self.held[vk] = target
            return True
        return False  # Preserve the original event when Windows blocks SendInput.

    def release(self, send):
        for target in self.held.values():
            send(target, True)
        self.held.clear()


def keyboard_status(state):
    path = state / 'keyboard-runtime.json'
    try:
        result = json.loads(path.read_text(encoding='utf-8'))
        running = bool(result.get('running')) and time.time() - result['heartbeat'] < 6
        return {**result, 'running': running}
    except (OSError, ValueError, KeyError):
        return {'running': False}


def start_keyboard(state, command_as_control=False):
    from vnc_desktop import write_json, operation_lock, console_python
    if os.name != 'nt':
        raise RuntimeError('The keyboard mode requires Windows')
    with operation_lock(state / 'keyboard-launch.lock'):
        current = keyboard_status(state)
        if current['running']:
            if current.get('command_as_control') != command_as_control:
                raise RuntimeError('Turn keyboard mode off before changing the Command mapping')
            return current
        args = [console_python(), str(Path(__file__).with_name('vnc_desktop.py')), 'keyboard', 'run']
        if command_as_control:
            args.append('--command-as-control')
        child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            current = keyboard_status(state)
            if current['running'] and current.get('pid') == child.pid:
                write_json(state / 'keyboard-preference.json',
                           {'enabled': True, 'command_as_control': command_as_control})
                return current
            if child.poll() is not None:
                raise RuntimeError('Keyboard mode failed to start; use keyboard run in a terminal for diagnostics')
            time.sleep(0.05)
        child.terminate()  # Only the newly launched worker owned by this call.
        child.wait(timeout=5)
        raise RuntimeError('Keyboard mode did not become ready; check the interactive Windows desktop')


def stop_keyboard(state):
    from vnc_desktop import write_json, operation_lock
    with operation_lock(state / 'keyboard-launch.lock'):
        write_json(state / 'keyboard-preference.json', {'enabled': False})
        current = keyboard_status(state)
        if not current['running']:
            return {'running': False}
        write_json(state / 'keyboard-stop.json', {'token': current['token']})
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            current = keyboard_status(state)
            if not current['running']:
                return current
            time.sleep(0.05)
        raise RuntimeError('Keyboard mode did not stop; do not remove its files yet')


def run_keyboard(state, command_as_control=False):
    from vnc_desktop import write_json, operation_lock
    if os.name != 'nt':
        raise RuntimeError('The keyboard mode requires Windows')
    api = C.WinDLL('user32', use_last_error=True)
    kernel = C.WinDLL('kernel32', use_last_error=True)
    pointer = C.c_size_t
    u32 = C.c_uint32

    class KeyEvent(C.Structure):
        _fields_ = [('vk', u32), ('scan', u32), ('flags', u32), ('time', u32), ('extra', pointer)]

    class KeyInput(C.Structure):
        _fields_ = [('vk', C.c_uint16), ('scan', C.c_uint16), ('flags', u32), ('time', u32), ('extra', pointer)]

    class MouseInput(C.Structure):
        _fields_ = [('x', C.c_int32), ('y', C.c_int32), ('data', u32), ('flags', u32), ('time', u32), ('extra', pointer)]

    class InputUnion(C.Union):
        _fields_ = [('keyboard', KeyInput), ('mouse', MouseInput)]

    class Input(C.Structure):
        _fields_ = [('kind', u32), ('value', InputUnion)]

    callback_type = C.WINFUNCTYPE(C.c_ssize_t, C.c_int, pointer, C.c_ssize_t)
    api.SetWindowsHookExW.argtypes = [C.c_int, callback_type, C.c_void_p, u32]
    api.SetWindowsHookExW.restype = C.c_void_p
    api.CallNextHookEx.argtypes = [C.c_void_p, C.c_int, pointer, C.c_ssize_t]
    api.CallNextHookEx.restype = C.c_ssize_t
    api.UnhookWindowsHookEx.argtypes = [C.c_void_p]
    api.SendInput.argtypes = [u32, C.POINTER(Input), C.c_int]
    kernel.GetModuleHandleW.argtypes = [C.c_wchar_p]
    kernel.GetModuleHandleW.restype = C.c_void_p
    mapper = KeyboardMapper(command_as_control)
    from ime_bridge import JamoMapper, ForegroundIme
    jamo = JamoMapper()
    ime = ForegroundIme()

    def send(vk, up):
        value = Input()
        value.kind = 1
        value.value.keyboard = KeyInput(vk, 0, 2 if up else 0, 0, MARKER)
        return api.SendInput(1, C.byref(value), C.sizeof(Input)) == 1

    def tap(vk, shifted):
        temporary_shift = shifted and not bool(ime.api.GetAsyncKeyState(0x10) & 0x8000)
        keys = []
        if temporary_shift:
            keys.append((0xA0, False))
        keys.extend(((vk, False), (vk, True)))
        if temporary_shift:
            keys.append((0xA0, True))
        inputs = (Input * len(keys))()
        for index, (key, up) in enumerate(keys):
            inputs[index].kind = 1
            inputs[index].value.keyboard = KeyInput(key, 0, 2 if up else 0, 0, MARKER)
        count = api.SendInput(len(inputs), inputs, C.sizeof(Input))
        if count != len(inputs) and count:
            send(vk, True)
            if temporary_shift:
                send(0xA0, True)
        return count == len(inputs)

    @callback_type
    def callback(code, message, address):
        if code >= 0:
            event = C.cast(address, C.POINTER(KeyEvent)).contents
            if event.extra != MARKER and event.vk in (0x14, 0x15):
                ime.invalidate()
            if jamo.handle(event.vk, event.scan, event.flags, event.extra,
                           ime.set_native, tap, ime.shortcut_pressed()):
                return 1
            if mapper.handle(event.vk, event.flags, event.extra, send):
                return 1
        return api.CallNextHookEx(None, code, message, address)

    with operation_lock(state / 'keyboard-worker.lock'):
        hook = api.SetWindowsHookExW(13, callback, kernel.GetModuleHandleW(None), 0)
        if not hook:
            raise C.WinError(C.get_last_error())
        token = uuid.uuid4().hex
        runtime = {'running': True, 'pid': os.getpid(), 'token': token,
                   'command_as_control': command_as_control, 'jamo_normalization': True}
        try:
            message = W.MSG()
            next_heartbeat = 0
            while True:
                while api.PeekMessageW(C.byref(message), None, 0, 0, 1):
                    if message.message == 0x12:
                        return 0
                    api.TranslateMessage(C.byref(message))
                    api.DispatchMessageW(C.byref(message))
                if time.monotonic() >= next_heartbeat:
                    write_json(state / 'keyboard-runtime.json', {**runtime, 'heartbeat': time.time()})
                    next_heartbeat = time.monotonic() + 1
                stop = state / 'keyboard-stop.json'
                if stop.exists():
                    try:
                        if json.loads(stop.read_text(encoding='utf-8')).get('token') == token:
                            break
                    except (OSError, ValueError):
                        pass
                time.sleep(0.02)
        finally:
            mapper.release(send)
            api.UnhookWindowsHookEx(hook)
            write_json(state / 'keyboard-runtime.json', {**runtime, 'running': False, 'heartbeat': time.time()})
    return 0
