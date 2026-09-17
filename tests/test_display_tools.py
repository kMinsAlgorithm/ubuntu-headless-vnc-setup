"""Offline regression checks. No display changes, service changes, or real-home writes."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = load('profile_cli_test', 'scripts/display-profile.py')
installer = load('profile_installer_test', 'scripts/install-resolution-switcher.py')
backend = load('profile_backend_test', 'resolution-switcher/resolution_switcher.py')
DISABLED = {'LoadState': 'loaded', 'ActiveState': 'inactive', 'UnitFileState': 'disabled'}


class PolicyTests(unittest.TestCase):
    def test_disabled_and_absent_allowed(self):
        cli.assert_manual_policy(DISABLED)
        cli.assert_manual_policy({'LoadState': 'not-found'})

    def test_active_or_enabled_rejected(self):
        for update in ({'ActiveState': 'active'}, {'ActiveState': 'activating'}, {'UnitFileState': 'enabled'}, {}):
            state = {} if not update else {**DISABLED, **update}
            with self.subTest(state=state), self.assertRaises(RuntimeError):
                cli.assert_manual_policy(state)

    def test_missing_systemd_unit_is_supported(self):
        result = types.SimpleNamespace(returncode=1, stdout='LoadState=not-found\nActiveState=inactive\n', stderr='')
        with patch.object(cli.subprocess, 'run', return_value=result):
            self.assertEqual(cli.adaptive_state()['LoadState'], 'not-found')

    def test_unavailable_systemd_session_is_an_error(self):
        result = types.SimpleNamespace(returncode=1, stdout='', stderr='Failed to connect to bus')
        with patch.object(cli.subprocess, 'run', return_value=result), self.assertRaises(RuntimeError):
            cli.adaptive_state()

    def test_open_chooser_or_missing_bus_rejected(self):
        for code, output in ((0, '(true,)'), (1, '')):
            with self.subTest(code=code), patch.object(cli.subprocess, 'run', return_value=types.SimpleNamespace(returncode=code, stdout=output)), self.assertRaises(RuntimeError):
                cli.assert_chooser_closed()

    def test_profiles_match_accepted_gui(self):
        self.assertEqual(set(cli.PROFILES.values()), {row[0] for row in backend.PROFILES})
        self.assertEqual(cli.PROFILES['ipad'], '1600x1050')
        self.assertTrue(all(backend.PROFILE_SCALES.get(mode, '1') == '1' for mode in cli.PROFILES.values()))


class FakeBackend:
    TIMEOUT = 20

    def __init__(self):
        self.mode = '1920x1080'
        self.scale = '1'
        self.events = []
        self.windows = [{'id': 10, 'geometry': [1400, 800, 800, 680]}]
        self.time = types.SimpleNamespace(sleep=Mock())
        self.guard = types.SimpleNamespace(wait=self.expire)
        self.failure = False
        self.expired = False

    def query(self):
        return {'output': 'TEST-0', 'mode': self.mode, 'framebuffer': self.mode, 'rate': '60.00',
                'modes': {mode: ['59.95', '60.00'] for mode in cli.PROFILES.values()}}

    def vnc_scale(self):
        return self.scale

    def set_vnc_scale(self, scale):
        self.scale = scale

    def ensure_ipad_modes(self):
        return self.query(), []

    def capture_windows(self):
        return list(self.windows)

    def start_guard(self, old, windows=None):
        self.original = old['mode'], self.scale, list(windows)
        self.events.append('guard-ready')
        return self.guard

    def apply_mode(self, output, mode, rate):
        self.events.append('apply')
        self.mode = mode
        if self.failure:
            raise RuntimeError('Simulated partial mode change')

    def fit_windows(self, windows, mode):
        self.windows = [{'id': 10, 'geometry': [0, 27, 800, 680]}]

    def log_event(self, event):
        pass

    def expire(self, **kwargs):
        self.expired = True
        self.mode, self.scale, self.windows = self.original

    def finish_guard(self, guard, keep=False):
        self.events.append('keep' if keep else 'revert')
        if not keep or self.expired:
            self.mode, self.scale, self.windows = self.original
            return {'status': 'reverted'}
        return {'status': 'kept'}


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.module = FakeBackend()
        self.policy = patch.object(cli, 'adaptive_state', return_value=DISABLED)
        self.chooser = patch.object(cli, 'assert_chooser_closed')
        self.policy.start()
        self.chooser.start()
        self.addCleanup(self.policy.stop)
        self.addCleanup(self.chooser.stop)

    def test_keep_prepares_guard_before_applying(self):
        result = cli.apply_profile(self.module, 'ipad', True)
        self.assertEqual(self.module.events, ['guard-ready', 'apply', 'keep'])
        self.assertEqual((result['status'], result['desktop'], result['vnc_scale']), ('kept', '1600x1050', '1'))

    def test_preview_restores_screen_scale_and_windows(self):
        self.module.scale = '3/5'
        windows = list(self.module.windows)
        with patch('builtins.print'):
            result = cli.apply_profile(self.module, 'ipad', False)
        self.assertEqual((result['status'], result['desktop'], result['vnc_scale']), ('reverted', '1920x1080', '3/5'))
        self.assertEqual(self.module.windows, windows)

    def test_partial_failure_rolls_back(self):
        self.module.failure = True
        with self.assertRaisesRegex(RuntimeError, 'partial'):
            cli.apply_profile(self.module, 'ipad', True)
        self.assertEqual(self.module.mode, '1920x1080')
        self.assertEqual(self.module.events[-1], 'revert')

    def test_identical_profile_does_not_mutate(self):
        self.module.mode = '1600x1050'
        result = cli.apply_profile(self.module, 'ipad', True)
        self.assertEqual(result['status'], 'unchanged')
        self.assertEqual(self.module.events, [])

    def test_same_resolution_with_scaled_vnc_is_repaired(self):
        self.module.mode, self.module.scale = '1600x1050', '3/5'
        result = cli.apply_profile(self.module, 'ipad', True)
        self.assertEqual(result['vnc_scale'], '1')
        self.assertEqual(result['status'], 'kept')

    def test_unsupported_profile_does_not_apply(self):
        self.module.ensure_ipad_modes = lambda: (self.module.query(), ['1600x1050'])
        with self.assertRaisesRegex(RuntimeError, 'not supported'):
            cli.apply_profile(self.module, 'ipad', True)
        self.assertEqual(self.module.events, [])

    def test_expired_confirmation_is_not_reported_as_kept(self):
        self.module.expired = True
        with self.assertRaisesRegex(RuntimeError, 'deadline expired'):
            cli.apply_profile(self.module, 'ipad', True)
        self.assertEqual(self.module.mode, '1920x1080')

    def test_enabled_watcher_blocks_before_display_changes(self):
        with patch.object(cli, 'adaptive_state', return_value={**DISABLED, 'UnitFileState': 'enabled'}), self.assertRaises(RuntimeError):
            cli.apply_profile(self.module, 'ipad', True)
        self.assertEqual(self.module.events, [])


class InstallTests(unittest.TestCase):
    def test_install_backup_permissions_and_space_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / 'user home'
            desktop = home / 'custom desktop'
            first = installer.install_files(home, desktop)
            self.assertTrue(all(not row['existed'] for row in first['files']))
            for source, installed in [('resolution-switcher/resolution_switcher.py', 'resolution_switcher.py'),
                                      ('scripts/display-profile.py', 'display_profile.py')]:
                self.assertEqual((ROOT / source).read_bytes(), (home / '.local/share/vnc-resolution-switcher' / installed).read_bytes())
            launcher = desktop / '화면 해상도 선택.desktop'
            self.assertEqual(launcher.stat().st_mode & 0o777, 0o755)
            if shutil.which('desktop-file-validate'):
                subprocess.run(['desktop-file-validate', str(launcher)], check=True, capture_output=True)
            app = home / '.local/share/vnc-resolution-switcher/resolution_switcher.py'
            app.write_text('previous local version\n')
            second = installer.install_files(home, desktop)
            self.assertTrue(all(row['existed'] for row in second['files']))
            record = next(row for row in second['files'] if row['destination'] == str(app))
            self.assertEqual(Path(record['backup']).read_text(), 'previous local version\n')
            saved = json.loads((Path(second['backup_directory']) / 'receipt.json').read_text())
            self.assertEqual(saved['sha256'], second['sha256'])

    def test_destination_symlink_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            app = home / '.local/share/vnc-resolution-switcher'
            app.mkdir(parents=True)
            target = home / 'keep.txt'
            target.write_text('untouched')
            (app / 'resolution_switcher.py').symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, 'symlink'):
                installer.install_files(home, home / 'Desktop')
            self.assertEqual(target.read_text(), 'untouched')

    def test_launcher_control_characters_rejected(self):
        for value in ('/home/a\nb', '/home/a\rb', '/home/a\0b'):
            with self.assertRaises(ValueError):
                installer.desktop_quote(value)


class IndependentGuardTests(unittest.TestCase):
    def test_keep_revert_eof_and_timeout(self):
        # Run the real watchdog in its own process, stubbing only the hardware restore.
        for action in ('keep', 'revert', 'eof', 'timeout'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as tmp:
                marker = Path(tmp) / 'restored.json'
                script = '''import importlib.util, json, pathlib, sys
spec = importlib.util.spec_from_file_location("guard_test", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.restore_state = lambda state: pathlib.Path(sys.argv[2]).write_text(json.dumps(state))
m.log_event = lambda event: None
sys.exit(m.guard_main({"mode": "1920x1080", "vnc_scale": "1"}, 0.2))
'''
                process = subprocess.Popen([sys.executable, '-c', script, str(ROOT / 'resolution-switcher/resolution_switcher.py'), str(marker)],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    self.assertEqual(json.loads(process.stdout.readline())['status'], 'ready')
                    if action == 'timeout':
                        process.wait(timeout=3)
                        stdout, stderr = process.communicate()
                    else:
                        stdout, stderr = process.communicate('' if action == 'eof' else action + '\n', timeout=3)
                    self.assertEqual(process.returncode, 0, stderr)
                    self.assertEqual(json.loads(stdout)['status'], 'kept' if action == 'keep' else 'reverted')
                    self.assertEqual(marker.exists(), action != 'keep')
                    if marker.exists():
                        self.assertEqual(json.loads(marker.read_text())['vnc_scale'], '1')
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()


if __name__ == '__main__':
    unittest.main()
