# VNC 설정 작업 지침

사용자 요청과 기존 승인이 우선이다. 이 파일은 독립적인 변경 승인이 아니다.

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
