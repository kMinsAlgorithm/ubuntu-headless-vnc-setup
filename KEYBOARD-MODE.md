# Mac / iPad용 VNC 키보드 모드

바탕화면 **VNC 키보드 모드**에서 **VNC 모드 켜기** 또는 **직접 사용 · 원래 설정**을 선택합니다. 기존 Xorg/x11vnc와 IBus 한글 환경을 위한 도구입니다.

| 기능 | VNC 모드 | 직접 사용 |
|---|---|---|
| VNC로 들어온 Caps Lock | Hangul 키로 변환 | 설치 전 VNC 매핑 복구 |
| Mac 화면 공유의 두벌식 낱자 | 두벌식 영문 키로 변환 후 Ubuntu IBus에서 조합 | 기존 VNC 매핑 복구 |
| 한/영 전환 | Caps Lock, Shift+Space, Control+Space | 켜기 전 입력기 설정 복구 |
| Mac 화면 공유의 Cmd+C/V | Ctrl+C/V로 복사·붙여넣기 | 기존 VNC 매핑 복구 |
| 기존 Ctrl 키 | 그대로 사용 | 그대로 사용 |
| Cmd·Alt 단독 한/영 전환 | 해제 | 켜기 전 설정대로 복구 |
| 대문자 | Shift+영문 키 | 기존 Caps Lock 기능 사용 가능 |
| 이미 켜진 Caps Lock 잠금 | 해제 | 복구 시에도 잠금은 꺼진 상태로 시작 |

VNC 키 매핑은 서버로 전달된 키에만 적용됩니다. IBus 전환키 설정은 같은 Ubuntu 사용자 전체에 적용되므로 직접 키보드를 사용할 때는 ‘직접 사용’을 선택합니다. 물리 키보드의 XKB 배열·Num Lock·Shift/Ctrl/Alt/Super 키 자체는 바꾸지 않습니다.

## Cmd로 복사·붙여넣기

Mac 기본 ‘화면 공유’의 실제 확인에서 **양쪽 Cmd 모두 `Alt_L`로 전달**됐습니다. VNC 모드에서 `Alt_L → Control_L`만 추가합니다. 일반 앱에서 **Cmd+C/V**는 복사·붙여넣기, **Cmd+A/X/Z**는 해당 앱의 전체 선택·잘라내기·되돌리기 단축키로 동작합니다. 기존 Ctrl도 계속 사용할 수 있습니다. 물리 키보드의 Ctrl/Cmd 위치를 바꾸거나 모든 앱에 Mac 단축키 전체를 구현하는 기능은 아닙니다.

Ubuntu 터미널은 원래 복사·붙여넣기에 **Ctrl+Shift+C/V**를 사용하므로 이 모드에서는 **Cmd+Shift+C/V**를 사용합니다. Cmd+C는 Ctrl+C와 같은 터미널 인터럽트입니다.

‘직접 사용’을 누르면 추가 Cmd 매핑도 원래 값으로 복구합니다. 이 추가 설정에는 관리자 인증이나 VNC 재시작이 필요 없습니다. Option과 Super 키를 일괄 변환하지 않습니다. 다른 VNC 앱/클라이언트가 Cmd를 다른 키로 보내면 그 클라이언트의 전달 키를 먼저 확인합니다. Mac 기본 화면 공유에서 사용자가 Cmd+A/C/V 복사·붙여넣기 정상 동작을 확인했습니다. iPad의 Cmd 전달 키와 단축키는 별도 실기 확인 대상입니다.

## Mac 기본 ‘화면 공유’ 앱

실제 진단에서 Caps Lock을 누를 때마다 **영문 키와 한글 낱자가 번갈아 전달**됐습니다. Caps Lock 자체도 매번 눌림·떼기가 전달됐고 서버의 Caps 잠금은 꺼져 있었습니다. Mac의 입력 소스와 Ubuntu의 한/영 상태가 함께 바뀌는 경로입니다.

VNC 모드는 단일 두벌식 자모 33개의 Unicode/legacy X11 키를 원래 영문 키로 변환합니다. 예를 들어 `ㄱㅏㄴㅏㄷㅏ` → `rkskek` → IBus의 **가나다**로 조합합니다. Shift로 만드는 ㄲ·ㅃ·ㅒ 등도 해당 대문자 키로 변환합니다. ASCII 영문·기호·완성된 한글 음절·복합 자모·클립보드는 변환하지 않습니다. 세벌식이나 이미 조합한 문자를 다시 조합하는 범용 기능은 아닙니다.

1. 바탕화면 **VNC 키보드 모드 → VNC 모드 켜기**를 선택합니다.
2. 입력칸에서 Caps Lock을 누르며 **abc → 가나다 → abc**를 확인합니다.
3. Mac에서 한글 입력을 선택했는데 Ubuntu에 영문이 나오면 **Shift+Space를 한 번** 눌러 Ubuntu 상태를 맞춥니다. 이 보조키는 서버로 전달되는 경우에만 동작합니다.
4. 다른 앱으로 이동하거나 Mac 입력 언어를 따로 바꾼 뒤 두 상태가 다시 어긋나면 같은 방법으로 맞춥니다.

이 보정은 서버로 도착한 낱자에 적용합니다. Mac 자체의 Caps Lock 옵션을 변경하거나 두 입력 소스를 항상 자동 동기화하는 기능은 아닙니다. 수정 적용 후 사용자가 Mac에서 정상 동작을 확인했습니다.

## iPad RVNC의 대문자·된소리 문제와 보정 모듈

실제 전용 창 시험에서 RVNC는 Caps Lock을 한 번 누를 때 `down`, 다음에 누를 때 `up`을 전송했습니다. 사이에는 대문자/소문자 입력이 번갈아 도착했고 서버 Caps 잠금은 계속 꺼져 있었습니다. 이를 일반적인 한 번의 down/up으로 처리하면 한/영은 두 번에 한 번만 바뀌어 `c → C → 빤 → 반` 같은 순환이 생깁니다.

선택형 [Caps 보정 모듈](keyboard-mode/caps-bridge/bridge.c)은 클라이언트별 전달 상태를 구분합니다. 일반 Mac의 down/up 한 쌍은 한 번, iPad처럼 문자 입력 사이에 잠금 상태를 보내는 클라이언트는 각 상태 변화를 한 번의 Caps 탭으로 전달합니다. 잠금 때문에 대문자로 바뀐 ASCII 문자는 명시적인 Shift 상태에 맞춰 보정합니다. 실제 Shift 대문자·된소리와 기호는 유지합니다. 입력 내용은 기록하지 않습니다.

- Mac의 자모 보정과 함께 사용할 수 있습니다. 각 클라이언트의 상태는 분리됩니다.
- ‘직접 사용’을 누르면 보정 모듈도 꺼지고 원래 설정을 복구합니다. 매번 관리자 권한이나 VNC 재시작이 필요한 것은 아닙니다.
- 최초 모듈 설치에는 **관리자 인증 및 VNC 재시작 1회**가 필요합니다. 같은 주소로 재접속합니다. GDM·Xorg·IBus와 사용자 프로그램은 재시작하지 않습니다.
- 관측한 iPad 전송 순서와 두 번째 Mac 접속, Shift·기호·원복은 격리 시험을 통과했습니다. 설치 후 사용자가 실제 iPad RVNC에서 **전환·조합·Shift 모두 정상**을 확인했습니다. 자세한 범위는 [VALIDATION.md](VALIDATION.md)를 확인합니다.

처음에는 Caps 눌림 중 실제 문자 입력이 도착해야 ‘잠금 상태를 보내는 클라이언트’로 식별됩니다. **접속 직후 문자 없이 Caps만 여러 번 누르는 경우**는 정상 Mac의 눌림·떼기와 구분할 수 없습니다. 먼저 Caps 뒤에 글자를 한 번 입력해 확인합니다. 입력 소스가 어긋나면 Shift+Space로 맞춥니다. 명시적으로 Caps를 누른 채 문자를 입력하는 Mac도 대문자 잠금을 없애는 같은 정책으로 처리됩니다.

RVNC 도구 막대에서 Shift를 고정한 경우는 명시적인 Shift로 유지됩니다. 해당 버튼을 해제해야 합니다. [RVNC 모바일 보조키 사용](https://help.realvnc.com/hc/en-us/articles/360018541231-Using-RealVNC-Viewer-for-Mobile-to-control-a-remote-device)을 참조합니다. iPad 하드웨어 키보드의 Caps 언어 전환 옵션은 [Apple 문서](https://support.apple.com/en-ca/guide/ipad/ipaddd28d7ed/ipados)에 있지만 사용자 기기에서는 해당 항목을 찾지 못했으므로 이를 해결 조건으로 두지 않았습니다.

### 모듈 빌드·설치·제거

현재 검증 ABI는 Ubuntu의 x11vnc `0.9.16-8`, libvncserver1/dev `0.9.13+dfsg-3ubuntu0.2`, x86_64입니다. **대상 PC의 libvncserver 헤더와 런타임 버전을 맞춰** 빌드합니다. 다른 ABI·배포판·threads 모드는 검증 완료가 아닙니다. 패키지 갱신 후에는 다시 빌드·시험합니다.

필요한 빌드 도구는 GCC와 libX11 개발 파일, 설치된 런타임과 같은 버전의 libvncserver 개발 헤더입니다. 이 PC에서는 개발 패키지를 임시 폴더에 다운로드·추출해 사용했으며 시스템 패키지는 변경하지 않았습니다.

```bash
# 헤더 경로와 버전은 해당 PC에서 확인한 실제 값으로 지정
/usr/bin/python3 scripts/build-caps-bridge.py --headers /실제/헤더/include --header-version 실제버전
# 실제 VNC에 적용하지 않는 모듈 통합 시험
VNC_TEST_CAPS_BRIDGE="$HOME/.local/state/vnc-keyboard-mode/build/caps-bridge.so" /usr/bin/python3 tests/probe_vnc_jamo.py
# 읽기 전용 배포 계획 확인
/usr/bin/python3 scripts/install-caps-bridge.py --artifact "$HOME/.local/state/vnc-keyboard-mode/build/caps-bridge.so"
# 검증 후 최초 관리자 설치. VNC 재접속 필요
sudo /usr/bin/python3 scripts/install-caps-bridge.py --install --artifact "$HOME/.local/state/vnc-keyboard-mode/build/caps-bridge.so"
```

설치기는 기존 `/usr/local/sbin/x11vnc-physical.sh`의 검토된 실행 형식만 받아들입니다. 주소·포트·인증 경로·나머지 옵션을 유지하며 해당 VNC 프로세스에만 모듈을 로드합니다. `/usr/bin/x11vnc`와 배포판 라이브러리는 교체하지 않습니다. 라이브러리는 `/usr/local/lib/vnc-keyboard-mode/caps-bridge.so`, 최초 실행기 백업은 `/var/backups/vnc-keyboard-mode/`, 설치 영수증은 `/var/lib/vnc-keyboard-mode/bridge-install.json`입니다. 시작 후 준비 신호가 없으면 원래 실행기로 되돌리고 VNC를 다시 시작합니다.

기본 사용자 프로그램도 최신으로 설치한 뒤 VNC 모드를 켭니다. CLI `status`의 `caps_bridge`는 `1`(켜짐), `0`(꺼짐), `not-installed`(해당 서버에 없음)입니다. 상태 조회는 실제 VNC PID와 모듈 준비 신호를 대조합니다.

```bash
# 필요할 때 모듈의 시스템 연결만 제거. 다시 VNC 재접속 필요
sudo /usr/bin/python3 scripts/install-caps-bridge.py --restore
```

원래 실행기를 복구한 뒤 비활성 라이브러리 파일은 검토용으로 남깁니다. 바탕화면의 ‘직접 사용’은 설치 제거와 달리 VNC 재시작 없이 키보드 동작만 복구합니다. 서버·클라이언트 실제 입력을 전체 기록하거나 비밀번호를 채팅으로 받지 않습니다.

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

`on`은 현재 한/영 전환키, 사용자 지정값 유무, x11vnc remap/skip_lockkeys를 먼저 백업합니다. 같은 모드를 다시 켜도 원래 설정을 덮어쓰지 않습니다. `off`는 그 설정을 복구합니다. 외부에서 다른 설정으로 바꾼 흔적이 있으면 임의로 덮어쓰지 않고 중단합니다. 이전 Caps Lock 전용 버전에서 갱신할 때도 최초 원본 백업을 유지하며, 저장된 이전 적용값만 업그레이드 대상으로 인정합니다.

| 파일 | 위치 |
|---|---|
| 프로그램 | `~/.local/share/vnc-keyboard-mode/keyboard_mode.py` |
| 바탕화면 아이콘 | `<바탕화면>/VNC 키보드 모드.desktop` |
| 사용자 서비스 | `~/.config/systemd/user/vnc-keyboard-mode.service` |
| 설정 백업과 현재 모드 | `~/.local/state/vnc-keyboard-mode/` |
| 설치 파일 백업 | 위 폴더의 `install-backups/` |

VNC 모드를 켜면 사용자 서비스가 활성화됩니다. 이 서비스는 x11vnc 프로세스가 새로 시작된 경우 선택한 키 매핑을 재적용합니다. 같은 프로세스가 살아 있는 동안에는 키 설정을 계속 덮어쓰지 않습니다. 끄면 서비스 실행·자동 시작도 해제합니다. 로그인 시 재개 경로는 설정돼 있지만 새 재부팅 시험은 별도로 기록합니다.

기본 사용자 설정은 VNC/GDM/IBus를 재시작하지 않아도 적용됩니다. 선택형 iPad 모듈을 최초 설치할 때만 VNC 재시작이 필요합니다. 해상도와 직접 VNC 접속 방식은 바꾸지 않습니다. 두 도구는 `~/.local/state/vnc-control.lock`으로 x11vnc 제어 요청을 직렬화합니다. 외부 도구에서 동시에 같은 X11VNC_REMOTE 속성을 사용하는 경우에도 응답 충돌이 없는지 확인해야 합니다.

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
/usr/bin/python3 tests/probe_vnc_jamo.py
```

34개 회귀 검사와 격리된 VNC 시험에서 Caps Lock 다섯 번→Hangul 다섯 번, 대문자 잠금 방지, 소문자·Shift 대문자·Super 유지, 원래 Caps Lock 기능 복구를 확인했습니다. 별도 Xvfb/IBus 시험에서 영문 키 입력→‘가나다’ 조합도 확인했습니다.

추가 [VNC→IBus 통합 시험](tests/probe_vnc_jamo.py)은 실제 RFB로 Unicode 자모→가나다, Shift 자모→빤, legacy 자모→반, 영문 복귀·Shift 대문자·기호를 확인합니다. 임시 Xvfb/DBus/IBus와 loopback VNC만 사용하며 사용자 세션을 재시작하지 않습니다.

Mac 기본 ‘화면 공유’에서 자모를 보내는 현상은 실제 진단으로 확인했습니다. 보정은 현재 PC에 적용했으며 사용자가 Mac 정상 동작을 확인했습니다. iPad RVNC도 모듈 설치 후 사용자가 전환·조합·Shift 정상 동작을 확인했습니다. 직접 연결 키보드와 새 재부팅은 미검증입니다. 서버 시험을 실제 클라이언트 확인 완료로 대신하지 않습니다.
