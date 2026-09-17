"""Settings transaction tests; no live keyboard or home-directory changes."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('keyboard_mode_test', Path(__file__).resolve().parents[1] / 'keyboard-mode/keyboard_mode.py')
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)


class FakeBackend:
    def __init__(self):
        self.current_ime = {'value': 'Hangul,Super_R,Alt_L', 'user': None}
        self.current_vnc = {'identity': 'boot:10:20', 'remap': 'F8-F9', 'skip_lockkeys': '1'}
        self.caps = True
        self.fail_once = False

    def ime(self):
        return dict(self.current_ime)

    def vnc(self):
        return dict(self.current_vnc)

    def set_ime(self, value):
        self.current_ime = dict(value)
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError('simulated settings failure')

    def set_vnc(self, value):
        self.current_vnc = dict(value)

    def clear_caps(self):
        self.caps = False


class KeyboardModeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        for name, value in [('STATE_DIR', self.folder), ('STATE_FILE', self.folder / 'state.json')]:
            override = patch.object(k, name, value)
            override.start()
            self.addCleanup(override.stop)
        self.backend = FakeBackend()

    def test_enable_disable_restores_exact_user_unset_state_and_other_remaps(self):
        ime, vnc = self.backend.ime(), self.backend.vnc()
        k.enable_mode(self.backend)
        self.assertEqual(self.backend.current_ime, k.TARGET_IME)
        self.assertEqual(self.backend.current_vnc['remap'], 'F8-F9,Caps_Lock-Hangul')
        self.assertEqual(self.backend.current_vnc['skip_lockkeys'], '0')
        self.assertFalse(self.backend.caps)
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.ime(), ime)
        self.assertEqual(self.backend.vnc(), vnc)
        self.assertFalse(k.load_state()['enabled'])

    def test_repeated_enable_preserves_original_baseline(self):
        before = self.backend.ime(), self.backend.vnc()
        k.enable_mode(self.backend)
        k.enable_mode(self.backend)
        k.disable_mode(self.backend)
        self.assertEqual((self.backend.ime(), self.backend.vnc()), before)
        self.assertEqual(len(list(self.folder.glob('backup-*.json'))), 1)

    def test_partial_enable_failure_rolls_back(self):
        before = self.backend.ime(), self.backend.vnc()
        self.backend.fail_once = True
        with self.assertRaisesRegex(RuntimeError, 'simulated'):
            k.enable_mode(self.backend)
        self.assertEqual((self.backend.ime(), self.backend.vnc()), before)
        self.assertFalse(k.load_state()['enabled'])

    def test_external_ime_edit_is_not_overwritten_on_enable_or_disable(self):
        k.enable_mode(self.backend)
        self.backend.current_ime = {'value': 'F12', 'user': 'F12'}
        for operation in (k.enable_mode, k.disable_mode):
            with self.assertRaisesRegex(RuntimeError, '외부'):
                operation(self.backend)
            self.assertEqual(self.backend.current_ime['value'], 'F12')

    def test_external_vnc_edit_is_not_overwritten(self):
        k.enable_mode(self.backend)
        self.backend.current_vnc['remap'] = 'F10-F11'
        with self.assertRaisesRegex(RuntimeError, '외부'):
            k.disable_mode(self.backend)
        self.assertEqual(self.backend.current_vnc['remap'], 'F10-F11')

    def test_new_server_gets_its_own_restore_baseline(self):
        old_ime = self.backend.ime()
        k.enable_mode(self.backend)
        self.backend.current_vnc = {'identity': 'newboot:12:30', 'remap': 'F2-F3', 'skip_lockkeys': '0'}
        new_vnc = self.backend.vnc()
        k.enable_mode(self.backend)
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.vnc(), new_vnc)
        self.assertEqual(self.backend.ime(), old_ime)

    def test_off_does_not_restore_options_into_an_unmanaged_new_server(self):
        k.enable_mode(self.backend)
        self.backend.current_vnc = {'identity': 'newboot:12:30', 'remap': 'F2-F3', 'skip_lockkeys': '0'}
        expected = self.backend.vnc()
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.vnc(), expected)

    def test_remap_files_are_rejected_before_mutation(self):
        before = self.backend.ime()
        self.backend.current_vnc['remap'] = '/private/custom-remap'
        with self.assertRaisesRegex(RuntimeError, '특수 형식'):
            k.enable_mode(self.backend)
        self.assertEqual(self.backend.ime(), before)
        self.assertIsNone(k.load_state())

    def test_conflicting_caps_mapping_is_restored(self):
        self.backend.current_vnc['remap'] = 'Caps_Lock-Escape,F8-F9'
        k.enable_mode(self.backend)
        self.assertEqual(self.backend.current_vnc['remap'], 'F8-F9,Caps_Lock-Hangul')
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.current_vnc['remap'], 'Caps_Lock-Escape,F8-F9')

    def test_backup_is_private(self):
        k.enable_mode(self.backend)
        for path in self.folder.glob('*.json'):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
