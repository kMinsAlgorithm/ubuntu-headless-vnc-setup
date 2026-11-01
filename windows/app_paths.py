"""Resolve the actual files behind packaged-app AppData redirection."""
import ctypes as C
import os
from pathlib import Path


def physical_path(path):
    path = Path(path).absolute()
    if os.name != 'nt' or not path.exists():
        return path
    api = C.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [C.c_wchar_p, C.c_uint32, C.c_uint32, C.c_void_p,
                                C.c_uint32, C.c_uint32, C.c_void_p]
    api.CreateFileW.restype = C.c_void_p
    api.GetFinalPathNameByHandleW.argtypes = [C.c_void_p, C.c_wchar_p, C.c_uint32, C.c_uint32]
    api.CloseHandle.argtypes = [C.c_void_p]
    handle = api.CreateFileW(str(path), 0, 7, None, 3, 0x02000000, None)
    if handle == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    try:
        buffer = C.create_unicode_buffer(32768)
        size = api.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        if not size or size >= len(buffer):
            raise OSError('Could not resolve the physical VNC tools directory')
        name = buffer.value
        if name.startswith('\\\\?\\UNC\\'):
            name = '\\\\' + name[8:]
        elif name.startswith('\\\\?\\'):
            name = name[4:]
        return Path(name)
    finally:
        api.CloseHandle(handle)


def user_root():
    installed = Path(__file__).absolute().parent
    if installed.name.lower() == 'app' and installed.parent.name.lower() == 'vncdesktoptools':
        return physical_path(installed).parent
    return physical_path(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'VncDesktopTools')
