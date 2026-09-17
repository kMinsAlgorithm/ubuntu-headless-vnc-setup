# Mac / iPad 해상도 선택기

2026-09-17 기준 PC에서 사용자가 확인한 최종 설정입니다. 기존 Xorg/x11vnc 화면에 바탕화면 아이콘을 추가합니다. 같은 서버에 접속한 모든 뷰어에 해상도 변경이 적용됩니다.

| 바탕화면 메뉴 | CLI 키 | 서버 화면 | VNC 배율 |
|---|---|---|---|
| Mac · FHD | `mac` | 1920×1080 | 1 (원본 픽셀) |
| iPad · 선명한 전체 보기 | `ipad` | **1600×1050** | **1 (원본 픽셀)** |
| iPad · 가로 화면 | `ipad-landscape` | 1184×824 | 1 |
| iPad · 큰 글씨 | `ipad-large-text` | 1024×768 | 1 |

기준 iPad는 가로 사용입니다. 최종 1600×1050은 실제 사용자가 선명도와 하단 여유를 확인한 값이며 모든 iPad 모델의 물리 해상도라는 뜻은 아닙니다. VNC 앱의 ‘화면에 맞추기’와 ‘비율 유지’를 사용합니다. 앱 이름과 정확한 모델은 확정하지 않았습니다.

## 왜 이 설정인가

- 기존 감지 서비스가 약 10초마다 1920×1080으로 되돌려 수동 해상도를 덮어썼습니다. 수동 선택 경로에서는 `adaptive-display-mode.service`를 중지하고 자동 시작도 끕니다.
- 서버가 1600×1200 화면을 3/5로 줄여 보낸 뒤 iPad에서 확대하면 글자가 흐렸습니다. 모든 모드를 `scale=1`로 전송합니다.
- 원본 전송으로 선명해진 후, iPad 하단 여유를 위해 1600×1200에서 **1600×1050**으로 낮췄습니다. 이 상태를 사용자가 수용했습니다.
- 화면보다 큰 일반 프로그램 창은 현재 작업 공간 안으로 위치·크기를 조정합니다. 최소 창 크기가 작업 공간보다 큰 앱, 최대화·전체 화면·최소화된 창은 별도 제약이 있습니다. 프로그램 자체의 최소 크기를 강제로 무시하지 않습니다.

## 설치 전 확인

대상 데스크톱의 일반 사용자로 레포 루트에서 실행합니다. 기존 VNC가 정상 동작하는 PC에 선택기만 추가한다면 [MANUAL.md](MANUAL.md)의 GDM/Xorg 재설치나 서비스 재시작 절차는 필요하지 않습니다.

필수 환경은 단일 활성 출력의 Xorg, xrandr, x11vnc 원격 제어, GTK3/PyGObject와 libwnck3입니다. 현재 검증한 화면 배치는 원점 (0,0), 회전 없음입니다. NVIDIA에서 RandR 화면 축소가 `RRSetScreenSize` 오류로 실패하면 `nvidia-settings`의 MetaMode 전환을 사용합니다. 다른 GPU·Wayland·다중 화면은 검증하지 않았습니다.

```bash
/usr/bin/python3 scripts/install-resolution-switcher.py --check
/usr/bin/python3 scripts/display-profile.py profiles
```

의존성이 없을 때만 Ubuntu 패키지를 설치합니다. `nvidia-settings`는 NVIDIA 대체 전환에 필요하며 다른 GPU에 NVIDIA 드라이버를 설치하라는 뜻은 아닙니다.

```bash
sudo apt-get install python3-gi python3-cairo python3-gi-cairo gir1.2-gtk-3.0 gir1.2-wnck-3.0 x11-xserver-utils x11-utils x11vnc libglib2.0-bin xdg-user-dirs
```

Codex/관리용 SSH에서 화면에 접근하지 못하면 실제 세션의 DISPLAY, XAUTHORITY 경로, XDG_RUNTIME_DIR, DBUS_SESSION_BUS_ADDRESS를 조사해 설정합니다. 인증 파일의 **내용은 읽거나 기록하지 않습니다**. 아래는 이 기준 PC에만 해당하는 예시입니다.

```bash
export DISPLAY=:0
export XAUTHORITY=/run/user/1000/gdm/Xauthority
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
/usr/bin/python3 scripts/display-profile.py status
```

다른 PC에서는 사용자와 UID, 세션 경로를 치환합니다. `sudo python3`로 선택기를 실행하지 않습니다. VNC 서버가 중복 실행되거나 원격 제어가 차단된 환경이면 먼저 그 원인을 해결합니다.

## 설치

열려 있는 ‘화면 해상도 선택’ 창을 닫습니다. 아래 명령은 설치 파일을 백업하고 아이콘·GUI·CLI를 설치하며, 충돌하는 자동 감지 서비스를 중지/비활성화합니다. 화면 해상도 자체는 변경하지 않습니다.

```bash
/usr/bin/python3 scripts/install-resolution-switcher.py --install --disable-adaptive
```

이미 watcher가 disabled/inactive이거나 없는 PC에서는 `--disable-adaptive`를 생략할 수 있습니다. 활성 상태에서 생략하면 설치를 거부합니다. `x11vnc-physical-policy.service`처럼 watcher를 다시 시작하는 다른 서비스도 조사하고 수동 경로에서 켜지 않습니다.

바탕화면 폴더는 `xdg-user-dir DESKTOP`으로 찾습니다. 필요한 경우 `--desktop-dir '/실제/바탕화면'`으로 지정합니다. 출력 JSON의 `desktop_trusted`가 false이면 GNOME 파일 관리자에서 아이콘에 ‘실행 허용’을 선택합니다.

설치 위치:

| 파일 | 위치 |
|---|---|
| GUI·아이콘·Codex CLI | `~/.local/share/vnc-resolution-switcher/` |
| 앱 메뉴 항목 | `~/.local/share/applications/vnc-resolution-switcher.desktop` |
| 바탕화면 항목 | `<바탕화면>/화면 해상도 선택.desktop` |
| 설치 백업·영수증 | `~/.local/state/vnc-resolution-switcher/install-backups/<시각>/receipt.json` |
| 전환 기록 | `~/.local/state/vnc-resolution-switcher/events.jsonl` |

기존 5개 대상 파일을 먼저 백업하고 각 파일을 교체합니다. 서비스 변경 전후 상태와 파일 지문은 영수증에 남깁니다. 설치 도중 실패하면 일부 파일은 교체되었을 수 있으므로 영수증과 백업을 확인합니다. 기존 Xorg/GDM/VNC 설정·비밀번호·직접 접속 방식은 이 설치기의 수정 대상이 아닙니다.

## 사용과 Codex 명령

바탕화면 **화면 해상도 선택** → 원하는 모드 → **선택한 해상도 적용** → 20초 안에 **이 해상도 유지**를 누릅니다. 취소·창 닫기·미확인 시간 초과 시 이전 화면과 VNC 배율, 캡처한 창 배치를 복구합니다. 별도 복구 프로세스가 있어 UI 프로세스가 종료돼도 복구를 시도합니다. X 서버 자체가 종료되면 이 복구를 보장할 수 없습니다.

Codex는 설치된 CLI로 상태를 읽고 적용할 수 있습니다. `profiles`와 `status`는 화면을 바꾸지 않습니다.

```bash
/usr/bin/python3 "$HOME/.local/share/vnc-resolution-switcher/display_profile.py" status
/usr/bin/python3 "$HOME/.local/share/vnc-resolution-switcher/display_profile.py" profiles
```

20초 미리보기 후 **자동 복구**:

```bash
/usr/bin/python3 "$HOME/.local/share/vnc-resolution-switcher/display_profile.py" apply ipad
```

사용자가 요청한 설정을 확인 후 **유지**:

```bash
/usr/bin/python3 "$HOME/.local/share/vnc-resolution-switcher/display_profile.py" apply ipad --keep
```

Mac으로 전환하려면 `ipad` 대신 `mac`을 씁니다. 레포 안에서는 `scripts/display-profile.py`로 같은 명령을 실행할 수 있습니다. `--keep`은 서버 화면과 VNC 배율을 확인한 뒤 확정합니다. 사람이 iPad에서 선명도·잘림을 직접 확인한 것까지 의미하지는 않습니다. GUI가 열려 있거나 자동 감지 서비스가 켜져 있으면 CLI 적용을 거부합니다. GUI와 CLI를 동시에 시작하지 않습니다.

같은 해상도와 scale=1이면 `unchanged`를 반환하고 창 크기도 다시 건드리지 않습니다. 모든 적용에는 기존 상태를 보관한 복구 프로세스가 먼저 준비됩니다. 미리보기 중 CLI가 종료되어 파이프가 닫혀도 복구를 시도합니다.

## 확인과 문제 해결

1. `status`에서 iPad는 `desktop: 1600x1050`, `vnc_scale: 1`, `native_pixels: true`인지 확인합니다.
2. watcher가 disabled/inactive인지 확인하고 35초 이상 뒤에도 해상도가 유지되는지 봅니다.
3. iPad에서 오른쪽·아래 끝, 글자 선명도, 원형 안내 표시, 클릭 좌표를 확인합니다.
4. 새 PC에서 실제 변경 시험이 필요하면 먼저 미리보기 자동 복구를 확인하고, 유지 시험을 진행합니다. 현재 사용 중인 화면을 문서 검증만을 위해 반복 전환하지 않습니다.

| 증상 | 점검 |
|---|---|
| 몇 초 후 FHD로 돌아감 | 자동 watcher와 이를 시작하는 다른 서비스, 마지막 변경 로그 |
| 글자가 흐림 | `scale=1` 여부, 뷰어의 확대/축소·화질 설정. 서버 축소 전송을 다시 켜지 않음 |
| 아래가 잘림 | 실제 화면이 1600×1050인지, 뷰어 전체 화면 맞춤·툴바·줌 상태 |
| 바탕화면은 다 보이나 앱 내용이 잘림 | 앱 최소 크기와 현재 작업 공간. 다른 프로필 또는 앱의 레이아웃 조정 |
| 동그라미가 타원 | 뷰어 비율 유지 설정. 서버 해상도를 억지로 늘려 보정하지 않음 |
| 사용자 정의 모드 없음 | GUI 실행/CLI 적용 시 X 세션에 재등록; 드라이버가 거부한 모드는 오류로 표시 |
| VNC scale 조회 실패 | 대상 DISPLAY/Xauthority, x11vnc 실행·원격 제어 가능 여부 |

`x11vnc -Q scaled_x,scaled_y`는 배율을 1로 돌린 뒤 예전 축소 크기가 남을 수 있습니다. 전송 크기가 의심되면 서버 로그의 최신 `rfbNewFramebuffer`/`NewFBSize`와 실제 뷰어를 함께 확인합니다. 접속 IP가 들어간 원본 로그는 레포에 넣지 않습니다.

선택한 모드와 사용자 정의 modeline은 **현재 X 세션에 적용**됩니다. 로그아웃·재부팅 후 마지막 선택을 자동 복원하는 기능은 없습니다. 다시 아이콘/CLI로 선택할 수 있으며, 재부팅 후 사용 흐름은 별도 검증 항목입니다. watcher를 껐으므로 실물 모니터 연결·해제에 따른 기존 자동 모드 전환도 수행하지 않습니다.

## 복구

- 화면 미리보기 중 문제가 생기면 유지하지 말고 20초 기다리거나 ‘이전 해상도로 복구’를 누릅니다.
- 이미 유지한 모드를 바꾸려면 CLI `apply mac --keep` 또는 아이콘으로 Mac 모드를 선택합니다. 이는 **수동 FHD 전환**이고 watcher 재활성화가 아닙니다.
- 설치 파일을 원복하려면 선택기를 닫고 해당 설치 영수증의 `files`를 확인합니다. `existed: true`인 항목은 `backup`을 `destination`으로 `cp -p --` 복사합니다. `existed: false`인 신규 파일은 이후 변경이 없는지 지문을 비교한 뒤 해당 파일만 제거합니다. 백업 디렉터리는 보존합니다.
- 서비스 상태도 설치 전으로 되돌릴 목적일 때만 `adaptive_before`를 확인합니다. 기존 자동 모니터 정책으로 돌아가겠다는 요청이 있으면 수동 선택기 사용을 중단하고 아래 명령을 적용합니다. 수동 iPad 사용을 유지할 때는 실행하지 않습니다.

```bash
systemctl --user enable --now adaptive-display-mode.service
```

현재 기준 PC는 **disabled/inactive 유지**가 정답입니다. VNC/GDM 재시작이나 재부팅을 일반 복구 명령으로 실행하지 않습니다.

## 구현 파일과 검증

- [GUI와 복구 프로세스](resolution-switcher/resolution_switcher.py)
- [설치기](scripts/install-resolution-switcher.py), [Codex CLI](scripts/display-profile.py)
- [자동 검사](tests/test_display_tools.py)
- [실제 상태](REFERENCE-STATE.md), [검증 범위](VALIDATION.md), [PC별 기록 양식](CHECKLIST.md)

```bash
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 scripts/install-resolution-switcher.py --check
git diff --check
```

자동 검사는 임시 디렉터리와 모의 화면을 사용합니다. 실제 디스플레이를 전환하지 않으며 실제 iPad 확인을 대체하지 않습니다.
