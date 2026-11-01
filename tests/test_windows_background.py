"""Independent worker entry points and redirected AppData path selection."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import ANY, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows'))
import app_paths
import background


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name)

    def save(self, name, value):
        (self.state / name).write_text(json.dumps(value), encoding='utf-8')

    def test_logon_task_does_nothing_when_preference_is_off(self):
        self.save('keyboard-preference.json', {'enabled': False})
        with patch('keyboard_hook.run_keyboard') as worker:
            self.assertEqual(background.run_background(self.state, 'keyboard'), 0)
            worker.assert_not_called()

    def test_keyboard_task_retains_saved_command_option_and_launch_identity(self):
        self.save('keyboard-preference.json', {'enabled': True, 'command_as_control': True})
        self.save('keyboard-launch.json', {'token': 'request-identity'})
        with patch('keyboard_hook.run_keyboard', return_value=0) as worker:
            self.assertEqual(background.run_background(self.state, 'keyboard'), 0)
        worker.assert_called_once_with(self.state, True, launch_token='request-identity')

    def test_logon_can_resume_without_an_interactive_launch_request(self):
        self.save('session-preference.json', {'enabled': True})
        with patch('session_mode.run_automatic', return_value=0) as worker:
            self.assertEqual(background.run_background(self.state, 'session'), 0)
        worker.assert_called_once_with(self.state, launch_token=ANY)
        self.assertTrue(worker.call_args.kwargs['launch_token'])

    def test_unknown_worker_never_launches_a_program(self):
        with self.assertRaises(ValueError):
            background.run_background(self.state, 'other')

    def test_installed_worker_uses_its_own_state_instead_of_scheduler_appdata(self):
        installed = self.state / 'VncDesktopTools' / 'app'
        installed.mkdir(parents=True)
        with patch.object(app_paths, '__file__', str(installed / 'app_paths.py')), patch.dict('os.environ', {'LOCALAPPDATA': str(self.state / 'different-scheduler-view')}):
            self.assertEqual(app_paths.user_root(), app_paths.physical_path(installed).parent)


if __name__ == '__main__':
    unittest.main()
