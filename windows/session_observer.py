"""Read existing TightVNC authentication events and live TCP ownership, locally.

No VNC/control password, packet content, clipboard, or keyboard event is read.
Peer addresses exist only in memory and are never returned in status files.
"""
import ctypes as C
import os
import re
import socket
import struct

U32 = C.c_uint32
AUTHENTICATED = re.compile(r'^Authentication passed by (\S+)\s*$')
DISCONNECTED = re.compile(r'^The client (\S+)(?:\s|$)')


class AuthenticationEvidence:
    def __init__(self):
        self.peers = set()

    def ingest(self, messages, bootstrap=False):
        for message in messages:
            if message in ('Service has been started successfully', 'Service has been stopped'):
                self.peers.clear()
                continue
            match = AUTHENTICATED.match(message)
            if match:
                self.peers.add(match.group(1))
            elif bootstrap:
                match = DISCONNECTED.match(message)
                if match:
                    self.peers.discard(match.group(1))

    def active(self, connected_peers):
        # A failed login or a mere open port never creates authentication evidence.
        # Keep a proven peer until its final live TCP connection disappears. This
        # avoids restoring local screens when an unauthenticated probe disconnects
        # concurrently with an authenticated viewer from the same NAT address.
        self.peers.intersection_update(connected_peers)
        return bool(self.peers)


def event_messages(data):
    """Parse documented EVENTLOGRECORD fields; ignore every other provider."""
    result = []
    offset = 0
    while offset + 56 <= len(data):
        size = struct.unpack_from('<I', data, offset)[0]
        if size < 60 or offset + size > len(data):
            raise RuntimeError('Invalid Windows event record')
        record = data[offset:offset + size]
        number = struct.unpack_from('<I', record, 8)[0]
        source = record[56:].decode('utf-16-le', errors='replace').split('\0', 1)[0]
        count = struct.unpack_from('<H', record, 26)[0]
        strings_offset = struct.unpack_from('<I', record, 36)[0]
        if source.lower() == 'tvnserver' and count and 56 <= strings_offset < size:
            strings = record[strings_offset:].decode('utf-16-le', errors='replace').split('\0')[:count]
            result.extend((number, message) for message in strings)
        offset += size
    return result


class WindowsSessionObserver:
    def __init__(self, port=5900):
        if os.name != 'nt':
            raise RuntimeError('VNC session observation requires Windows')
        self.port = port
        self.advapi = C.WinDLL('advapi32', use_last_error=True)
        self.ip = C.WinDLL('iphlpapi', use_last_error=True)
        a = self.advapi
        a.OpenEventLogW.argtypes = [C.c_wchar_p, C.c_wchar_p]
        a.OpenEventLogW.restype = C.c_void_p
        a.CloseEventLog.argtypes = [C.c_void_p]
        a.GetOldestEventLogRecord.argtypes = [C.c_void_p, C.POINTER(U32)]
        a.GetNumberOfEventLogRecords.argtypes = [C.c_void_p, C.POINTER(U32)]
        a.ReadEventLogW.argtypes = [C.c_void_p, U32, U32, C.c_void_p, U32, C.POINTER(U32), C.POINTER(U32)]
        a.OpenSCManagerW.argtypes = [C.c_wchar_p, C.c_wchar_p, U32]
        a.OpenSCManagerW.restype = C.c_void_p
        a.OpenServiceW.argtypes = [C.c_void_p, C.c_wchar_p, U32]
        a.OpenServiceW.restype = C.c_void_p
        a.CloseServiceHandle.argtypes = [C.c_void_p]
        a.QueryServiceStatusEx.argtypes = [C.c_void_p, U32, C.c_void_p, U32, C.POINTER(U32)]
        self.ip.GetExtendedTcpTable.argtypes = [C.c_void_p, C.POINTER(U32), C.c_int, U32, C.c_int, U32]
        self.log = a.OpenEventLogW(None, 'Application')
        if not self.log:
            raise C.WinError(C.get_last_error())
        self.evidence = AuthenticationEvidence()
        oldest, latest = self.bounds()
        self.cursor = max(oldest - 1, latest - 512)
        self.process_id = self.server_process_id()
        self.evidence.ingest(self.read_events(), bootstrap=True)

    def close(self):
        if self.log:
            self.advapi.CloseEventLog(self.log)
            self.log = None

    def bounds(self):
        oldest, count = U32(), U32()
        if not self.advapi.GetOldestEventLogRecord(self.log, C.byref(oldest)) or not self.advapi.GetNumberOfEventLogRecords(self.log, C.byref(count)):
            raise C.WinError(C.get_last_error())
        return oldest.value, oldest.value + count.value - 1

    def read_events(self):
        oldest, latest = self.bounds()
        if self.cursor < oldest - 1 or self.cursor > latest:
            self.evidence.peers.clear()
            self.cursor = max(oldest - 1, latest)
        messages = []
        for _ in range(32):  # Bound work even when another application floods its log.
            if self.cursor >= latest:
                break
            buffer = C.create_string_buffer(65536)
            used, required = U32(), U32()
            ok = self.advapi.ReadEventLogW(self.log, 0x6, self.cursor + 1, buffer, len(buffer), C.byref(used), C.byref(required))
            if not ok and C.get_last_error() == 122 and 65536 < required.value <= 1048576:
                buffer = C.create_string_buffer(required.value)
                ok = self.advapi.ReadEventLogW(self.log, 0x6, self.cursor + 1, buffer, len(buffer), C.byref(used), C.byref(required))
            if not ok:
                error = C.get_last_error()
                if error in (38, 87):
                    break
                raise C.WinError(error)
            raw = buffer.raw[:used.value]
            if not raw:
                break
            messages.extend(message for _, message in event_messages(raw))
            offset = 0
            while offset + 56 <= len(raw):
                size, number = struct.unpack_from('<I', raw, offset)[0], struct.unpack_from('<I', raw, offset + 8)[0]
                if size < 60 or offset + size > len(raw):
                    raise RuntimeError('Invalid Windows event record length')
                self.cursor = max(self.cursor, number)
                offset += size
        return messages

    def server_process_id(self):
        manager = self.advapi.OpenSCManagerW(None, None, 1)
        if not manager:
            raise C.WinError(C.get_last_error())
        service = None
        try:
            service = self.advapi.OpenServiceW(manager, 'tvnserver', 4)
            if not service:
                raise C.WinError(C.get_last_error())
            status = (U32 * 9)()
            needed = U32()
            if not self.advapi.QueryServiceStatusEx(service, 0, status, C.sizeof(status), C.byref(needed)):
                raise C.WinError(C.get_last_error())
            return int(status[7]) if status[1] == 4 else 0
        finally:
            if service:
                self.advapi.CloseServiceHandle(service)
            self.advapi.CloseServiceHandle(manager)

    def connected_peers(self, process_id):
        if not process_id:
            return set()
        size = U32()
        result = self.ip.GetExtendedTcpTable(None, C.byref(size), False, 2, 5, 0)
        if result not in (0, 122):
            raise RuntimeError('TCP ownership query failed: %d' % result)
        buffer = C.create_string_buffer(size.value)
        result = self.ip.GetExtendedTcpTable(buffer, C.byref(size), False, 2, 5, 0)
        if result:
            raise RuntimeError('TCP ownership query failed: %d' % result)
        count = struct.unpack_from('<I', buffer.raw)[0]
        if 4 + 24 * count > len(buffer):
            raise RuntimeError('Invalid Windows TCP table')
        peers = set()
        for index in range(count):
            state, local_ip, local_port, remote_ip, remote_port, owner = struct.unpack_from('<6I', buffer.raw, 4 + 24 * index)
            if state == 5 and owner == process_id and socket.ntohs(local_port & 65535) == self.port:
                peers.add(socket.inet_ntoa(struct.pack('<I', remote_ip)))
        return peers

    def sample(self):
        process_id = self.server_process_id()
        if process_id != self.process_id:
            self.evidence.peers.clear()
            self.process_id = process_id
        self.evidence.ingest(self.read_events())
        return self.evidence.active(self.connected_peers(process_id))
