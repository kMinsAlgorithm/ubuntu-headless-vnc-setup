#!/usr/bin/python3
"""Opt-in clipboard protection test on disposable Xvfb/loopback VNC only.

Uses fixed text; never reads the real desktop or its clipboard. x11vnc waits
45 seconds to create its selection window on an X server without a WM.
"""
import os
from pathlib import Path
import selectors
import socket
import struct
import subprocess
import tempfile
import time
import json
from probe_vnc_keyboard import connect, ProbeBackend, k


def main():
    sample = '가나다 abc123'
    # Model a client sending back text that has already been misdecoded.
    returned = sample.encode('utf8').decode('latin1')
    processes = []
    sock = None
    with tempfile.TemporaryDirectory(prefix='vnc-clipboard-probe-') as tmp:
        folder = Path(tmp)
        with (folder / 'server.log').open('w') as log:
            try:
                x = subprocess.Popen(['Xvfb', '-displayfd', '1', '-screen', '0', '640x480x24',
                                      '-nolisten', 'tcp'], stdout=subprocess.PIPE, stderr=log, text=True)
                processes.append(x)
                with selectors.DefaultSelector() as selector:
                    selector.register(x.stdout, selectors.EVENT_READ)
                    assert selector.select(5), 'Xvfb did not start'
                    number = x.stdout.readline().strip()
                assert number.isdigit()
                os.environ.update(DISPLAY=':' + number, NO_AT_BRIDGE='1',
                                  GTK_IM_MODULE='gtk-im-context-simple', GIO_USE_VFS='local')
                for name in ('XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS'):
                    os.environ.pop(name, None)
                k.STATE_DIR, k.STATE_FILE = folder / 'state', folder / 'state/state.json'
                import gi
                gi.require_version('Gtk', '3.0')
                gi.require_version('Gdk', '3.0')
                from gi.repository import Gtk, Gdk, GLib

                def pump(seconds=.6):
                    deadline = time.monotonic() + seconds
                    while time.monotonic() < deadline:
                        while GLib.MainContext.default().pending():
                            GLib.MainContext.default().iteration(False)
                        time.sleep(.01)

                with socket.socket() as temporary:
                    temporary.bind(('127.0.0.1', 0))
                    port = temporary.getsockname()[1]
                server = subprocess.Popen(['x11vnc', '-display', os.environ['DISPLAY'],
                    '-listen', '127.0.0.1', '-rfbport', str(port), '-no6', '-nopw', '-forever',
                    '-shared', '-noxdamage', '-noshm', '-input', 'KMBCF'], stdout=log, stderr=log)
                processes.append(server)
                deadline = time.monotonic() + 8
                while True:
                    try:
                        sock = connect(port)
                        break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(.1)
                sock.sendall(struct.pack('!BBHHHH', 3, 0, 0, 0, 1, 1))
                deadline = time.monotonic() + 55
                while 'created selwin:' not in (folder / 'server.log').read_text():
                    assert time.monotonic() < deadline, 'Selection window did not initialize'
                    pump(.2)

                clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
                primary = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)

                def copy_sample():
                    for selection in (clipboard, primary):
                        selection.set_text(sample, -1)
                    pump()

                def receive(text):
                    encoded = text.encode('utf8')
                    sock.sendall(struct.pack('!B3xI', 6, len(encoded)) + encoded)
                    pump()

                backend = ProbeBackend()
                original = backend.vnc()
                copy_sample()
                receive(returned)
                assert clipboard.wait_for_text() == returned, 'Baseline corruption was not reproduced'
                k.enable_mode(backend, protect_clipboard=True)
                copy_sample()
                receive(returned)
                assert clipboard.wait_for_text() == sample
                assert primary.wait_for_text() == sample
                k.enable_mode(backend, protect_clipboard=False)
                receive('remote abc123')
                assert clipboard.wait_for_text() == 'remote abc123'
                assert primary.wait_for_text() == 'remote abc123'
                k.disable_mode(backend)
                assert backend.vnc() == original
                print(json.dumps({'baseline_overwrite_reproduced': True,
                    'protected_clipboard': True, 'protected_primary': True,
                    'receive_restored': True, 'original_settings_restored': True}))
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


if __name__ == '__main__':
    main()
