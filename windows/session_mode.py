"""Authenticated VNC connection -> virtual-only desktop -> prior layout on exit."""
import json
from contextlib import ExitStack
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid


class SessionPolicy:
    def __init__(self, grace=4):
        self.grace = grace
        self.last_active = None

    def remote(self, authenticated, now):
        if authenticated:
            self.last_active = now
        return self.last_active is not None and now - self.last_active < self.grace


def worker_active(state):
    """The process owns this lock even if its status heartbeat has failed."""
    from vnc_desktop import operation_lock
    if not (state / 'session-worker.lock').exists():
        return False
    try:
        with operation_lock(state / 'session-worker.lock'):
            return False
    except RuntimeError:
        return True


def automatic_status(state):
    preference = state / 'session-preference.json'
    runtime = state / 'session-runtime.json'
    saved = json.loads(preference.read_text(encoding='utf-8')) if preference.exists() else {}
    try:
        current = json.loads(runtime.read_text(encoding='utf-8'))
        current['running'] = bool(current.get('running')) and time.time() - current['heartbeat'] < 6
    except (OSError, ValueError, KeyError):
        current = {'running': False, 'phase': 'off'}
    return {**current, 'worker_active': worker_active(state),
            'enabled': bool(saved.get('enabled')), 'profile': saved.get('profile', 'mac'),
            'recovery_pending': (state / 'session-recovery.json').exists()}


def launch(arguments, **streams):
    from vnc_desktop import console_python
    return subprocess.Popen([console_python(), str(Path(__file__).with_name('vnc_desktop.py'))] + arguments,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, **streams)


def start_automatic(state, profile='mac', port=5900):
    from vnc_desktop import write_json, operation_lock, PROFILES
    if os.name != 'nt':
        raise RuntimeError('Automatic VNC display mode requires Windows')
    if profile not in PROFILES or not 1 <= port <= 65535:
        raise ValueError('Invalid automatic VNC display profile or port')
    with operation_lock(state / 'session-launch.lock'):
        current = automatic_status(state)
        if current['running']:
            return current
        if current['worker_active']:
            raise RuntimeError('The automatic observer owns its lock but its heartbeat is stale; use auto off before restarting')
        # Validate the actual driver mode before installing a background policy.
        from win32_backend import WindowsBackend
        adapter = WindowsBackend()
        target = adapter.choose(virtual=True)
        adapter.target_mode(target['device'], *PROFILES[profile])
        write_json(state / 'session-preference.json', {'enabled': True, 'profile': profile, 'port': port})
        child = launch(['auto', 'run'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = automatic_status(state)
            if current['running'] and current.get('pid') == child.pid:
                return current
            if child.poll() is not None:
                raise RuntimeError(current.get('error', 'Automatic display observer did not start'))
            time.sleep(0.05)
        raise RuntimeError('Automatic display observer is still starting; inspect auto status before retrying')


def stop_automatic(state):
    from vnc_desktop import write_json, operation_lock
    with operation_lock(state / 'session-launch.lock'):
        current = automatic_status(state)
        preference = state / 'session-preference.json'
        saved = json.loads(preference.read_text(encoding='utf-8')) if preference.exists() else {}
        write_json(preference, {**saved, 'enabled': False})
        if current['running'] or current['worker_active']:
            if not current.get('token'):
                raise RuntimeError('The automatic observer is starting; retry auto off after its status is available')
            write_json(state / 'session-stop.json', {'token': current['token']})
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if not worker_active(state):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError('Automatic mode is still restoring the display; do not remove its files')
        if (state / 'session-recovery.json').exists():
            child, events = launch_guard(state, recover_only=True)
            result = finish_guard(child, events)
            if result.get('status') != 'restored':
                raise RuntimeError(result.get('error', 'Reconnect the original monitors to finish restoring'))
        return automatic_status(state)


def read_output(process):
    events = queue.Queue()

    def read():
        try:
            for line in process.stdout:
                events.put(json.loads(line))
        finally:
            events.put(None)
    threading.Thread(target=read, daemon=True).start()
    return events


def launch_guard(state, profile='mac', recover_only=False):
    from vnc_desktop import write_json
    path = state / ('session-request-' + uuid.uuid4().hex + '.json')
    write_json(path, {'state': str(state), 'profile': profile, 'recover_only': recover_only})
    process = launch(['_session-guard', str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, text=True, encoding='utf-8')
    return process, read_output(process)


def finish_guard(process, events, restore=True):
    if restore and process.poll() is None:
        try:
            process.stdin.write('restore\n')
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
    process.stdin.close()
    process.wait(timeout=22)
    result = {}
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        try:
            event = events.get(timeout=0.1)
        except queue.Empty:
            continue
        if event is None:
            break
        result = event
    if not result:
        result = {'status': 'error', 'error': 'Display guard exited without a restoration result'}
    process.stdout.close()
    process.stderr.close()
    return result


def restore_checkpoint(adapter, state):
    from vnc_desktop import operation_lock
    checkpoint = state / 'session-recovery.json'
    if not checkpoint.exists():
        return
    saved = json.loads(checkpoint.read_text(encoding='utf-8'))
    deadline = time.monotonic() + 15
    while True:
        try:
            with operation_lock(state / 'display-operation.lock'):
                adapter.restore(saved['snapshot'])
                checkpoint.unlink()
                return
        except RuntimeError as error:
            if 'already running' not in str(error) or time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


def session_guard(path):
    from vnc_desktop import write_json, operation_lock, backend, PROFILES, emit
    request = json.loads(path.read_text(encoding='utf-8'))
    path.unlink()
    state = Path(request['state'])
    checkpoint = state / 'session-recovery.json'
    adapter = backend()
    incoming = queue.Queue()

    def read():
        import sys
        try:
            for line in sys.stdin:
                incoming.put(line.strip())
        finally:
            incoming.put('restore')
    threading.Thread(target=read, daemon=True).start()
    # Keep ownership through error recovery as well as the normal connection.
    with ExitStack() as ownership:
        owns_guard = False
        try:
            ownership.enter_context(operation_lock(state / 'session-guard.lock'))
            owns_guard = True
            if not request['recover_only']:
                with operation_lock(state / 'display-operation.lock'):
                    target = adapter.choose(virtual=True)
                    width, height = PROFILES[request['profile']]
                    adapter.target_mode(target['device'], width, height)
                    # Preserve an unfinished original backup after a crash or cable removal.
                    if not checkpoint.exists():
                        write_json(checkpoint, {'snapshot': adapter.snapshot()})
                    adapter.apply(target['device'], width, height, headless=True)
                emit({'status': 'virtual', 'virtual_screen': adapter.virtual_screen()})
                while True:
                    try:
                        message = incoming.get(timeout=8)
                    except queue.Empty:
                        break  # Parent stopped reporting: restore independently.
                    if message != 'active':
                        break
            restore_checkpoint(adapter, state)
            emit({'status': 'restored'})
            return 0
        except Exception as error:
            if not owns_guard:
                emit({'status': 'error', 'error': str(error)})
                return 1
            # Even a partial mode change must be undone before reporting failure.
            try:
                restore_checkpoint(adapter, state)
            except Exception as restore_error:
                emit({'status': 'restore-pending', 'error': str(restore_error)})
                return 1
            emit({'status': 'error', 'error': str(error)})
            return 1


def run_automatic(state):
    from vnc_desktop import write_json, operation_lock
    from session_observer import WindowsSessionObserver
    preference = state / 'session-preference.json'
    saved = json.loads(preference.read_text(encoding='utf-8'))
    token = uuid.uuid4().hex
    runtime = {'running': True, 'pid': os.getpid(), 'token': token, 'phase': 'observing'}
    heartbeat_stop = threading.Event()
    child, events, observer = None, None, None
    last_retry = 0
    policy = SessionPolicy()

    def heartbeat():
        while not heartbeat_stop.is_set():
            try:
                write_json(state / 'session-runtime.json', {**runtime, 'heartbeat': time.time()})
            except OSError:
                # A longer sharing violation must not permanently kill this
                # thread while the display supervisor continues to run.
                pass
            heartbeat_stop.wait(1)

    with operation_lock(state / 'session-worker.lock'):
        try:
            observer = WindowsSessionObserver(saved.get('port', 5900))
            beat = threading.Thread(target=heartbeat, daemon=True)
            beat.start()
            while True:
                stop = state / 'session-stop.json'
                if stop.exists() and json.loads(stop.read_text(encoding='utf-8')).get('token') == token:
                    break
                want_remote = policy.remote(observer.sample(), time.monotonic())
                if child is not None and (child.poll() is not None or not want_remote):
                    runtime['phase'] = 'restoring'
                    result = finish_guard(child, events)
                    child = None
                    runtime['phase'] = 'observing' if result.get('status') == 'restored' else 'restore-pending'
                    if result.get('error'):
                        runtime['error'] = result['error']
                    last_retry = time.monotonic()
                if want_remote and child is None:
                    child, events = launch_guard(state, saved.get('profile', 'mac'))
                    first = events.get(timeout=12)
                    if not first or first.get('status') != 'virtual':
                        result = finish_guard(child, events)
                        child = None
                        raise RuntimeError((first or result).get('error', 'Virtual display could not be activated'))
                    runtime['phase'] = 'virtual'
                    runtime.pop('error', None)
                if child is not None:
                    child.stdin.write('active\n')
                    child.stdin.flush()
                elif not want_remote and (state / 'session-recovery.json').exists() and time.monotonic() - last_retry >= 5:
                    recovery, recovery_events = launch_guard(state, recover_only=True)
                    result = finish_guard(recovery, recovery_events)
                    runtime['phase'] = 'observing' if result.get('status') == 'restored' else 'restore-pending'
                    last_retry = time.monotonic()
                time.sleep(0.7)
        except Exception as error:
            runtime['phase'] = 'error'
            runtime['error'] = str(error)
        finally:
            if child is not None:
                try:
                    result = finish_guard(child, events)
                    if result.get('status') != 'restored':
                        runtime['phase'] = 'restore-pending'
                        runtime['error'] = result.get('error', 'Original display restoration is pending')
                except Exception as error:
                    runtime['phase'] = 'restore-pending'
                    runtime['error'] = str(error)
            if observer is not None:
                observer.close()
            runtime['running'] = False
            heartbeat_stop.set()
            if 'beat' in locals():
                beat.join(timeout=2)
            write_json(state / 'session-runtime.json', {**runtime, 'heartbeat': time.time()})
    return 1 if runtime['phase'] in ('error', 'restore-pending') else 0
