"""Windows display APIs. Importing this module never changes the desktop."""
import base64
import ctypes as C
import os

U32, I32, U16 = C.c_uint32, C.c_int32, C.c_uint16


class Point(C.Structure):
    _fields_ = [('x', I32), ('y', I32)]


class DevMode(C.Structure):
    _fields_ = [('device', C.c_char * 32), ('spec', U16), ('driver', U16),
                ('size', U16), ('extra', U16), ('fields', U32),
                ('position', Point), ('orientation', U32), ('fixed_output', U32),
                ('color', C.c_int16), ('duplex', C.c_int16), ('y_resolution', C.c_int16),
                ('tt_option', C.c_int16), ('collate', C.c_int16), ('form', C.c_char * 32),
                ('log_pixels', U16), ('bits', U32), ('width', U32), ('height', U32),
                ('flags', U32), ('frequency', U32), ('icm_method', U32), ('icm_intent', U32),
                ('media', U32), ('dither', U32), ('reserved1', U32), ('reserved2', U32),
                ('panning_width', U32), ('panning_height', U32)]


class DisplayDevice(C.Structure):
    _fields_ = [('size', U32), ('device', C.c_char * 32), ('description', C.c_char * 128),
                ('flags', U32), ('device_id', C.c_char * 128), ('key', C.c_char * 128)]


class Rect(C.Structure):
    _fields_ = [('left', I32), ('top', I32), ('right', I32), ('bottom', I32)]


class Placement(C.Structure):
    _fields_ = [('length', U32), ('flags', U32), ('show', U32),
                ('minimum', Point), ('maximum', Point), ('normal', Rect)]


def pack(value):
    return base64.b64encode(bytes(value)).decode('ascii')


def unpack(kind, value):
    raw = base64.b64decode(value, validate=True)
    if len(raw) != C.sizeof(kind):
        raise RuntimeError('Invalid saved Windows display structure')
    return kind.from_buffer_copy(raw)


class WindowsBackend:
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('These tools require Windows 10/11')
        self.api = C.WinDLL('user32', use_last_error=True)
        self.api.EnumDisplayDevicesA.argtypes = [C.c_char_p, U32, C.POINTER(DisplayDevice), U32]
        self.api.EnumDisplaySettingsExA.argtypes = [C.c_char_p, U32, C.POINTER(DevMode), U32]
        self.api.ChangeDisplaySettingsExA.argtypes = [C.c_char_p, C.POINTER(DevMode), C.c_void_p, U32, C.c_void_p]
        self.api.ChangeDisplaySettingsExA.restype = I32
        self.api.SetDisplayConfig.argtypes = [U32, C.c_void_p, U32, C.c_void_p, U32]
        self.api.SetDisplayConfig.restype = I32
        self.api.GetWindowPlacement.argtypes = [C.c_void_p, C.POINTER(Placement)]
        self.api.SetWindowPlacement.argtypes = [C.c_void_p, C.POINTER(Placement)]
        self.api.GetWindowThreadProcessId.argtypes = [C.c_void_p, C.POINTER(U32)]
        self.api.IsWindow.argtypes = [C.c_void_p]
        self.api.IsWindowVisible.argtypes = [C.c_void_p]
        self.window_callback = C.WINFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p)
        self.api.EnumWindows.argtypes = [self.window_callback, C.c_void_p]
        try:
            self.api.SetProcessDpiAwarenessContext.argtypes = [C.c_void_p]
            self.api.SetProcessDpiAwarenessContext(C.c_void_p(-4))
        except AttributeError:
            self.api.SetProcessDPIAware()

    def mode(self, device, index=0xFFFFFFFF):
        mode = DevMode()
        mode.size = C.sizeof(mode)
        if not self.api.EnumDisplaySettingsExA(device.encode('ascii'), index, C.byref(mode), 0):
            return None
        return mode

    def devices(self):
        result = []
        index = 0
        while True:
            device = DisplayDevice()
            device.size = C.sizeof(device)
            if not self.api.EnumDisplayDevicesA(None, index, C.byref(device), 0):
                break
            index += 1
            if device.flags & 8:  # Ignore legacy mirroring drivers.
                continue
            name = device.device.decode('ascii')
            current = self.mode(name) if device.flags & 1 else None
            registered = current or self.mode(name, 0xFFFFFFFE)
            if registered is None:
                continue
            description = device.description.decode('mbcs', errors='replace')
            result.append({'device': name, 'description': description,
                           'virtual': 'virtual display' in description.lower() or 'mttvdd' in description.lower(),
                           'active': bool(device.flags & 1), 'primary': bool(device.flags & 4),
                           'width': int(registered.width), 'height': int(registered.height),
                           'x': int(registered.position.x), 'y': int(registered.position.y),
                           'frequency': int(registered.frequency), 'orientation': int(registered.orientation)})
        return result

    def modes(self, device):
        result = []
        index = 0
        while True:
            mode = self.mode(device, index)
            if mode is None:
                break
            result.append(mode)
            index += 1
        return result

    def choose(self, device=None, virtual=False):
        devices = self.devices()
        if device:
            candidates = [item for item in devices if item['device'] == device]
        elif virtual:
            candidates = [item for item in devices if item['virtual']]
        else:
            candidates = [item for item in devices if item['primary'] and item['active']]
        if len(candidates) != 1:
            raise RuntimeError('Choose one available display with --display; install the virtual driver for headless mode')
        return candidates[0]

    def target_mode(self, device, width, height):
        current = self.mode(device) or self.mode(device, 0xFFFFFFFE)
        candidates = [m for m in self.modes(device) if (m.width, m.height, m.bits, m.orientation) ==
                      (width, height, current.bits, current.orientation)]
        if not candidates:
            raise RuntimeError('The display driver does not advertise this resolution; choose the virtual display')
        target = min(candidates, key=lambda m: (abs(int(m.frequency) - int(current.frequency)), -int(m.frequency)))
        target.position = current.position
        target.fields = 0x00000020 | 0x00080000 | 0x00100000 | 0x00040000 | 0x00400000 | 0x00000080
        self._change(device, target, 2)  # CDS_TEST before any change.
        return target

    def _change(self, device, mode, flags=0):
        result = self.api.ChangeDisplaySettingsExA(device.encode('ascii') if device else None,
                                                  C.byref(mode) if mode is not None else None, None, flags, None)
        if result != 0:
            raise RuntimeError('Windows display change failed for %s (code %d)' % (device or 'topology', result))

    def snapshot(self):
        displays = []
        for item in self.devices():
            mode = self.mode(item['device']) or self.mode(item['device'], 0xFFFFFFFE)
            displays.append({**item, 'mode': pack(mode)})
        windows = []

        @self.window_callback
        def capture(hwnd, _):
            if self.api.IsWindowVisible(hwnd):
                placement = Placement()
                placement.length = C.sizeof(placement)
                pid = U32()
                self.api.GetWindowThreadProcessId(hwnd, C.byref(pid))
                if self.api.GetWindowPlacement(hwnd, C.byref(placement)) and placement.show == 1:
                    windows.append({'handle': int(hwnd), 'pid': pid.value, 'placement': pack(placement)})
            return 1

        self.api.EnumWindows(capture, None)
        return {'schema': 1, 'displays': displays, 'windows': windows}

    def apply(self, device, width, height, headless=False):
        target = self.target_mode(device, width, height)
        if headless:
            target.position = Point(0, 0)
            # Explicit topology selection is persistent; the guard restores it on cancellation.
            self._change(device, target, 0x10000011)  # UPDATE_REGISTRY | NORESET | SET_PRIMARY
            for item in self.devices():
                if item['device'] != device and item['active']:
                    detached = DevMode()
                    detached.size = C.sizeof(detached)
                    detached.fields = 0x00000020 | 0x00080000 | 0x00100000
                    self._change(item['device'], detached, 0x10000001)
            self._change(None, None)
        else:
            self._change(device, target)
        live = self.mode(device)
        if live is None or (live.width, live.height) != (width, height):
            raise RuntimeError('Windows did not apply the requested resolution')

    def restore(self, snapshot):
        current = {item['device']: item for item in self.devices()}
        available = set(current)
        if any(item['active'] and item['device'] not in available for item in snapshot['displays']):
            raise RuntimeError('An original display is disconnected; reconnect it before restoring the topology')
        if any(item['active'] and not current[item['device']]['active'] for item in snapshot['displays']):
            # An NVIDIA adapter disabled by an IDD-only topology cannot always be
            # reattached by ChangeDisplaySettingsEx. Re-enable the connected paths
            # through the modern topology API before restoring their exact modes.
            result = self.api.SetDisplayConfig(0, None, 0, None, 0x84)  # SDC_APPLY | SDC_TOPOLOGY_EXTEND
            if result != 0:
                raise RuntimeError('Windows could not re-enable connected display paths (code %d)' % result)
            current = {item['device']: item for item in self.devices()}
        ordered = sorted(snapshot['displays'], key=lambda item: not item['primary'])
        for item in ordered:
            if item['device'] not in available:
                continue
            # NVIDIA enumerates unused connectors with zero-sized registry modes.
            # Trying to detach such an already inactive connector returns BADMODE
            # and would prevent the pending multi-display restore from being applied.
            if not item['active'] and not current[item['device']]['active']:
                continue
            mode = unpack(DevMode, item['mode'])
            mode.fields = 0x00000020 | 0x00080000 | 0x00100000 | 0x00040000 | 0x00400000 | 0x00000080
            if not item['active']:
                mode.width = mode.height = 0
                mode.fields = 0x00000020 | 0x00080000 | 0x00100000
            flags = 0x10000001 | (0x10 if item['primary'] else 0)
            self._change(item['device'], mode, flags)
        self._change(None, None)
        live = {item['device']: item for item in self.devices()}
        for item in snapshot['displays']:
            actual = live.get(item['device'])
            if item['active'] and (not actual or any(actual[key] != item[key] for key in
                                                     ('active', 'primary', 'width', 'height', 'x', 'y', 'orientation', 'frequency'))):
                raise RuntimeError('The original display layout was not fully restored')
        for item in snapshot.get('windows', []):
            pid = U32()
            self.api.GetWindowThreadProcessId(item['handle'], C.byref(pid))
            if self.api.IsWindow(item['handle']) and pid.value == item['pid']:
                placement = unpack(Placement, item['placement'])
                self.api.SetWindowPlacement(item['handle'], C.byref(placement))

    def virtual_screen(self):
        return dict(zip(('x', 'y', 'width', 'height'), [self.api.GetSystemMetrics(i) for i in (76, 77, 78, 79)]))
