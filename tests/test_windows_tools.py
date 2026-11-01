"""Windows transactions and injected-key policies; never change the live desktop."""
import copy
import importlib.util
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'windows'))
import vnc_desktop as app
from keyboard_hook import KeyboardMapper, MARKER
from win32_backend import DevMode, WindowsBackend, pack, unpack
from unittest.mock import Mock


class FakeDisplay:
    def __init__(self):
        self.current = {'device': 'DISPLAY1', 'active': True, 'virtual': True,
                        'width': 1920, 'height': 1080}
        self.events = []
        self.partial_failure = False
        self.restore_failure = False

    def choose(self, device=None, virtual=False):
        return dict(self.current)

    def target_mode(self, device, width, height):
        self.events.append('test')
        if width == 1184:
            raise RuntimeError('Unsupported display mode')

    def snapshot(self):
        self.events.append('snapshot')
        return copy.deepcopy(self.current)

    def apply(self, device, width, height, headless=False):
        self.events.append('apply')
        self.current.update(width=width, height=height, headless=headless)
        if self.partial_failure:
            raise RuntimeError('Driver rejected a partial change')

    def restore(self, snapshot):
        self.events.append('restore')
        if self.restore_failure:
            raise RuntimeError('Monitor was disconnected')
        self.current = copy.deepcopy(snapshot)

    def virtual_screen(self):
        return {key: self.current[key] for key in ('width', 'height')}


class DisplayTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.adapter = FakeDisplay()
        self.original = dict(self.adapter.current)
        self.request = {'action': 'apply', 'profile': 'ipad', 'timeout': 20}
        self.events = []

    def run_transaction(self, decision='keep', clock=lambda: 0):
        return app.perform_transaction(self.adapter, self.request, self.state, self.events.append,
                                       lambda timeout: decision, clock=clock)

    def test_keep_checks_driver_before_mutation_and_retains_original(self):
        result = self.run_transaction()
        self.assertEqual(result['status'], 'kept')
        self.assertEqual(self.adapter.current['width'], 1600)
        self.assertEqual(self.adapter.events[:3], ['test', 'snapshot', 'apply'])
        self.assertEqual(json.loads((self.state / 'original-display.json').read_text()), self.original)

    def test_cancel_timeout_and_parent_eof_restore_exact_snapshot(self):
        for decision in ('revert', '', 'unknown'):
            with self.subTest(decision=decision):
                result = self.run_transaction(decision)
                self.assertEqual(result['status'], 'reverted')
                self.assertEqual(self.adapter.current, self.original)

    def test_late_confirmation_is_not_kept(self):
        times = iter((0, 21))
        result = self.run_transaction(clock=lambda: next(times))
        self.assertEqual(result['status'], 'reverted')

    def test_same_mode_does_not_write_state_or_change_windows(self):
        self.request['profile'] = 'mac'
        self.assertEqual(self.run_transaction()['status'], 'unchanged')
        self.assertEqual(self.adapter.events, [])
        self.assertEqual(list(self.state.iterdir()), [])

    def test_unsupported_mode_does_not_capture_or_mutate(self):
        self.request['profile'] = 'ipad-landscape'
        with self.assertRaisesRegex(RuntimeError, 'Unsupported'):
            self.run_transaction()
        self.assertEqual(self.adapter.current, self.original)
        self.assertEqual(self.adapter.events, ['test'])

    def test_partial_failure_rolls_back(self):
        self.adapter.partial_failure = True
        with self.assertRaisesRegex(RuntimeError, 'partial'):
            self.run_transaction()
        self.assertEqual(self.adapter.current, self.original)

    def test_failed_rollback_reports_backup_instead_of_success(self):
        self.adapter.partial_failure = self.adapter.restore_failure = True
        with self.assertRaisesRegex(RuntimeError, 'rollback needs attention'):
            self.run_transaction()
        self.assertTrue((self.state / 'last-transaction.json').exists())

    def test_headless_rejects_physical_output_before_mutation(self):
        self.request['action'] = 'headless'
        self.adapter.current['virtual'] = False
        with self.assertRaisesRegex(RuntimeError, 'virtual display'):
            self.run_transaction()
        self.assertNotIn('apply', self.adapter.events)

    def test_inactive_display_requires_explicit_headless_action(self):
        self.adapter.current['active'] = False
        with self.assertRaisesRegex(RuntimeError, 'inactive'):
            self.run_transaction()

    def test_headless_uses_guard_and_restores_on_disconnect(self):
        self.request['action'] = 'headless'
        self.assertEqual(self.run_transaction('')['status'], 'reverted')
        self.assertEqual(self.adapter.current, self.original)

    def test_original_backup_survives_multiple_profile_changes(self):
        self.run_transaction()
        self.request['profile'] = 'ipad-large-text'
        self.run_transaction()
        self.assertEqual(json.loads((self.state / 'original-display.json').read_text()), self.original)

    def test_restore_can_be_previewed_and_cancelled(self):
        self.run_transaction()
        current = copy.deepcopy(self.adapter.current)
        self.request['action'] = 'restore'
        self.assertEqual(self.run_transaction('revert')['status'], 'reverted')
        self.assertEqual(self.adapter.current, current)

    def test_second_process_cannot_take_active_operation_lock(self):
        lock = self.state / 'operation.lock'
        command = [sys.executable, '-c',
                   'import sys; sys.path.insert(0, sys.argv[1]); import vnc_desktop as a; '
                   'from pathlib import Path; '\
                   '\nwith a.operation_lock(Path(sys.argv[2])): print("unexpected")',
                   str(ROOT / 'windows'), str(lock)]
        with app.operation_lock(lock):
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('unexpected\n', result.stdout)


class KeyboardPolicyTests(unittest.TestCase):
    def setUp(self):
        self.mapper = KeyboardMapper()
        self.sent = []

    def send(self, vk, up):
        self.sent.append((vk, up))
        return True

    def test_physical_caps_and_unrelated_injected_keys_are_untouched(self):
        self.assertFalse(self.mapper.handle(0x14, 0, 0, self.send))
        self.assertFalse(self.mapper.handle(0x41, 0x10, 0, self.send))
        self.assertEqual(self.sent, [])

    def test_injected_caps_pair_toggles_once_and_suppresses_repeat(self):
        for flags in (0x10, 0x10, 0x90):
            self.assertTrue(self.mapper.handle(0x14, flags, 0, self.send))
        self.assertEqual(self.sent, [(0x15, False), (0x15, True)])

    def test_own_injected_events_do_not_recurse(self):
        self.assertFalse(self.mapper.handle(0x14, 0x10, MARKER, self.send))

    def test_windows_blocked_injection_keeps_original_key(self):
        self.assertFalse(self.mapper.handle(0x14, 0x10, 0, lambda vk, up: False))
        self.assertEqual(self.mapper.held, {})

    def test_stop_releases_replacement_modifiers(self):
        mapper = KeyboardMapper(True)
        mapper.handle(0xA4, 0x10, 0, self.send)
        mapper.release(self.send)
        self.assertEqual(self.sent, [(0xA2, False), (0xA2, True)])
        self.assertEqual(mapper.held, {})

    def test_command_conversion_is_opt_in_and_preserves_altgr(self):
        self.assertFalse(self.mapper.handle(0xA4, 0x10, 0, self.send))
        self.assertFalse(KeyboardMapper(True).handle(0xA5, 0x10, 0, self.send))


class PackageContractTests(unittest.TestCase):
    def test_virtual_driver_modes_match_profiles_without_changing_approved_values(self):
        import xml.etree.ElementTree as ET
        config = ET.parse(ROOT / 'windows/vdd_settings.xml')
        modes = {(int(item.findtext('width')), int(item.findtext('height')))
                 for item in config.findall('.//resolution')}
        self.assertEqual(modes, set(app.PROFILES.values()))
        self.assertEqual(app.PROFILES['ipad'], (1600, 1050))

    def test_packages_are_pinned_to_https_and_sha256(self):
        manifest = json.loads((ROOT / 'windows/packages.json').read_text())
        for package in manifest.values():
            self.assertTrue(package['url'].startswith('https://'))
            self.assertRegex(package['sha256'], r'^[a-f0-9]{64}$')

    def test_native_mode_snapshot_is_lossless(self):
        value = DevMode()
        value.size = 156
        value.width, value.height, value.frequency = 3440, 1440, 100
        restored = unpack(DevMode, pack(value))
        self.assertEqual(bytes(value), bytes(restored))


class NativeTopologyRecoveryTests(unittest.TestCase):
    def test_reenables_disabled_adapter_before_modes_and_skips_unused_connectors(self):
        adapter = WindowsBackend.__new__(WindowsBackend)
        physical = dict(device='physical', active=True, primary=True, width=1920, height=1080,
                        x=0, y=0, orientation=0, frequency=60)
        unused = dict(physical, device='unused', active=False, primary=False, width=0, height=0)
        mode = DevMode()
        mode.width, mode.height, mode.frequency = 1920, 1080, 60
        snapshot = {'displays': [{**physical, 'mode': pack(mode)}, {**unused, 'mode': pack(mode)}], 'windows': []}
        calls = []
        adapter.devices = Mock(side_effect=[[dict(physical, active=False), unused],
                                           [physical, unused], [physical, unused]])
        adapter.api = Mock()
        adapter.api.SetDisplayConfig.side_effect = lambda *args: calls.append('enable-topology') or 0
        adapter._change = lambda device, mode, flags=0: calls.append(device or 'apply-topology')
        adapter.restore(snapshot)
        self.assertEqual(calls, ['enable-topology', 'physical', 'apply-topology'])

    def test_topology_failure_is_reported_without_attempting_legacy_changes(self):
        adapter = WindowsBackend.__new__(WindowsBackend)
        adapter.devices = lambda: [{'device': 'physical', 'active': False}]
        adapter.api = Mock()
        adapter.api.SetDisplayConfig.return_value = 5
        adapter._change = Mock()
        with self.assertRaisesRegex(RuntimeError, 're-enable'):
            adapter.restore({'displays': [{'device': 'physical', 'active': True}], 'windows': []})
        adapter._change.assert_not_called()


if __name__ == '__main__':
    unittest.main()
