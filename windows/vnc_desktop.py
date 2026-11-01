"""Windows VNC display profiles, guarded headless mode, and desktop chooser."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

PROFILES = {'mac': (1920, 1080), 'ipad': (1600, 1050),
            'ipad-landscape': (1184, 824), 'ipad-large-text': (1024, 768)}
STATE = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'VncDesktopTools' / 'state'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def operation_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError('Another display or keyboard operation is already running')
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RuntimeError('Another display or keyboard operation is already running')
        yield


def backend():
    from win32_backend import WindowsBackend
    return WindowsBackend()


def perform_transaction(adapter, request, state, emit, decide, clock=time.monotonic):
    """The guard owns every display mutation and rolls back before releasing its lock."""
    action = request['action']
    target = None
    if action != 'restore':
        target = adapter.choose(request.get('display'), virtual=(action == 'headless'))
        width, height = PROFILES[request['profile']]
        if action == 'apply' and target['active'] and (target['width'], target['height']) == (width, height):
            result = {'status': 'unchanged', 'display': target['device']}
            emit(result)
            return result
        if action == 'headless' and not target['virtual']:
            raise RuntimeError('Headless mode requires the signed virtual display, not a physical display')
        if action == 'apply' and not target['active']:
            raise RuntimeError('This display is inactive; activate the virtual display with headless mode first')
        adapter.target_mode(target['device'], width, height)
    original_path = state / 'original-display.json'
    restore_target = json.loads(original_path.read_text(encoding='utf-8')) if action == 'restore' else None
    snapshot = adapter.snapshot()
    # Keep a recovery copy on disk before the first Windows API mutation.
    write_json(state / 'last-transaction.json', snapshot)
    if action != 'restore' and not original_path.exists():
        write_json(original_path, snapshot)
    try:
        if action == 'restore':
            adapter.restore(restore_target)
        else:
            adapter.apply(target['device'], width, height, headless=(action == 'headless'))
        deadline = clock() + request['timeout']
        emit({'status': 'preview', 'action': action, 'timeout': request['timeout'],
              'virtual_screen': adapter.virtual_screen()})
        decision = decide(request['timeout'])
        if decision == 'keep' and clock() < deadline:
            return {'status': 'kept', 'action': action, 'virtual_screen': adapter.virtual_screen()}
        adapter.restore(snapshot)
        return {'status': 'reverted', 'reason': 'cancelled, disconnected, or timed out'}
    except BaseException:
        try:
            adapter.restore(snapshot)
        except Exception as restore_error:
            raise RuntimeError('Display operation failed and rollback needs attention: %s; backup: %s' %
                               (restore_error, state / 'last-transaction.json'))
        raise


def emit(value):
    try:
        print(json.dumps(value, ensure_ascii=True), flush=True)
    except BrokenPipeError:
        # A vanished GUI/CLI must not turn a completed rollback into an error.
        pass


def read_decision(timeout):
    messages = queue.Queue()

    def read():
        try:
            messages.put(sys.stdin.readline().strip())  # EOF also triggers rollback.
        except (OSError, ValueError):
            messages.put('revert')

    threading.Thread(target=read, daemon=True).start()
    try:
        return messages.get(timeout=timeout)
    except queue.Empty:
        return 'revert'


def guard(request_path):
    request = json.loads(request_path.read_text(encoding='utf-8'))
    request_path.unlink()
    state = Path(request.pop('state'))
    try:
        with operation_lock(state / 'display-operation.lock'):
            result = perform_transaction(backend(), request, state, emit, read_decision)
        write_json(state / 'last-result.json', result)
        if result['status'] != 'unchanged':
            emit(result)
        return 0
    except Exception as error:
        result = {'status': 'error', 'error': str(error)}
        write_json(state / 'last-result.json', result)
        emit(result)
        return 1


def console_python():
    executable = Path(sys.executable)
    if executable.name.lower() == 'pythonw.exe':
        executable = executable.with_name('python.exe')
    return str(executable)


def start_guard(request):
    STATE.mkdir(parents=True, exist_ok=True)
    request_path = STATE / ('request-' + uuid.uuid4().hex + '.json')
    write_json(request_path, {**request, 'state': str(STATE)})
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        return subprocess.Popen([console_python(), str(Path(__file__).resolve()), '_guard', str(request_path)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding='utf-8', creationflags=flags)
    except Exception:
        request_path.unlink()
        raise


def apply_cli(request, keep=False):
    process = start_guard(request)
    try:
        while True:
            line = process.stdout.readline()
            if not line:
                break
            result = json.loads(line)
            emit(result)
            if result['status'] == 'preview' and keep:
                process.stdin.write('keep\n')
                process.stdin.flush()
        code = process.wait(timeout=15)
        if code and process.stderr:
            detail = process.stderr.read().strip()
            if detail:
                print(detail, file=sys.stderr)
        return code
    finally:
        process.stdin.close()  # Ctrl+C/parent exit: guard receives EOF and restores.


def profiles(adapter=None, device=None):
    supported = None
    if adapter is not None:
        virtual_displays = [d for d in adapter.devices() if d['virtual']]
        try:
            selected = adapter.choose(device, virtual=(device is None and len(virtual_displays) == 1))
            supported = {(int(mode.width), int(mode.height)) for mode in adapter.modes(selected['device'])}
        except RuntimeError:
            if device is not None:
                raise
    return {key: {'width': value[0], 'height': value[1],
                  'supported': None if supported is None else value in supported}
            for key, value in PROFILES.items()}


def status():
    adapter = backend()
    from keyboard_hook import keyboard_status
    return {'displays': adapter.devices(), 'virtual_screen': adapter.virtual_screen(),
            'profiles': profiles(adapter), 'keyboard': keyboard_status(STATE),
            'recovery_available': (STATE / 'original-display.json').exists()}


def gui():
    import tkinter as tk
    from tkinter import messagebox, ttk
    from keyboard_hook import keyboard_status, start_keyboard, stop_keyboard
    root = tk.Tk()
    root.title('VNC 화면 · 키보드')
    root.geometry('620x470')
    root.minsize(570, 440)
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='VNC 화면 선택', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
    adapter = backend()
    devices = adapter.devices()
    labels = [d['device'] + ' · ' + d['description'] for d in devices]
    selected = tk.StringVar(value=next((label for label, d in zip(labels, devices) if d['virtual']), labels[0] if labels else ''))
    ttk.Combobox(frame, textvariable=selected, values=labels, state='readonly').pack(fill='x', pady=(12, 8))
    choices = [key + ' · %d × %d' % value for key, value in PROFILES.items()]
    profile = tk.StringVar(value=choices[0])
    ttk.Combobox(frame, textvariable=profile, values=choices, state='readonly').pack(fill='x')
    ttk.Label(frame, text='드라이버가 제공하는 해상도만 적용합니다. 미확인 시 20초 뒤 복구합니다.\n헤드리스 모드는 가상 화면만 켜므로 물리 모니터는 꺼집니다.', wraplength=560).pack(anchor='w', pady=10)
    message = tk.StringVar(value='준비됨 · 현재 화면은 유지됩니다.')
    buttons = ttk.Frame(frame)
    buttons.pack(fill='x', pady=5)

    def operate(action):
        try:
            device = selected.get().split(' · ')[0]
            request = {'action': action, 'display': device, 'profile': profile.get().split(' · ')[0], 'timeout': 20}
            process = start_guard(request)
            events = queue.Queue()

            def read():
                try:
                    for line in process.stdout:
                        events.put(json.loads(line))
                finally:
                    events.put(None)

            threading.Thread(target=read, daemon=True).start()
            for button in buttons.winfo_children():
                button.configure(state='disabled')
            confirmation = [None]

            def confirm(result):
                window = tk.Toplevel(root)
                confirmation[0] = window
                window.title('이 화면을 유지할까요?')
                window.attributes('-topmost', True)
                deadline = time.monotonic() + result['timeout']
                text = tk.StringVar()
                ttk.Label(window, textvariable=text, padding=20).pack()

                def choose(value):
                    try:
                        process.stdin.write(value + '\n')
                        process.stdin.flush()
                    except (BrokenPipeError, OSError):
                        pass
                    window.destroy()
                    confirmation[0] = None

                ttk.Button(window, text='이 화면 유지', command=lambda: choose('keep')).pack(side='left', padx=20, pady=15)
                ttk.Button(window, text='이전 화면 복구', command=lambda: choose('revert')).pack(side='right', padx=20, pady=15)
                window.protocol('WM_DELETE_WINDOW', lambda: choose('revert'))

                def tick():
                    remaining = max(0, int(deadline - time.monotonic()))
                    text.set('확인하지 않으면 %d초 뒤 이전 화면으로 복구합니다.' % remaining)
                    if remaining > 0 and window.winfo_exists():
                        window.after(250, tick)
                tick()

            def poll():
                try:
                    event = events.get_nowait()
                except queue.Empty:
                    root.after(80, poll)
                    return
                if event is None:
                    if confirmation[0] is not None:
                        confirmation[0].destroy()
                    process.stdin.close()
                    for button in buttons.winfo_children():
                        button.configure(state='normal')
                    return
                message.set({'preview': '미리보기 중', 'kept': '선택한 화면을 유지합니다.',
                             'reverted': '이전 화면으로 복구했습니다.', 'unchanged': '이미 같은 해상도입니다.'}.get(event['status'], event.get('error', '완료')))
                if event['status'] == 'preview':
                    confirm(event)
                root.after(80, poll)
            poll()
        except Exception as error:
            messagebox.showerror('VNC 도구', str(error))

    ttk.Button(buttons, text='선택한 화면 해상도', command=lambda: operate('apply')).pack(side='left', padx=(0, 6))
    ttk.Button(buttons, text='가상 화면만 사용', command=lambda: operate('headless')).pack(side='left', padx=6)
    ttk.Button(buttons, text='처음 화면 복구', command=lambda: operate('restore')).pack(side='left', padx=6)
    ttk.Separator(frame).pack(fill='x', pady=18)
    ttk.Label(frame, text='VNC 키보드 모드', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='주입된 Caps Lock → 한/영. 다른 프로그램이 주입한 같은 키도 해당됩니다.\n물리 키 매핑은 유지합니다. 실제 Mac/iPad 한글 조합은 기기에서 확인하세요.', wraplength=560).pack(anchor='w', pady=8)
    command = tk.BooleanVar(value=False)
    ttk.Checkbutton(frame, text='주입된 Alt → Ctrl (Mac Cmd가 Alt로 전달될 때만)', variable=command).pack(anchor='w')
    keyboard_label = tk.StringVar()

    def keyboard(on):
        try:
            result = start_keyboard(STATE, command.get()) if on else stop_keyboard(STATE)
            keyboard_label.set('VNC 모드 켜짐' if result['running'] else '직접 사용 모드')
        except Exception as error:
            messagebox.showerror('키보드 모드', str(error))
    row = ttk.Frame(frame)
    row.pack(anchor='w', pady=10)
    ttk.Button(row, text='VNC 모드 켜기', command=lambda: keyboard(True)).pack(side='left', padx=(0, 8))
    ttk.Button(row, text='직접 사용 · 끄기', command=lambda: keyboard(False)).pack(side='left')
    keyboard_label.set('VNC 모드 켜짐' if keyboard_status(STATE)['running'] else '직접 사용 모드')
    ttk.Label(frame, textvariable=keyboard_label).pack(anchor='w')
    ttk.Label(frame, textvariable=message, wraplength=560).pack(anchor='w', pady=12)
    root.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    sub.add_parser('gui')
    sub.add_parser('resume-keyboard')
    sub.add_parser('profiles').add_argument('--display')
    for action in ('apply', 'headless', 'restore'):
        item = sub.add_parser(action)
        if action != 'restore':
            item.add_argument('profile', choices=PROFILES, nargs='?', default='mac')
            item.add_argument('--display')
        item.add_argument('--keep', action='store_true')
        item.add_argument('--timeout', type=int, default=20, choices=range(2, 121), metavar='2..120')
    sub.add_parser('_guard').add_argument('request', type=Path)
    keyboard = sub.add_parser('keyboard')
    keyboard.add_argument('action', choices=('status', 'on', 'off', 'run'))
    keyboard.add_argument('--command-as-control', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == '_guard':
            return guard(args.request)
        if args.command == 'gui':
            gui()
        elif args.command == 'status':
            emit(status())
        elif args.command == 'profiles':
            emit(profiles(backend(), args.display))
        elif args.command in ('apply', 'headless', 'restore'):
            return apply_cli({'action': args.command, 'display': getattr(args, 'display', None),
                              'profile': getattr(args, 'profile', 'mac'), 'timeout': args.timeout}, args.keep)
        elif args.command in ('keyboard', 'resume-keyboard'):
            from keyboard_hook import keyboard_status, start_keyboard, stop_keyboard, run_keyboard
            action = getattr(args, 'action', 'resume')
            if action == 'run':
                return run_keyboard(STATE, args.command_as_control)
            if action == 'on':
                emit(start_keyboard(STATE, args.command_as_control))
            elif action == 'off':
                emit(stop_keyboard(STATE))
            elif action == 'resume':
                preference = STATE / 'keyboard-preference.json'
                saved = json.loads(preference.read_text(encoding='utf-8')) if preference.exists() else {}
                if saved.get('enabled'):
                    start_keyboard(STATE, saved.get('command_as_control', False))
            else:
                emit(keyboard_status(STATE))
        return 0
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        emit({'status': 'error', 'error': str(error)})
        return 1


if __name__ == '__main__':
    sys.exit(main())
