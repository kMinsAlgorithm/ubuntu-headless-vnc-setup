# Mac / iPad용 VNC 키보드 모드

바탕화면 **VNC 키보드 모드**에서 **VNC 모드 켜기** 또는 **직접 사용 · 원래 설정**을 선택합니다. 기존 Xorg/x11vnc와 IBus 한글 환경을 위한 도구입니다.

| 기능 | VNC 모드 | 직접 사용 |
|---|---|---|
| VNC로 들어온 Caps Lock | Hangul 키로 변환 | 설치 전 VNC 매핑 복구 |
| 한/영 전환 | Caps Lock, Shift+Space, Control+Space | 켜기 전 입력기 설정 복구 |
| Cmd·Alt 단독 한/영 전환 | 해제 | 켜기 전 설정대로 복구 |
| 대문자 | Shift+영문 키 | 기존 Caps Lock 기능 사용 가능 |
| 이미 켜진 Caps Lock 잠금 | 해제 | 복구 시에도 잠금은 꺼진 상태로 시작 |

VNC 키 매핑은 서버로 전달된 키에만 적용됩니다. IBus 전환키 설정은 같은 Ubuntu 사용자 전체에 적용되므로 직접 키보드를 사용할 때는 ‘직접 사용’을 선택합니다. 물리 키보드의 XKB 배열·Num Lock·Shift/Ctrl/Alt/Super 키 자체는 바꾸지 않습니다.

## 한글이 낱자로 입력될 때

**먼저 Mac/iPad 입력 언어를 ABC/영문으로 두고, 우분투에서 한글을 조합합니다.** Mac에서 한글 모드로 입력하면 VNC 앱이 자음·모음 문자를 개별 전송할 수 있습니다. 이 경우 서버에서 Caps Lock만 재매핑해도 ‘ㄱㅏㄴㅏ’ 문제가 해결되지는 않습니다.

1. Mac/iPad 입력 언어를 **ABC/영문**으로 선택합니다.
2. VNC 창 안에서 **Shift+Space**로 우분투 한/영을 전환합니다.
3. ‘가나다’처럼 조합되는지 테스트 입력칸에서 확인합니다.
4. Caps Lock을 누를 때 Mac/iPad 입력 언어까지 바뀌면 클라이언트가 그 키를 자체 처리하고 있는 것입니다. 해당 VNC 앱의 원격 키 전달 기능을 확인합니다. 서버에서 클라이언트의 언어 설정을 변경할 수는 없습니다.

Caps Lock을 모든 앱에서 계속 한/영 전환에 사용하려는 경우, 기기 전체의 Caps Lock 단축키를 무조건 끄지 말고 VNC 앱에만 적용할 수 있는 설정을 우선 조사합니다. 앱 이름과 버전에 따라 지원 여부가 다릅니다. 사용할 수 없다면 VNC에서는 Shift+Space를 보조키로 쓸 수 있습니다.

Mac의 Caps Lock 입력 언어 전환 옵션은 [Apple 입력 소스 설정](https://support.apple.com/en-euro/guide/mac-help/mchl84525d76/mac)을 참조합니다. RealVNC의 Cmd/Option 매핑은 [공식 키보드 매핑 문서](https://help.realvnc.com/hc/en-us/articles/360002250597-Keyboard-Mapping-To-and-From-a-Mac)를 참조합니다. 사용 중인 앱이 확정되기 전 다른 앱의 옵션을 적용하지 않습니다.

## 설치와 Codex 명령

기존 VNC가 실행 중이고, 대상 데스크톱에서 IBus `hangul` 엔진을 사용해야 합니다. root가 아닌 해당 사용자로 실행합니다. DISPLAY/XAUTHORITY/사용자 DBus는 [해상도 매뉴얼](DISPLAY-PROFILES.md)의 조사 절차를 따릅니다. 인증 파일 내용을 읽지 않습니다.

레포 루트에서:

```bash
# 의존성 확인만 수행
/usr/bin/python3 scripts/install-keyboard-mode.py
# 파일 백업 후 아이콘·프로그램·사용자 서비스 설치. 키 설정은 아직 바꾸지 않음
/usr/bin/python3 scripts/install-keyboard-mode.py --install
```

필수: Python3/PyGObject/GTK3, IBus 한글, x11vnc, libX11, gsettings, systemctl, gio, xdg-user-dir. 기본 환경이 없는 PC에 전체 입력기를 자동 교체하는 설치기는 아닙니다.

설치 후:

```bash
/usr/bin/python3 "$HOME/.local/share/vnc-keyboard-mode/keyboard_mode.py" status
/usr/bin/python3 "$HOME/.local/share/vnc-keyboard-mode/keyboard_mode.py" on
/usr/bin/python3 "$HOME/.local/share/vnc-keyboard-mode/keyboard_mode.py" off
/usr/bin/python3 "$HOME/.local/share/vnc-keyboard-mode/keyboard_mode.py" gui
```

`on`은 현재 한/영 전환키, 사용자 지정값 유무, x11vnc remap/skip_lockkeys를 먼저 백업합니다. 같은 모드를 다시 켜도 원래 설정을 덮어쓰지 않습니다. `off`는 그 설정을 복구합니다. 외부에서 다른 설정으로 바꾼 흔적이 있으면 임의로 덮어쓰지 않고 중단합니다.

| 파일 | 위치 |
|---|---|
| 프로그램 | `~/.local/share/vnc-keyboard-mode/keyboard_mode.py` |
| 바탕화면 아이콘 | `<바탕화면>/VNC 키보드 모드.desktop` |
| 사용자 서비스 | `~/.config/systemd/user/vnc-keyboard-mode.service` |
| 설정 백업과 현재 모드 | `~/.local/state/vnc-keyboard-mode/` |
| 설치 파일 백업 | 위 폴더의 `install-backups/` |

VNC 모드를 켜면 사용자 서비스가 활성화됩니다. 이 서비스는 x11vnc 프로세스가 새로 시작된 경우 선택한 키 매핑을 재적용합니다. 같은 프로세스가 살아 있는 동안에는 키 설정을 계속 덮어쓰지 않습니다. 끄면 서비스 실행·자동 시작도 해제합니다. 로그인 시 재개 경로는 설정돼 있지만 새 재부팅 시험은 별도로 기록합니다.

VNC/GDM/IBus를 재시작하지 않아도 적용됩니다. 해상도와 직접 VNC 접속 방식은 바꾸지 않습니다. 두 도구는 `~/.local/state/vnc-control.lock`으로 x11vnc 제어 요청을 직렬화합니다. 외부 도구에서 동시에 같은 X11VNC_REMOTE 속성을 사용하는 경우에도 응답 충돌이 없는지 확인해야 합니다.

## 복구와 제거

먼저 바탕화면의 **직접 사용 · 원래 설정**, 또는 CLI `off`를 실행합니다. 설정 파일만 지워서는 입력기와 VNC 매핑이 복구되지 않습니다.

복구 확인 후 앱·바탕화면 아이콘·앱 메뉴 항목·사용자 서비스 파일을 제거하고 `systemctl --user daemon-reload`를 수행할 수 있습니다. 원래 설정을 보관한 `.local/state/vnc-keyboard-mode` 백업은 보존합니다. 설치 전 파일이 있었다면 설치 영수증의 `backup`을 해당 `destination`으로 복구합니다.

VNC 서버가 이미 종료됐다면 기존 프로세스가 사라진 것을 확인하고 입력기 설정을 복구합니다. 새 VNC 서버가 아직 이 도구의 관리를 받지 않았다면 이전 서버의 옵션을 그 서버에 덮어쓰지 않습니다.

## 구현과 검증

- [프로그램](keyboard-mode/keyboard_mode.py), [설치기](scripts/install-keyboard-mode.py)
- [설정·복구 검사](tests/test_keyboard_mode.py)
- [실제 RFB 입력 검사](tests/probe_vnc_keyboard.py): 별도 Xvfb와 127.0.0.1 전용 임시 VNC만 사용. 실제 서버 암호와 사용자 입력을 읽지 않습니다.

```bash
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 tests/probe_vnc_keyboard.py
/usr/bin/python3 tests/probe_ibus_composition.py
```

28개 회귀 검사와 격리된 VNC 시험에서 Caps Lock 다섯 번→Hangul 다섯 번, 대문자 잠금 방지, 소문자·Shift 대문자·Super 유지, 원래 Caps Lock 기능 복구를 확인했습니다. 별도 Xvfb/IBus 시험에서 영문 키 입력→‘가나다’ 조합도 확인했습니다.

실제 Mac에서는 **Mac 입력 언어가 한글일 때 자음·모음이 분리되는 증상**이 보고됐습니다. 서버 시험을 실제 클라이언트 확인 완료로 대신하지 않습니다. Mac ABC 상태에서의 조합, 앱별 Caps Lock 전달, iPad와 직접 연결 키보드는 실제 확인 결과를 추가 기록합니다.
