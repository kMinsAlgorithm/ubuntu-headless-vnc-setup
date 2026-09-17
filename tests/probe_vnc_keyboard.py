#!/usr/bin/python3
"""Opt-in integration check using a disposable Xvfb and loopback-only x11vnc.

Never connects to the user's desktop, VNC password, or existing VNC port.
The input engine is stubbed; real CapsLock/Hangul RFB/X11 events are checked.
"""
import importlib.util
import json
import os
from pathlib import Path
import selectors
import socket
import struct
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('keyboard_probe', ROOT / 'keyboard-mode/keyboard_mode.py')
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)


def recv_exact(sock, count):
    result = b''
    while len(result) < count:
        part = sock.recv(count - len(result))
        if not part:
            raise RuntimeError('Test VNC connection closed')
        result += part
    return result


def connect(port):
    sock = socket.create_connection(('127.0.0.1', port), timeout=3)
    assert recv_exact(sock, 12).startswith(b'RFB 003.')
    sock.sendall(b'RFB 003.008\n')
    count = recv_exact(sock, 1)[0]
    assert 1 in recv_exact(sock, count), 'Expected None auth on isolated test server only'
    sock.sendall(b'\x01')
    assert recv_exact(sock, 4) == b'\0' * 4
    sock.sendall(b'\x01')
    header = recv_exact(sock, 24)
    recv_exact(sock, struct.unpack('!I', header[20:24])[0])
    return sock


def key(sock, keysym, down):
    sock.sendall(struct.pack('!BBHI', 4, int(down), 0, keysym))


def tap(sock, keysym):
    key(sock, keysym, True)
    time.sleep(.08)
    key(sock, keysym, False)
    time.sleep(.12)


class ProbeBackend(k.Backend):
    def __init__(self):
        self.current_ime = {'value': 'Hangul,Super_R,Alt_L', 'user': 'Hangul,Super_R,Alt_L'}

    def ime(self):
        return dict(self.current_ime)

    def set_ime(self, value):
        self.current_ime = dict(value)


def main():
    processes = []
    with tempfile.TemporaryDirectory(prefix='vnc-keyboard-probe-') as tmp:
        folder = Path(tmp)
        server_log = (folder / 'server.log').open('w+')
        event_log = (folder / 'events.log').open('w+')
        sock = None
        try:
            xvfb = subprocess.Popen(['Xvfb', '-displayfd', '1', '-screen', '0', '640x480x24', '-nolisten', 'tcp'],
                                    stdout=subprocess.PIPE, stderr=server_log, text=True)
            processes.append(xvfb)
            with selectors.DefaultSelector() as selector:
                selector.register(xvfb.stdout, selectors.EVENT_READ)
                assert selector.select(5), 'Xvfb did not start'
                number = xvfb.stdout.readline().strip()
            assert number.isdigit()
            os.environ['DISPLAY'] = ':' + number
            os.environ.pop('XAUTHORITY', None)
            # Never use a live IBus session in this probe.
            os.environ.pop('DBUS_SESSION_BUS_ADDRESS', None)
            k.STATE_DIR, k.STATE_FILE = folder / 'state', folder / 'state/state.json'
            with socket.socket() as temporary:
                temporary.bind(('127.0.0.1', 0))
                port = temporary.getsockname()[1]
            server = subprocess.Popen(['x11vnc', '-display', os.environ['DISPLAY'], '-listen', '127.0.0.1',
                                       '-rfbport', str(port), '-no6', '-nopw', '-forever', '-shared', '-xkb',
                                       '-noxdamage', '-noshm', '-repeat', '-quiet'], stdout=server_log, stderr=server_log)
            processes.append(server)
            deadline = time.monotonic() + 8
            while True:
                try:
                    sock = connect(port)
                    break
                except (ConnectionRefusedError, OSError):
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(.1)
            xev = subprocess.Popen(['stdbuf', '-oL', 'xev', '-event', 'keyboard', '-name', 'VNCKeyboardProbe'], stdout=event_log, stderr=server_log)
            processes.append(xev)
            window = k.run('xdotool', 'search', '--sync', '--name', '^VNCKeyboardProbe$', timeout=5).splitlines()[0]
            k.run('xdotool', 'windowfocus', '--sync', window)
            tap(sock, 0xffe5)
            assert k.caps_lock(), 'Baseline Caps Lock did not activate'
            backend = ProbeBackend()
            original = backend.vnc()
            k.enable_mode(backend)
            assert not k.caps_lock()
            start = event_log.tell()
            for _ in range(5):
                tap(sock, 0xffe5)
            assert not k.caps_lock(), 'VNC Caps Lock still enabled uppercase lock'
            tap(sock, ord('a'))
            key(sock, 0xffe1, True)
            tap(sock, ord('A'))
            key(sock, 0xffe1, False)
            tap(sock, 0xffe9)  # Screen Sharing Command becomes Control.
            tap(sock, 0xffeb)  # Super_L remains a modifier, not Hangul.
            time.sleep(.2)
            event_log.flush()
            events = (folder / 'events.log').read_text()
            assert events.count('keysym 0xff31, Hangul') >= 10, events[-2000:]
            assert 'keysym 0x61, a' in events
            assert 'keysym 0x41, A' in events
            assert 'keysym 0xffeb, Super_L' in events
            assert 'keysym 0xffe3, Control_L' in events
            assert 'keysym 0xffe9, Alt_L' not in events
            k.disable_mode(backend)
            assert backend.vnc() == original
            tap(sock, 0xffe9)
            time.sleep(.2)
            assert 'keysym 0xffe9, Alt_L' in (folder / 'events.log').read_text()
            tap(sock, 0xffe5)
            assert k.caps_lock(), 'Original Caps Lock function was not restored'
            print(json.dumps({'isolated_rfb_caps_to_hangul_pairs': 5, 'vnc_caps_lock': False,
                              'lowercase_a': True, 'shift_uppercase_A': True, 'super_preserved': True,
                              'command_to_control': True, 'original_command_restored': True,
                              'original_caps_function_restored': True, 'actual_ibus_text': 'not tested in this probe'}))
        finally:
            if sock:
                sock.close()
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
            server_log.close()
            event_log.close()


if __name__ == '__main__':
    main()
