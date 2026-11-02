"""Remote capture shortcuts, including an F12 fallback for character translation."""
from collections import deque

MARKER = 0x564E4354


class CaptureKeys:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.modifiers = set()
        self.held = set()
        self.pending = deque()

    def handle(self, vk, flags, extra):
        if not self.enabled or not flags & 0x10 or extra == MARKER:
            return False
        up = bool(flags & 0x80)
        if vk in (0x10, 0xA0, 0xA1, 0x11, 0xA2, 0xA3, 0x12, 0xA4, 0xA5, 0x5B, 0x5C):
            if up:
                self.modifiers.discard(vk)
            else:
                self.modifiers.add(vk)
            return False
        if vk not in (0x33, 0x34, 0x53, 0x7B):
            return False
        if up:
            if vk in self.held:
                self.held.remove(vk)
                return True
            return False
        if vk in self.held:
            return True
        control = bool(self.modifiers & {0x11, 0xA2, 0xA3})
        shift = bool(self.modifiers & {0x10, 0xA0, 0xA1})
        other = bool(self.modifiers & {0x12, 0xA4, 0xA5, 0x5B, 0x5C})
        if not control or not shift or other:
            return False
        self.held.add(vk)
        if not self.pending:
            self.pending.append('full' if vk == 0x33 else 'region')
        return True

    def take(self):
        # Let the user release the hotkey before showing a selection overlay.
        if self.modifiers or self.held or not self.pending:
            return None
        return self.pending.popleft()
