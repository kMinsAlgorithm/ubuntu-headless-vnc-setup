"""Opt-in RFB → x11vnc remap → real IBus test, isolated from the user session."""

import os, sys, subprocess, time, tempfile, selectors, socket, threading, json
from pathlib import Path
from probe_vnc_keyboard import connect, tap, key, k


def worker():
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("IBus", "1.0")
    from gi.repository import Gtk, GLib, Gio, IBus

    processes = []
    daemon = subprocess.Popen(
        [
            "ibus-daemon",
            "--replace",
            "--xim",
            "--panel",
            "disable",
            "--emoji-extension",
            "disable",
            "--address",
            os.environ["IBUS_ADDRESS"],
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    processes.append(daemon)
    try:
        IBus.init()
        bus = IBus.Bus.new()
        deadline = time.monotonic() + 8
        while not bus.is_connected():
            if time.monotonic() > deadline:
                raise RuntimeError("IBus unavailable")
            while GLib.MainContext.default().pending():
                GLib.MainContext.default().iteration(False)
            time.sleep(0.1)
            bus = IBus.Bus.new()
        settings = Gio.Settings.new("org.freedesktop.ibus.engine.hangul")
        settings.set_string("switch-keys", "Hangul,Shift+space,Control+space")
        Gio.Settings.sync()
        assert bus.set_global_engine("hangul")
        with socket.socket() as temp:
            temp.bind(("127.0.0.1", 0))
            port = temp.getsockname()[1]
        server = subprocess.Popen(
            [
                "x11vnc",
                "-display",
                os.environ["DISPLAY"],
                "-listen",
                "127.0.0.1",
                "-rfbport",
                str(port),
                "-no6",
                "-nopw",
                "-forever",
                "-shared",
                "-xkb",
                "-noxdamage",
                "-noshm",
                "-quiet",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={
                **os.environ,
                **(
                    {"LD_PRELOAD": os.environ["VNC_TEST_CAPS_BRIDGE"]}
                    if "VNC_TEST_CAPS_BRIDGE" in os.environ
                    else {}
                ),
            },
        )
        processes.append(server)
        deadline = time.monotonic() + 8
        while True:
            try:
                sock = connect(port)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)
        if "VNC_TEST_CAPS_BRIDGE" in os.environ:
            bridge_pid = subprocess.check_output(
                ["xprop", "-root", "_VNC_KEYBOARD_CAPS_BRIDGE"], text=True
            )
            assert f"= {server.pid}, 1" in bridge_pid, bridge_pid

        k.STATE_DIR = Path(os.environ["XDG_RUNTIME_DIR"]) / "keyboard-state"
        k.STATE_FILE = k.STATE_DIR / "state.json"
        backend = k.Backend()
        baseline = backend.vnc()
        k.enable_mode(backend)
        if "VNC_TEST_CAPS_BRIDGE" in os.environ:
            assert backend.vnc()["caps_bridge"] == "1"
        win = Gtk.Window(title="Isolated VNC Jamo Composition Probe")
        entry = Gtk.Entry()
        win.add(entry)
        win.show_all()
        entry.grab_focus()
        import gi.repository.GdkX11

        xid = win.get_window().get_xid()
        result = {}
        errors = []

        def record(label, expected):
            done = threading.Event()

            def read():
                actual = entry.get_text()
                result[label] = actual
                if actual != expected:
                    errors.append((label, expected, actual))
                done.set()
                return False

            GLib.idle_add(read)
            assert done.wait(3)

        def send_text(text, unicode=False):
            for c in text:
                tap(sock, ord(c) | (0x1000000 if unicode and ord(c) > 127 else 0))

        def run():
            try:
                time.sleep(1)
                subprocess.run(
                    ["xdotool", "windowfocus", "--sync", str(xid)], check=True
                )
                tap(sock, 0xFF1B)
                send_text("abc ")
                time.sleep(0.5)
                record("latin", "abc ")
                tap(sock, 0xFFE5)
                send_text("ㄱㅏㄴㅏㄷㅏ ", True)
                time.sleep(0.5)
                record("unicode_jamo", "abc 가나다 ")
                send_text("ㅃㅏㄴ ", True)
                time.sleep(0.5)
                record("shifted_jamo", "abc 가나다 빤 ")
                for c in "ㅂㅏㄴ":
                    tap(sock, 0xEA1 + ord(c) - 0x3131)
                send_text(" ")
                time.sleep(0.5)
                record("legacy_jamo", "abc 가나다 빤 반 ")
                # Actual iPad software keyboard uses bare UCS code points.
                send_text("ㄱㅏㄴㅏㄷㅏ ㅃㅏㄴ ")
                time.sleep(0.5)
                record("ipad_software_jamo", "abc 가나다 빤 반 가나다 빤 ")
                tap(sock, 0xFFE5)
                send_text("abc ")
                key(sock, 0xFFE1, True)
                send_text("ABC")
                key(sock, 0xFFE1, False)
                send_text(" !@? ")
                time.sleep(0.5)
                record("back_to_latin", "abc 가나다 빤 반 가나다 빤 abc ABC !@? ")
                if "VNC_TEST_CAPS_BRIDGE" in os.environ:
                    # Actual observed RVNC iPad pattern: Caps down, uppercase
                    # letters, Caps up, lowercase letters. Physical Shift is separate.
                    key(sock, 0xFFE5, True)
                    send_text("C ")
                    key(sock, 0xFFE5, False)
                    send_text("c ")
                    key(sock, 0xFFE5, True)
                    send_text("QKS ")
                    key(sock, 0xFFE5, False)
                    send_text("c ")
                    key(sock, 0xFFE5, True)
                    key(sock, 0xFFE1, True)
                    send_text("Q")
                    key(sock, 0xFFE1, False)
                    send_text("KS ")
                    time.sleep(0.5)
                    record(
                        "ipad_state_caps", "abc 가나다 빤 반 가나다 빤 abc ABC !@? ㅊ c 반 c 빤 "
                    )
                    key(sock, 0xFFE5, False)
                    # A second client (Mac) must not inherit the iPad latch state.
                    other = connect(port)
                    tap(other, 0xFFE5)
                    for c in "rkskek ":
                        tap(other, ord(c))
                    tap(other, 0xFFE5)
                    for c in "abc ":
                        tap(other, ord(c))
                    time.sleep(0.5)
                    record(
                        "second_mac_client",
                        "abc 가나다 빤 반 가나다 빤 abc ABC !@? ㅊ c 반 c 빤 가나다 abc ",
                    )
                    other.close()
                # macOS Screen Sharing sends either Command key as Alt_L.
                # Exercise actual GTK clipboard actions, not just key event names.
                previous = result.get('second_mac_client', result['back_to_latin'])
                def command(letter):
                    key(sock, 0xFFE9, True)
                    tap(sock, ord(letter))
                    key(sock, 0xFFE9, False)
                    time.sleep(.2)
                command('a')
                command('c')
                tap(sock, 0xFF57)  # End: deselect and append.
                command('v')
                time.sleep(.5)
                record('command_copy_paste', previous + previous)
                assert not k.caps_lock(), "Remapped Caps enabled uppercase lock"
            except BaseException as exc:
                errors.append(repr(exc))
            finally:
                GLib.idle_add(Gtk.main_quit)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        GLib.timeout_add_seconds(
            45, lambda: (errors.append("timeout"), Gtk.main_quit(), False)[-1]
        )
        Gtk.main()
        thread.join(2)
        k.disable_mode(backend)
        assert backend.vnc() == baseline
        tap(sock, 0xFFE5)
        assert k.caps_lock(), "Off did not restore original Caps Lock"
        result["original_caps_restored"] = True
        sock.close()
        print(
            json.dumps({"result": result, "errors": errors}, ensure_ascii=False),
            flush=True,
        )
        assert not errors
    finally:
        for p in reversed(processes):
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()


if "--worker" in sys.argv:
    worker()
else:
    with tempfile.TemporaryDirectory(prefix="vnc-jamo-probe-") as tmp:
        log = open(Path(tmp) / "xvfb.log", "w")
        x = subprocess.Popen(
            [
                "Xvfb",
                "-displayfd",
                "1",
                "-screen",
                "0",
                "640x480x24",
                "-nolisten",
                "tcp",
            ],
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
        )
        try:
            with selectors.DefaultSelector() as sel:
                sel.register(x.stdout, selectors.EVENT_READ)
                assert sel.select(5)
                display = ":" + x.stdout.readline().strip()
            Path(tmp + "/runtime").mkdir(mode=0o700)
            env = {
                **os.environ,
                "XDG_RUNTIME_DIR": tmp + "/runtime",
                "GIO_USE_VFS": "local",
                "GTK_USE_PORTAL": "0",
                "NO_AT_BRIDGE": "1",
                "DISPLAY": display,
                "XDG_CONFIG_HOME": tmp + "/config",
                "XDG_CACHE_HOME": tmp + "/cache",
                "IBUS_ADDRESS": "unix:path=" + tmp + "/ibus.sock",
                "GTK_IM_MODULE": "ibus",
                "QT_IM_MODULE": "ibus",
                "XMODIFIERS": "@im=ibus",
            }
            for keyname in ("XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS"):
                env.pop(keyname, None)
            subprocess.run(
                ["dbus-run-session", "--", "/usr/bin/python3", __file__, "--worker"],
                env=env,
                check=True,
                timeout=55,
            )
        finally:
            x.terminate()
            x.wait(timeout=3)
            log.close()
