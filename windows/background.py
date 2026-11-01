"""Launch persistent workers through the user's interactive scheduled tasks."""
import json
import os
from pathlib import Path
import subprocess
import uuid


def launch_background(state, kind):
    from vnc_desktop import write_json
    if kind not in ('keyboard', 'session'):
        raise ValueError('Unknown background worker')
    helper = state.parent / 'app' / 'background-tasks.ps1'
    if not helper.is_file():
        raise RuntimeError('Install the Windows tools before enabling a background mode')
    token = uuid.uuid4().hex
    write_json(state / (kind + '-launch.json'), {'token': token})
    powershell = Path(os.environ['SystemRoot']) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-File', str(helper), '-Action', 'Start', '-AppDirectory', str(helper.parent),
                             '-Kind', kind], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                            timeout=20)
    if result.returncode:
        raise RuntimeError('Could not start the independent Windows task; reinstall the user tools')
    return token


def run_background(state, kind):
    if kind not in ('keyboard', 'session'):
        raise ValueError('Unknown background worker')
    preference = state / (kind + '-preference.json')
    saved = json.loads(preference.read_text(encoding='utf-8')) if preference.exists() else {}
    if not saved.get('enabled'):
        return 0
    request = state / (kind + '-launch.json')
    token = (json.loads(request.read_text(encoding='utf-8')).get('token') if request.exists() else None) or uuid.uuid4().hex
    if kind == 'keyboard':
        from keyboard_hook import run_keyboard
        return run_keyboard(state, saved.get('command_as_control', False), launch_token=token)
    from session_mode import run_automatic
    return run_automatic(state, launch_token=token)
