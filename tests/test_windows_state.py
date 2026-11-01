"""Status replacement must preserve complete state through Windows read races."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows'))
import vnc_desktop as app


class StatusWriteTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing semantics')
    def test_real_windows_reader_can_close_during_status_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'runtime.json'
            app.write_json(path, {'generation': 1})
            probe = Path(folder) / 'probe.json'
            probe.write_text('{}')
            reader = path.open('rb')
            try:
                with self.assertRaises(PermissionError):
                    os.replace(probe, path)
                release = threading.Timer(0.15, reader.close)
                release.start()
                try:
                    app.write_json(path, {'generation': 2})
                finally:
                    release.join(timeout=2)
                self.assertEqual(json.loads(path.read_text()), {'generation': 2})
            finally:
                reader.close()

    def test_temporary_reader_sharing_violation_retries_atomic_replace(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'runtime.json'
            app.write_json(path, {'generation': 1})
            replace = os.replace
            attempts = []

            def temporary_denial(source, destination):
                attempts.append(None)
                if len(attempts) < 3:
                    self.assertEqual(json.loads(path.read_text()), {'generation': 1})
                    raise PermissionError('Reader temporarily denies replacement')
                return replace(source, destination)

            with patch.object(app.os, 'replace', side_effect=temporary_denial), patch.object(app.time, 'sleep'):
                app.write_json(path, {'generation': 2})
            self.assertEqual(json.loads(path.read_text()), {'generation': 2})
            self.assertEqual(len(attempts), 3)
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])

    def test_persistent_denial_preserves_old_state_and_has_bounded_retries(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'runtime.json'
            app.write_json(path, {'generation': 1})
            with patch.object(app.os, 'replace', side_effect=PermissionError('Denied')) as replace, patch.object(app.time, 'sleep'):
                with self.assertRaises(PermissionError):
                    app.write_json(path, {'generation': 2})
            self.assertEqual(replace.call_count, 11)
            self.assertEqual(json.loads(path.read_text()), {'generation': 1})
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
