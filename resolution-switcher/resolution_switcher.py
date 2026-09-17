#!/usr/bin/python3
"""Small X11 resolution chooser with an independent rollback process."""
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time

APP_DIR = Path(__file__).resolve().parent
TIMEOUT = 20
PROFILES = (
    ("1920x1080", "Mac · FHD", "1920 × 1080  ·  넓은 작업 공간"),
    ("1600x1050", "iPad · 선명한 전체 보기", "1600 × 1050  ·  원본 화질 + 하단 여유"),
    ("1184x824", "iPad · 가로 화면", "1184 × 824  ·  가로 비율에 맞춤"),
    ("1024x768", "iPad · 큰 글씨", "1024 × 768  ·  프로그램 창 높이까지 확보"),
)


# Transmit original pixels; pre-shrinking text caused blur when the client enlarged it.
PROFILE_SCALES = {}

# Landscape CVT modes; the shorter desktop leaves room for the viewer toolbar.
# Registered in the current X session only; no Xorg/system configuration edits.
IPAD_MODELINES = {
    "1600x1050": "114.00 1600 1648 1680 1760 1050 1053 1063 1080 +hsync -vsync",
    "1184x824": "68.25 1184 1232 1264 1344 824 827 837 848 +hsync -vsync",
}


def ensure_ipad_modes():
    state = query()
    errors = []
    for mode, timings in IPAD_MODELINES.items():
        if mode in state["modes"]:
            continue
        try:
            try:
                randr("--newmode", mode, *timings.split())
            except RuntimeError as exc:
                # A named mode can exist globally without being attached here.
                if "BadName" not in str(exc):
                    raise
            randr("--addmode", state["output"], mode)
        except Exception as exc:
            errors.append(mode)
            log_event({"status": "mode-unavailable", "mode": mode, "error": str(exc)})
    return query(), errors


def randr(*args):
    result = subprocess.run(
        ["/usr/bin/xrandr", *args], capture_output=True, text=True,
        timeout=8, env={**os.environ, "LC_ALL": "C"},
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "화면 설정을 읽거나 변경하지 못했습니다.")
    return result.stdout


def query():
    outputs = []
    current = None
    raw = randr("--query")
    screen = re.search(r"current (\d+) x (\d+)", raw)
    for line in raw.splitlines():
        header = re.match(r"^(\S+) connected(?: primary)? (\d+x\d+)\+(-?\d+)\+(-?\d+)", line)
        if line and not line[0].isspace():
            current = None
        if header:
            current = {"output": header[1], "size": header[2], "modes": {}, "mode": None, "rate": None, "position": header[3] + "x" + header[4], "framebuffer": "x".join(screen.groups()) if screen else None}
            outputs.append(current)
        elif current:
            mode = re.match(r"^\s+(\d+x\d+)\s+(.+)$", line)
            if mode:
                rates = re.findall(r"(\d+\.\d+)([*+]*)", mode[2])
                current["modes"][mode[1]] = [r for r, _ in rates]
                for rate, flags in rates:
                    if "*" in flags:
                        current.update(mode=mode[1], rate=rate)
    if len(outputs) != 1:
        raise RuntimeError("이 프로그램은 활성 화면이 하나인 X11 데스크톱에서 사용합니다.")
    if not outputs[0]["mode"]:
        raise RuntimeError("현재 해상도를 확인하지 못해 변경을 중단했습니다.")
    return outputs[0]


def nvidia(*args):
    result = subprocess.run(
        ["/usr/bin/nvidia-settings", *args], capture_output=True, text=True,
        timeout=8, env={**os.environ, "LC_ALL": "C"},
    )
    if result.returncode or "ERROR:" in result.stderr:
        raise RuntimeError(result.stderr.strip() or "NVIDIA 화면 변경에 실패했습니다.")
    return result.stdout.strip()


def apply_mode(output, mode, rate):
    args = ("--output", output, "--mode", mode, "--rate", rate)
    try:
        randr(*args)
    except RuntimeError as exc:
        # NVIDIA can reject the intermediate framebuffer shrink in RandR 1.2.
        # Switch the whole MetaMode atomically, then select the exact refresh rate.
        if "RRSetScreenSize" not in str(exc) or not Path("/usr/bin/nvidia-settings").exists():
            raise
        state = query()
        if state["output"] != output or state["position"] != "0x0":
            raise RuntimeError("현재 화면 배치에서는 NVIDIA 대체 전환을 사용할 수 없습니다.")
        nvidia("--assign", f"CurrentMetaMode={output}: {mode} +0+0")
        randr(*args)
    state = query()
    if (state["output"], state["mode"], state["framebuffer"]) != (output, mode, mode):
        raise RuntimeError("요청한 해상도가 화면 전체에 적용되지 않았습니다.")



def x_tool(*args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=3,
                            env={**os.environ, "LC_ALL": "C"})
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "창 정보를 확인하지 못했습니다.")
    return result.stdout


def work_area(framebuffer):
    width, height = map(int, framebuffer.split("x"))
    props = x_tool("/usr/bin/xprop", "-root", "_NET_CURRENT_DESKTOP", "_NET_WORKAREA")
    desktop = int(re.search(r"_NET_CURRENT_DESKTOP.*?=\s*(\d+)", props)[1])
    values = [int(v) for v in re.search(r"_NET_WORKAREA.*?=\s*([^\n]+)", props)[1].split(",")]
    left, top, area_width, area_height = values[desktop * 4:desktop * 4 + 4]
    left, top = min(max(0, left), width - 1), min(max(0, top), height - 1)
    return left, top, min(area_width, width - left), min(area_height, height - top)


_WNCK = None
_GDK = None


def window_screen():
    global _WNCK, _GDK
    if _WNCK is None:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        gi.require_version("Wnck", "3.0")
        from gi.repository import Gdk, Gtk, Wnck
        Gtk.init_check()
        Wnck.set_client_type(Wnck.ClientType.PAGER)
        _WNCK, _GDK = Wnck, Gdk
    from gi.repository import GLib
    context = GLib.MainContext.default()
    if not context.is_owner():
        for _ in range(50):
            if not context.pending():
                break
            context.iteration(False)
    screen = _WNCK.Screen.get_default()
    screen.force_update()
    return screen


def capture_windows():
    screen = window_screen()
    workspace = screen.get_active_workspace()
    windows = []
    for win in screen.get_windows():
        if win.get_window_type() != _WNCK.WindowType.NORMAL or not win.is_on_workspace(workspace):
            continue
        if win.is_minimized() or win.is_fullscreen() or win.is_maximized_horizontally() or win.is_maximized_vertically():
            continue
        if win.get_pid() == os.getpid():
            continue
        wid = hex(win.get_xid())
        try:
            props = x_tool("/usr/bin/xprop", "-id", wid, "WM_NORMAL_HINTS", "_GTK_APPLICATION_ID")
            if "local.kmg.VncResolutionSwitcher" in props:
                continue
            frame = win.get_geometry()
            client = win.get_client_window_geometry()
            minsize = re.search(r"minimum size:\s*(\d+) by (\d+)", props)
            minimum = list(map(int, minsize.groups())) if minsize else [1, 1]
            bl, bt = client.xp - frame.xp, client.yp - frame.yp
            borders = [bl, frame.widthp - client.widthp - bl, bt, frame.heightp - client.heightp - bt]
            windows.append({"id": wid, "pid": str(win.get_pid()),
                            "geometry": [frame.xp, frame.yp, client.widthp, client.heightp],
                            "borders": borders, "minimum": minimum})
        except (RuntimeError, subprocess.TimeoutExpired):
            continue
    return windows


def set_window_geometry(window, geometry):
    screen = window_screen()
    win = next((w for w in screen.get_windows() if w.get_xid() == int(window["id"], 16)), None)
    if win is None or str(win.get_pid()) != window.get("pid"):
        return
    x, y, width, height = geometry
    bl, br, bt, bb = window["borders"]
    mask = (_WNCK.WindowMoveResizeMask.X | _WNCK.WindowMoveResizeMask.Y |
            _WNCK.WindowMoveResizeMask.WIDTH | _WNCK.WindowMoveResizeMask.HEIGHT)
    win.set_geometry(_WNCK.WindowGravity.STATIC, mask, x, y, width + bl + br, height + bt + bb)
    _GDK.Display.get_default().flush()


def fit_windows(windows, framebuffer):
    left, top, width, height = work_area(framebuffer)
    for window in windows:
        x, y, w, h = window["geometry"]
        bl, br, bt, bb = window["borders"]
        minw, minh = window["minimum"]
        available_w, available_h = width - bl - br, height - bt - bb
        if available_w < minw or available_h < minh:
            log_event({"status": "window-minimum-exceeds-screen", "id": window["id"], "minimum": window["minimum"]})
            continue
        w, h = max(minw, min(w, available_w)), max(minh, min(h, available_h))
        x = max(left, min(x, left + width - w - bl - br))
        y = max(top, min(y, top + height - h - bt - bb))
        try:
            if [x, y, w, h] != window["geometry"]:
                set_window_geometry(window, [x, y, w, h])
        except (RuntimeError, subprocess.TimeoutExpired):
            pass


def restore_windows(windows):
    for window in windows:
        try:
            set_window_geometry(window, window["geometry"])
        except (RuntimeError, subprocess.TimeoutExpired):
            pass



def vnc_scale():
    response = x_tool("/usr/bin/x11vnc", "-Q", "scale")
    match = re.search(r"(?:ans|aro)=scale:([^,\n]*)", response)
    if not match:
        raise RuntimeError("VNC 화면 배율을 확인하지 못했습니다.")
    return match[1].strip() or "1"


def set_vnc_scale(scale):
    if vnc_scale() == scale:
        return
    x_tool("/usr/bin/x11vnc", "-sync", "-R", "scale:" + scale)
    if vnc_scale() != scale:
        raise RuntimeError("VNC 화면 배율이 적용되지 않았습니다.")


def restore_state(snapshot):
    if snapshot.get("metamode"):
        nvidia("--assign", "CurrentMetaMode=" + snapshot["metamode"])
    apply_mode(snapshot["output"], snapshot["mode"], snapshot["rate"])
    if "vnc_scale" in snapshot:
        set_vnc_scale(snapshot["vnc_scale"])
    if snapshot.get("windows"):
        time.sleep(0.2)
        restore_windows(snapshot["windows"])


def log_event(event):
    try:
        folder = Path.home() / ".local/state/vnc-resolution-switcher"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "events.jsonl").open("a") as stream:
            stream.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **event}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def guard_main(snapshot, timeout):
    """A closed UI pipe, explicit revert, or timeout restores the old mode."""
    selector = selectors.DefaultSelector()
    selector.register(sys.stdin, selectors.EVENT_READ)
    print(json.dumps({"status": "ready"}), flush=True)
    events = selector.select(timeout)
    command = os.read(sys.stdin.fileno(), 128).strip() if events else b""
    if command == b"keep":
        result = {"status": "kept"}
    else:
        try:
            restore_state(snapshot)
            result = {"status": "reverted", "mode": snapshot["mode"]}
        except Exception as exc:
            result = {"status": "error", "error": str(exc)}
    log_event(result)
    try:
        print(json.dumps(result, ensure_ascii=False), flush=True)
    except BrokenPipeError:
        pass
    return 1 if result["status"] == "error" else 0


def start_guard(state, timeout=TIMEOUT, windows=None):
    snapshot = {key: state[key] for key in ("output", "mode", "rate")}
    snapshot["vnc_scale"] = vnc_scale()
    if windows is not None:
        snapshot["windows"] = windows
    if Path("/usr/bin/nvidia-settings").exists():
        try:
            raw = nvidia("--query", "CurrentMetaMode", "--terse")
            if "::" in raw:
                snapshot["metamode"] = raw.split("::", 1)[1].strip()
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            pass
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--guard", json.dumps(snapshot), str(timeout)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        if not selector.select(5) or process.stdout.readline().strip() != '{"status": "ready"}':
            process.stdin.close()
            process.wait(timeout=12)
            raise RuntimeError("자동 복구 준비에 실패해 해상도를 변경하지 않았습니다.")
    finally:
        selector.close()
    return process


def finish_guard(process, keep=False):
    try:
        stdout, _ = process.communicate("keep\n" if keep else "revert\n", timeout=12)
    except subprocess.TimeoutExpired:
        raise RuntimeError("화면 복구가 지연되고 있습니다. 잠시 뒤 현재 해상도를 확인해 주세요.")
    lines = stdout.strip().splitlines()
    if not lines:
        raise RuntimeError("화면 변경 결과를 확인하지 못했습니다.")
    result = json.loads(lines[-1])
    if result["status"] == "error":
        raise RuntimeError(result["error"])
    return result


def create_app():
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gio, GLib, Gtk

    class Chooser(Gtk.Application):
        def __init__(self):
            super().__init__(application_id="local.kmg.VncResolutionSwitcher", flags=Gio.ApplicationFlags.FLAGS_NONE)
            self.window = None
            self.guard = None
            self.timer = None
            self.deadline = None
            self.preview_mode = None
            self.preview_windows = []
            self.buttons = []

        def do_activate(self):
            if self.window:
                self.window.present()
                return
            self.window = Gtk.ApplicationWindow(application=self, title="화면 해상도 선택")
            self.window.set_default_size(490, 600)
            self.window.set_resizable(False)
            self.window.set_position(Gtk.WindowPosition.CENTER)
            self.window.set_icon_from_file(str(APP_DIR / "display.svg"))
            self.window.connect("delete-event", self.on_close)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=24)
            self.window.add(box)
            title = Gtk.Label(xalign=0)
            title.set_markup('<span size="x-large" weight="bold">접속 기기에 맞는 화면</span>')
            box.pack_start(title, False, False, 0)
            self.current_label = Gtk.Label(xalign=0)
            box.pack_start(self.current_label, False, False, 0)
            box.pack_start(Gtk.Separator(), False, False, 2)
            self.choices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.pack_start(self.choices, False, False, 0)
            group = None
            for mode, name, detail in PROFILES:
                button = Gtk.RadioButton.new_with_label_from_widget(group, name + "\n" + detail)
                group = group or button
                button.set_size_request(-1, 57)
                self.choices.pack_start(button, False, False, 0)
                self.buttons.append((mode, button))
            note = Gtk.Label(xalign=0)
            note.set_text("iPad는 ‘선명한 전체 보기’를 사용해 보세요.\nVNC 앱에서 ‘비율 유지 / 화면에 맞추기’를 켜 주세요.\n같은 서버 화면을 보는 모든 접속에 적용됩니다.")
            note.set_line_wrap(True)
            box.pack_start(note, False, False, 4)
            ratio_check = Gtk.Box(spacing=12)
            circle = Gtk.DrawingArea()
            circle.set_size_request(44, 44)
            def draw_circle(widget, cr):
                cr.set_source_rgb(0.15, 0.39, 0.92)
                cr.set_line_width(3)
                cr.arc(22, 22, 17, 0, 6.283185307179586)
                cr.stroke()
                return False
            circle.connect("draw", draw_circle)
            ratio_check.pack_start(circle, False, False, 0)
            hint = Gtk.Label(label="이 원이 타원처럼 보이면\nVNC 앱에서 ‘비율 유지’를 확인해 주세요.", xalign=0)
            ratio_check.pack_start(hint, False, False, 0)
            box.pack_start(ratio_check, False, False, 0)
            self.status = Gtk.Label(xalign=0)
            self.status.set_line_wrap(True)
            self.status.set_max_width_chars(48)
            box.pack_start(self.status, False, False, 0)
            self.actions = Gtk.Box(spacing=8)
            box.pack_end(self.actions, False, False, 0)
            self.close_button = Gtk.Button(label="닫기")
            self.close_button.connect("clicked", lambda _: self.window.close())
            self.apply_button = Gtk.Button(label="선택한 해상도 적용")
            self.apply_button.get_style_context().add_class("suggested-action")
            self.apply_button.connect("clicked", self.on_apply)
            self.actions.pack_start(self.close_button, False, False, 0)
            self.actions.pack_end(self.apply_button, False, False, 0)
            self.confirm = Gtk.Box(spacing=8)
            self.revert_button = Gtk.Button(label="이전 해상도로 복구")
            self.revert_button.connect("clicked", lambda _: self.finish(False))
            self.keep_button = Gtk.Button(label="이 해상도 유지")
            self.keep_button.get_style_context().add_class("suggested-action")
            self.keep_button.connect("clicked", lambda _: self.finish(True))
            self.confirm.pack_start(self.revert_button, True, True, 0)
            self.confirm.pack_start(self.keep_button, True, True, 0)
            box.pack_end(self.confirm, False, False, 0)
            self.confirm.set_no_show_all(True)
            self.refresh()
            self.window.show_all()
            GLib.timeout_add(200, self.center_window)

        def center_window(self):
            try:
                left, top, width, height = work_area(query()["framebuffer"])
                frame = self.window.get_window().get_frame_extents()
                self.window.move(left + max(0, (width - frame.width) // 2), top + max(0, (height - frame.height) // 2))
            except Exception as exc:
                log_event({"status": "window-position-error", "error": str(exc)})
            return False

        def fit_preview(self):
            if self.guard and self.preview_mode:
                try:
                    if query()["framebuffer"] == self.preview_mode:
                        fit_windows(self.preview_windows, self.preview_mode)
                except Exception as exc:
                    log_event({"status": "window-fit-error", "error": str(exc)})
                self.center_window()
            return False

        def refresh(self):
            try:
                state, unavailable = ensure_ipad_modes()
                if unavailable:
                    self.status.set_text("이 화면에서 사용할 수 없는 iPad 해상도: " + ", ".join(unavailable))
                self.current_label.set_text("현재 화면: " + state["mode"].replace("x", " × "))
                for mode, button in self.buttons:
                    button.set_sensitive(mode in state["modes"])
                    if mode == state["mode"]:
                        button.set_active(True)
                self.apply_button.set_sensitive(True)
                return state
            except Exception as exc:
                self.apply_button.set_sensitive(False)
                self.status.set_text(str(exc))
                return None

        def on_apply(self, _):
            if self.guard:
                return
            selected = next(mode for mode, button in self.buttons if button.get_active())
            try:
                state = query()
                target_scale = PROFILE_SCALES.get(selected, "1")
                if selected == state["mode"] and vnc_scale() == target_scale:
                    self.status.set_text("이미 선택한 해상도를 사용 중입니다.")
                    return
                if selected not in state["modes"]:
                    raise RuntimeError("현재 화면에서 지원하지 않는 해상도입니다.")
                rate = min(state["modes"][selected], key=lambda value: abs(float(value) - 60))
                self.preview_windows = capture_windows()
                self.guard = start_guard(state, windows=self.preview_windows)
                self.deadline = time.monotonic() + TIMEOUT
                apply_mode(state["output"], selected, rate)
                set_vnc_scale(target_scale)
                if self.guard.poll() is not None or time.monotonic() >= self.deadline:
                    raise RuntimeError("변경 시간이 초과되어 이전 해상도로 복구합니다.")
                self.preview_mode = selected
                log_event({"status": "preview", "from": state["mode"], "to": selected, "vnc_scale": target_scale})
                preview_text = "미리보기: " + selected.replace("x", " × ")
                if target_scale != "1":
                    preview_text += "  ·  축소 전송 중"
                self.current_label.set_text(preview_text)
                self.choices.set_sensitive(False)
                self.actions.hide()
                self.confirm.set_no_show_all(False)
                self.confirm.show_all()
                GLib.timeout_add(350, self.fit_preview)
                self.tick()
                self.timer = GLib.timeout_add(200, self.tick)
            except Exception as exc:
                message = str(exc)
                if self.guard:
                    try:
                        finish_guard(self.guard)
                    except Exception as restore_exc:
                        message += "\n복구 확인 필요: " + str(restore_exc)
                    self.guard = None
                self.refresh()
                self.status.set_text(message)

        def tick(self):
            remaining = max(0, int(self.deadline - time.monotonic() + 0.999))
            self.status.set_text(f"화면이 잘 보이나요? {remaining}초 안에 ‘유지’를 누르세요.\n확인하지 않으면 이전 해상도로 자동 복구됩니다.")
            if not remaining or self.guard.poll() is not None:
                self.timer = None
                self.finish(False)
                return False
            return True

        def finish(self, keep):
            if not self.guard:
                return
            if self.timer:
                GLib.source_remove(self.timer)
                self.timer = None
            conflict = False
            if keep:
                try:
                    actual = query()
                    conflict = (actual["mode"] != self.preview_mode or actual["framebuffer"] != self.preview_mode
                                or vnc_scale() != PROFILE_SCALES.get(self.preview_mode, "1"))
                except Exception:
                    conflict = True
                if conflict:
                    keep = False
                    log_event({"status": "external-resolution-change", "expected": self.preview_mode})
            try:
                result = finish_guard(self.guard, keep)
                message = "이 해상도를 유지합니다." if result["status"] == "kept" else "이전 해상도로 복구했습니다."
                if conflict and result["status"] == "reverted":
                    message = "다른 설정이 해상도를 바꾸어 이전 화면으로 복구했습니다."
            except Exception as exc:
                message = "화면 상태를 확인해 주세요: " + str(exc)
            self.guard = None
            self.preview_mode = None
            self.confirm.hide()
            self.actions.show_all()
            self.choices.set_sensitive(True)
            self.refresh()
            self.status.set_text(message)
            GLib.timeout_add(250, self.center_window)

        def on_close(self, *_):
            if self.guard:
                self.finish(False)
            self.quit()
            return False

    return Chooser()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--guard":
        sys.exit(guard_main(json.loads(sys.argv[2]), float(sys.argv[3])))
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        print(json.dumps(query(), ensure_ascii=False, indent=2))
    else:
        sys.exit(create_app().run([sys.argv[0]]))
