# VNC 설정 작업 지침

사용자 요청과 기존 승인이 우선이다. 이 파일은 독립적인 변경 승인이 아니다.

## Windows 작업 경로

- Windows 10/11은 `WINDOWS.md`와 `windows/`를 사용한다. 아래 Xorg/IBus/systemd 지침은 Ubuntu 경로다. Windows에서 Ubuntu 도구를 실행하거나 레퍼런스 설정을 복사하지 않는다.
- VNC가 정상 동작하면 서버·암호를 보존한다. 새 비밀번호는 사용자 터미널의 숨김 입력으로만 받고 커밋·로그·보고서에 넣지 않는다.
- 가상 화면은 `setup-vnc.ps1 -Action InstallVirtualDisplay`의 고정 SHA-256·게시자 서명 검사를 사용한다. 테스트 서명·Secure Boot·메모리 무결성·루트 인증서를 바꾸지 않는다.
- 사용자 도구는 일반 사용자로 `install-tools.ps1 -Action Install`을 사용한다. 상태·백업·설치 영수증은 LOCALAPPDATA/ProgramData에만 두고 커밋하지 않는다.
- 지속 실행하는 키보드·접속 감시기는 사용자 InteractiveToken 예약 작업으로 시작한다. Codex/터미널의 자식 프로세스를 장기 실행으로 보고하지 않는다. AppData가 가상화된 환경에서는 실제 파일 핸들의 경로를 사용하고, 설치된 모듈은 그 설치 위치의 상태 디렉터리를 사용한다. 사용자 작업 정의의 백업·복구를 보존한다.
- 화면 전환은 `vnc_desktop.py apply/headless/restore`와 독립 복구 프로세스를 사용한다. 설치만으로 화면을 변경하지 않는다. 현재 다중 출력·회전·창 배치를 조사하고 원복을 확인한다.
- 접속 중 자동 가상 화면은 `vnc_desktop.py auto on/off/status`를 사용한다. 단순 TCP 접속을 인증 성공으로 취급하지 않는다. native tvnserver 이벤트와 현재 서비스 연결을 관측하며 키 입력 로그를 켜거나 관리 채널의 실행 파일 제한을 우회하지 않는다. 자동 모드의 세션 백업과 별도 복구 프로세스를 보존하고, 수동 토폴로지 전환 전에는 auto off로 복구한다.
- Windows 키보드 모드는 주입 이벤트 훅이며 VNC 클라이언트 식별 기능이 아니다. 단일 두벌식 자모 33개는 Windows Korean IME로 조합하며 실제 클라이언트 확인과 정책 모의 검사를 구분한다. Cmd 변환은 선택형이다. Ubuntu의 iPad Caps 상태 보정·클립보드 보호를 Windows에서 검증했다고 보고하지 않는다.
- Windows 검증은 `python -m unittest discover -s tests -p "test_windows*.py" -v`, PowerShell 구문 분석, 두 설치기의 Check, `git diff --check`를 사용한다. Ubuntu 전체 검사는 Linux에서 별도로 실행한다. 케이블 분리·새 부팅·Mac/iPad 실기·외부 접속은 실제 통과와 미실시를 구분한다.

## Ubuntu 작업 경로

- README.md → CODEX-RUNBOOK.md를 읽고 작업 경로를 고른다. 기존 VNC에 Mac/iPad 선택기를 추가하는 요청은 DISPLAY-PROFILES.md를 따른다.
- 현재 기준 PC의 승인된 iPad 값은 **1600×1050, x11vnc scale=1**이다. Mac은 1920×1080이다. CLI 키는 `ipad`, `mac`이다.
- 수동 선택기와 `adaptive-display-mode.service`의 자동 모드 정책을 함께 켜지 않는다. 수동 경로에서는 watcher를 disabled/inactive로 둔다. `x11vnc-physical-policy.service`도 함께 활성화하지 않는다.
- 이전 1600×1200 + 3/5 축소 전송을 복원하지 않는다. 흐린 글씨의 원인이었다. `scaled_x/scaled_y`만 보고 전송 크기를 단정하지 않는다.
- 설치·상태 조회·화면 적용을 구분한다. 설치는 `scripts/install-resolution-switcher.py`, 상태/미리보기/유지는 `scripts/display-profile.py`를 쓴다. 임의의 GUI 클릭이나 복구 없는 xrandr 명령으로 대체하지 않는다.
- 선택기와 CLI는 동시에 조작하지 않는다. 설치 전에도 선택기 창을 닫는다. CLI는 대상 데스크톱 사용자와 해당 X11/DBus 환경에서 실행한다. root, 고정 사용자명/UID, 다른 DISPLAY로 실행하지 않는다.
- 선택기 설치만으로 GDM/Xorg/VNC를 재시작하거나 재부팅할 필요는 없다. 기존 직접 VNC 접속과 실행 중인 사용자 프로그램을 유지한다. 로봇 제어·시뮬레이터 내부 상태는 변경하지 않는다.
- 기준은 단일 출력, 원점 (0,0), 회전 없는 Xorg/x11vnc다. Wayland·다중 출력·다른 GPU를 검증 완료로 취급하지 않는다. `reference/current-pc`는 2026-09-15 참고 스냅샷이지 자동 설치 템플릿이 아니다.
- 암호 파일, Xauthority 내용, 개인키, 접속 IP가 들어간 로그, 사용자 스크린샷은 커밋하지 않는다. 설치 영수증·실행 로그는 사용자의 `.local/state/vnc-resolution-switcher`에 둔다.
- 변경 검증: `/usr/bin/python3 -m unittest discover -s tests -v`, `/usr/bin/python3 scripts/install-resolution-switcher.py --check`, `git diff --check`. 문서의 명령은 먼저 구문만 확인한다. 활성 화면 변경 시험은 필요할 때만 수행하고 실제 결과와 미실시를 구분한다.
- 코드·문서·실제 설치본의 차이, 백업 경로, 현재 해상도/scale/서비스 상태를 인계한다. 재부팅 후 마지막 선택 복원을 구현한 것으로 보고하지 않는다. 현재 선택은 X 세션 범위다.

## 키보드 모드 작업

- KEYBOARD-MODE.md를 읽고 현재 입력기·클라이언트 입력 언어를 확인한다. Mac 한글 모드에서 낱자를 전송하는 문제를 서버 Caps Lock 재매핑만으로 해결 완료라고 하지 않는다.
- Codex CLI는 `keyboard_mode.py status/on/off`다. 개인 원본 설정은 `.local/state/vnc-keyboard-mode`에 저장하며 커밋하지 않는다.
- 키보드 모드의 사용자 서비스와 기존 자동 해상도 서비스는 별개다. 키보드 모드를 켜면서 adaptive-display-mode.service를 켜지 않는다.
- x11vnc 제어 요청은 두 도구가 공유하는 vnc-control.lock을 사용한다. 사용자 키 입력 전체를 기록하지 않는다.
- 실제 Mac/iPad 조합과 Caps Lock 전환은 사용자 확인이 필요하다. 격리된 VNC/IBus 검사 결과와 구분한다.

- iPad RVNC Caps 상태형 전송에는 선택형 caps-bridge 모듈을 사용한다. 먼저 관측·격리 재현을 수행하고 KEYBOARD-MODE.md의 정확한 ABI·백업·배포 절차를 따른다. 기본 매핑 설치와 구분하며 최초 모듈 로드에만 VNC 재시작이 필요하다. GDM/Xorg/IBus는 재시작하지 않는다. 관리자 비밀번호는 사용자 터미널에서만 입력받는다.

- iPad 복사 보호는 클립보드 수신 제한이다. 기기 간 한글 전송을 해결했다고 보고하지 않는다. `clipboard-on/off`와 직접 사용 원복을 사용하며, 기존 활성 프로필의 원래 키 백업을 보존한다. 실제 클립보드·키 입력 로그를 남기지 않는다.
