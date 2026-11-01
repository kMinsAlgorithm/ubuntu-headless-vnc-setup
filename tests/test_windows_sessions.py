"""Session evidence and automatic display restoration; no live display changes."""
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'windows'))
import session_mode as session
import session_observer as observer
import vnc_desktop as app


class AuthenticationTests(unittest.TestCase):
    def test_bare_tcp_connection_never_activates_remote_display(self):
        evidence = observer.AuthenticationEvidence()
        self.assertFalse(evidence.active({'203.0.113.10'}))

    def test_failed_authentication_never_activates_remote_display(self):
        evidence = observer.AuthenticationEvidence()
        evidence.ingest(['Authentication failed from 203.0.113.10'])
        self.assertFalse(evidence.active({'203.0.113.10'}))

    def test_success_requires_matching_live_server_connection(self):
        evidence = observer.AuthenticationEvidence()
        evidence.ingest(['Authentication passed by 203.0.113.10'])
        self.assertTrue(evidence.active({'203.0.113.10'}))
        self.assertFalse(evidence.active(set()))
        self.assertFalse(evidence.active({'203.0.113.10'}))  # New TCP session needs new proof.

    def test_multiple_viewers_keep_mode_until_the_final_proven_peer_leaves(self):
        evidence = observer.AuthenticationEvidence()
        evidence.ingest(['Authentication passed by 203.0.113.10', 'Authentication passed by 203.0.113.11'])
        self.assertTrue(evidence.active({'203.0.113.10', '203.0.113.11'}))
        self.assertTrue(evidence.active({'203.0.113.11'}))
        self.assertFalse(evidence.active(set()))

    def test_unauthenticated_probe_disconnect_does_not_evict_authenticated_peer(self):
        evidence = observer.AuthenticationEvidence()
        evidence.ingest(['Authentication passed by 203.0.113.10'])
        evidence.ingest(['The client 203.0.113.10 #9 has been disconnected for the reason: Connection has been gracefully closed'])
        self.assertTrue(evidence.active({'203.0.113.10'}))

    def test_service_restart_discards_old_evidence(self):
        evidence = observer.AuthenticationEvidence()
        evidence.ingest(['Authentication passed by 203.0.113.10', 'Service has been started successfully'])
        self.assertFalse(evidence.active({'203.0.113.10'}))

    def test_bootstrap_does_not_reuse_disconnected_historical_credentials(self):
        evidence = observer.AuthenticationEvidence()
        evidence.ingest(['Authentication passed by 203.0.113.10', 'The client 203.0.113.10 has disconnected'], bootstrap=True)
        self.assertFalse(evidence.active({'203.0.113.10'}))


class TimingTests(unittest.TestCase):
    def test_no_early_activation_and_short_reconnect_grace(self):
        policy = session.SessionPolicy(grace=4)
        self.assertFalse(policy.remote(False, 100))
        self.assertTrue(policy.remote(True, 101))
        self.assertTrue(policy.remote(False, 104))
        self.assertFalse(policy.remote(False, 105))
        self.assertTrue(policy.remote(True, 106))


class FakeDisplay:
    def __init__(self):
        self.screen = 'physical-layout'
        self.calls = []
        self.failure = False

    def choose(self, **kwargs):
        return {'device': 'VIRTUAL'}

    def target_mode(self, *args):
        pass

    def snapshot(self):
        self.calls.append('snapshot')
        return {'screen': self.screen}

    def apply(self, *args, **kwargs):
        self.screen = 'virtual-only'
        self.calls.append('virtual')
        if self.failure:
            raise RuntimeError('Partial mode change failed')

    def virtual_screen(self):
        return {'width': 1920, 'height': 1080}

    def restore(self, snapshot):
        self.screen = snapshot['screen']
        self.calls.append('restore')


class GuardianTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name)
        self.adapter = FakeDisplay()
        self.events = []

    def run_guard(self, input_text='', recover=False):
        request = self.state / 'request.json'
        app.write_json(request, {'state': str(self.state), 'profile': 'mac', 'recover_only': recover})
        with patch.object(app, 'backend', return_value=self.adapter), patch.object(app, 'emit', side_effect=self.events.append), patch.object(sys, 'stdin', io.StringIO(input_text)):
            return session.session_guard(request)

    def test_parent_eof_restores_exact_original_and_clears_checkpoint(self):
        self.assertEqual(self.run_guard(), 0)
        self.assertEqual(self.adapter.screen, 'physical-layout')
        self.assertEqual(self.adapter.calls, ['snapshot', 'virtual', 'restore'])
        self.assertFalse((self.state / 'session-recovery.json').exists())
        self.assertEqual(self.events[-1]['status'], 'restored')

    def test_heartbeats_then_stop_restore_before_exit(self):
        self.assertEqual(self.run_guard('active\nactive\nrestore\n'), 0)
        self.assertEqual(self.adapter.screen, 'physical-layout')

    def test_partial_switch_failure_restores_and_does_not_report_success(self):
        self.adapter.failure = True
        self.assertEqual(self.run_guard(), 1)
        self.assertEqual(self.adapter.screen, 'physical-layout')
        self.assertEqual(self.events[-1]['status'], 'error')

    def test_failed_restore_keeps_the_original_recovery_copy(self):
        with patch.object(self.adapter, 'restore', side_effect=RuntimeError('Monitor disconnected')):
            self.assertEqual(self.run_guard(), 1)
        self.assertTrue((self.state / 'session-recovery.json').exists())
        self.assertEqual(self.events[-1]['status'], 'restore-pending')

    def test_recovery_reuses_original_backup_instead_of_capturing_virtual_state(self):
        app.write_json(self.state / 'session-recovery.json', {'snapshot': {'screen': 'original-before-crash'}})
        self.adapter.screen = 'virtual-after-crash'
        self.assertEqual(self.run_guard(), 0)
        self.assertEqual(self.adapter.screen, 'original-before-crash')
        self.assertNotIn('snapshot', self.adapter.calls)

    def test_competing_guard_cannot_restore_another_active_session(self):
        app.write_json(self.state / 'session-recovery.json', {'snapshot': {'screen': 'owned-by-other-guard'}})
        with app.operation_lock(self.state / 'session-guard.lock'):
            self.assertEqual(self.run_guard(), 1)
        self.assertEqual(self.adapter.calls, [])

    def test_recovery_only_does_not_switch_to_virtual(self):
        app.write_json(self.state / 'session-recovery.json', {'snapshot': {'screen': 'original-before-crash'}})
        self.assertEqual(self.run_guard(recover=True), 0)
        self.assertEqual(self.adapter.calls, ['restore'])

    def test_manual_topology_changes_are_blocked_during_automatic_mode(self):
        with patch('session_mode.automatic_status', return_value={'running': True}):
            with self.assertRaisesRegex(RuntimeError, 'automatic'):
                app.perform_transaction(self.adapter, {'action': 'restore'}, self.state, self.events.append, lambda _: 'keep')


class EventRecordTests(unittest.TestCase):
    def record(self, source, message):
        names = (source + '\0LOCALHOST\0').encode('utf-16-le')
        text = (message + '\0').encode('utf-16-le')
        start = 56 + len(names)
        size = start + len(text) + 4
        header = bytearray(56)
        struct.pack_into('<I', header, 0, size)
        struct.pack_into('<I', header, 8, 123)
        struct.pack_into('<H', header, 26, 1)
        struct.pack_into('<I', header, 36, start)
        return bytes(header) + names + text + struct.pack('<I', size)

    def test_parser_uses_only_tightvnc_provider(self):
        text = 'Authentication passed by 203.0.113.10'
        self.assertEqual(observer.event_messages(self.record('tvnserver', text)), [(123, text)])
        self.assertEqual(observer.event_messages(self.record('another-app', text)), [])

    def test_truncated_event_record_is_rejected(self):
        with self.assertRaises(RuntimeError):
            observer.event_messages(self.record('tvnserver', 'test')[:-8])


class StaleHeartbeatTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name)
        app.write_json(self.state / 'session-runtime.json',
                       {'running': True, 'pid': 0, 'token': 'owned-worker', 'heartbeat': 0})

    def test_stale_heartbeat_does_not_hide_live_worker_lock(self):
        with app.operation_lock(self.state / 'session-worker.lock'):
            status = session.automatic_status(self.state)
            self.assertFalse(status['running'])
            self.assertTrue(status['worker_active'])
        self.assertFalse(session.automatic_status(self.state)['worker_active'])

    def test_stop_signals_stale_worker_and_waits_before_recovery(self):
        app.write_json(self.state / 'session-recovery.json', {'snapshot': {'screen': 'original'}})
        with patch.object(session, 'worker_active', side_effect=[True, True, False, False]) as active, patch.object(session.time, 'sleep'), patch.object(session, 'launch_guard') as guard, patch.object(session, 'finish_guard', return_value={'status': 'restored'}):
            def recovery(*args, **kwargs):
                self.assertEqual(active.call_count, 3)
                return object(), object()
            guard.side_effect = recovery
            session.stop_automatic(self.state)
        stop = json.loads((self.state / 'session-stop.json').read_text())
        self.assertEqual(stop['token'], 'owned-worker')
        self.assertFalse(json.loads((self.state / 'session-preference.json').read_text())['enabled'])

    def test_stop_timeout_never_starts_competing_recovery(self):
        checkpoint = self.state / 'session-recovery.json'
        app.write_json(checkpoint, {'snapshot': {'screen': 'original'}})
        with patch.object(session, 'worker_active', return_value=True), patch.object(session.time, 'monotonic', side_effect=[0, 0, 26]), patch.object(session.time, 'sleep'), patch.object(session, 'launch_guard') as guard:
            with self.assertRaisesRegex(RuntimeError, 'still restoring'):
                session.stop_automatic(self.state)
            guard.assert_not_called()
        self.assertTrue(checkpoint.exists())


if __name__ == '__main__':
    unittest.main()
