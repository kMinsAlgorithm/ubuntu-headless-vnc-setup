"""Normalize injected single two-beolsik jamo into the Windows Korean IME.

No text, keys, client addresses, or input history are logged or persisted.
"""
import ctypes as C
import os

MARKER = 0x564E4354
JAMO_KEYS = {
    'ㄱ': 'r', 'ㄲ': 'R', 'ㄴ': 's', 'ㄷ': 'e', 'ㄸ': 'E', 'ㄹ': 'f',
    'ㅁ': 'a', 'ㅂ': 'q', 'ㅃ': 'Q', 'ㅅ': 't', 'ㅆ': 'T', 'ㅇ': 'd',
    'ㅈ': 'w', 'ㅉ': 'W', 'ㅊ': 'c', 'ㅋ': 'z', 'ㅌ': 'x', 'ㅍ': 'v', 'ㅎ': 'g',
    'ㅏ': 'k', 'ㅐ': 'o', 'ㅑ': 'i', 'ㅒ': 'O', 'ㅓ': 'j', 'ㅔ': 'p',
    'ㅕ': 'u', 'ㅖ': 'P', 'ㅗ': 'h', 'ㅛ': 'y', 'ㅜ': 'n', 'ㅠ': 'b',
    'ㅡ': 'm', 'ㅣ': 'l',
}


class JamoMapper:
    def __init__(self):
        self.client_language = False
        self.suppressed = set()

    def handle(self, vk, scan, flags, extra, set_native, tap, shortcut=False):
        if not flags & 0x10 or extra == MARKER:
            return False
        up = bool(flags & 0x80)
        if not up and vk in (0x14, 0x15):
            self.client_language = False  # Explicit remote switching retains legacy Caps behavior.
            return False
        key = JAMO_KEYS.get(chr(scan)) if vk == 0xE7 and 0 <= scan <= 0xFFFF else None
        if key:
            if up:
                if scan in self.suppressed:
                    self.suppressed.discard(scan)
                    return True
                return False
            if shortcut or not set_native(True):
                return False
            if tap(ord(key.upper()), key.isupper()):
                self.client_language = True
                self.suppressed.add(scan)
                return True
            return False
        latin = 0x41 <= vk <= 0x5A or vk == 0xE7 and (0x41 <= scan <= 0x5A or 0x61 <= scan <= 0x7A)
        if self.client_language and not up and latin and not shortcut:
            # A client which sends Korean jamo switches back to ASCII when its
            # own input source becomes English. Commit the Korean composition
            # before letting that English event pass through.
            set_native(False)
        return False


class Point(C.Structure):
    _fields_ = [('x', C.c_int32), ('y', C.c_int32)]


class Rect(C.Structure):
    _fields_ = [('left', C.c_int32), ('top', C.c_int32), ('right', C.c_int32), ('bottom', C.c_int32)]


class GuiThreadInfo(C.Structure):
    _fields_ = [('size', C.c_uint32), ('flags', C.c_uint32),
                ('active', C.c_void_p), ('focus', C.c_void_p), ('capture', C.c_void_p),
                ('menu_owner', C.c_void_p), ('move_size', C.c_void_p), ('caret', C.c_void_p), ('rect', Rect)]


class ForegroundIme:
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('The foreground IME bridge requires Windows')
        self.api = C.WinDLL('user32', use_last_error=True)
        self.imm = C.WinDLL('imm32', use_last_error=True)
        self.api.GetForegroundWindow.restype = C.c_void_p
        self.api.GetWindowThreadProcessId.argtypes = [C.c_void_p, C.POINTER(C.c_uint32)]
        self.api.GetGUIThreadInfo.argtypes = [C.c_uint32, C.POINTER(GuiThreadInfo)]
        self.api.GetKeyboardLayout.argtypes = [C.c_uint32]
        self.api.GetKeyboardLayout.restype = C.c_void_p
        self.api.GetAsyncKeyState.argtypes = [C.c_int]
        self.api.GetAsyncKeyState.restype = C.c_int16
        self.imm.ImmGetDefaultIMEWnd.argtypes = [C.c_void_p]
        self.imm.ImmGetDefaultIMEWnd.restype = C.c_void_p
        self.api.SendMessageTimeoutW.argtypes = [C.c_void_p, C.c_uint32, C.c_size_t, C.c_ssize_t,
                                                C.c_uint32, C.c_uint32, C.POINTER(C.c_size_t)]
        self.cache = None

    def invalidate(self):
        self.cache = None

    def shortcut_pressed(self):
        return any(self.api.GetAsyncKeyState(key) & 0x8000 for key in (0x11, 0x12, 0x5B, 0x5C))

    def command(self, window, command, value=0):
        result = C.c_size_t()
        if not self.api.SendMessageTimeoutW(window, 0x283, command, value, 2, 25, C.byref(result)):
            return None
        return result.value

    def set_native(self, enabled):
        foreground = self.api.GetForegroundWindow()
        if not foreground:
            return False
        thread = self.api.GetWindowThreadProcessId(foreground, None)
        layout = self.api.GetKeyboardLayout(thread) or 0
        if layout & 0xFFFF != 0x412:
            self.invalidate()
            return False  # Never replace an unrelated user's keyboard language.
        info = GuiThreadInfo()
        info.size = C.sizeof(info)
        focus = foreground
        if self.api.GetGUIThreadInfo(thread, C.byref(info)) and info.focus:
            focus = info.focus
        identity = (focus, layout, bool(enabled))
        if self.cache == identity:
            return True
        window = self.imm.ImmGetDefaultIMEWnd(focus)
        if not window:
            return False
        mode = self.command(window, 1)  # IMC_GETCONVERSIONMODE
        if mode is None:
            return False
        if enabled:
            if self.command(window, 6, 1) is None:  # IMC_SETOPENSTATUS
                return False
            desired = mode | 1
        else:
            desired = mode & ~1
        if self.command(window, 2, desired) is None:  # IMC_SETCONVERSIONMODE
            return False
        if not enabled and self.command(window, 6, 0) is None:
            return False
        actual = self.command(window, 1)
        if actual is None or bool(actual & 1) != bool(enabled):
            return False
        self.cache = identity
        return True
