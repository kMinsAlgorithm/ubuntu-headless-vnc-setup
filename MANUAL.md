# Ubuntu 가상 디스플레이와 VNC 상세 매뉴얼

작성일: 2026-09-15 · 기본 OS: Ubuntu Desktop 22.04 LTS · 고려 OS: Ubuntu Desktop 24.04 LTS

**경로 선택:** 이 본문은 헤드리스 VNC 기반 구성과 **실물 모니터 자동 감지**를 다룹니다. 기존 VNC에 Mac/iPad 수동 해상도 선택기만 추가할 때는 [DISPLAY-PROFILES.md](DISPLAY-PROFILES.md)를 따릅니다. 2026-09-17 기준 PC는 수동 경로이며, 본문의 watcher enable/restart 예시를 적용하지 않습니다. 선택기 설치에는 재부팅이나 VNC/GDM 재시작이 필요하지 않습니다.

## 1. 목표와 검증 범위

1. 모니터가 있으면 Ubuntu의 주 모니터 화면을 원격에서 조작한다.
2. 모니터가 없으면 기본 1920×1080 가상 화면으로 같은 사용자 데스크톱을 유지한다.
3. 부팅 후 자동 로그인과 VNC 자동 시작으로 현장 로그인 없이 접속한다.
4. 실행 중 모니터 연결 상태를 감지하고, 로그인 세션을 종료하지 않고 화면을 조정한다.
5. VNC 뷰어에서 대상 주소·포트로 직접 접속할 수 있도록 구성하고 실제 외부망에서 시험한다.

**완료는 대상 PC의 실제 시험으로 판단합니다.** 파일 생성·문법 검사·서비스의 `active` 표시는 화면 공유 전체의 성공을 뜻하지 않습니다.

| 항목 | 기준 PC에서 확인한 것 | 대상 PC에서 필요한 작업 |
|---|---|---|
| 출력 선택 | NVIDIA `DFP-2` / Xrandr `HDMI-0` 고정 | 실제 출력·주 모니터 조사 |
| 모니터 없음 | 물리 출력 미검출 상태의 1920×1080 | 실제 원격 접속 시험 |
| 모니터 있음 | 선호 해상도로 바꾸는 코드 존재 | 실제 케이블 연결·해제 시험 |
| 자동 시작 | 자동 로그인 세션·서비스 실행 확인 | 재부팅 후 접속 시험 |
| 여러 모니터 | 주 모니터 자동 추적 미구현 | 8장의 선택·영역 갱신 구현 및 시험 |
| 외부 접속 | 공인 IP에서 VNC를 사용한 기록 | 직접 VNC 접속 주소·공유기·방화벽 경로 기록 |
| Ubuntu 24.04 | 기준 PC는 22.04 | 24.04 장비에서 별도 검증 |

기준 PC의 상세 상태는 [REFERENCE-STATE.md](REFERENCE-STATE.md), 참고 원본은 [reference/current-pc](reference/current-pc)에 있습니다.

## 2. 구성 이해

```text
Ubuntu 부팅
  → GDM이 대상 사용자로 자동 로그인
  → Xorg가 화면 준비
  → 화면 감지 서비스가 모니터 정보와 해상도 확인
  → x11vnc가 같은 Xorg 데스크톱 공유
  → 외부 기기가 정해진 네트워크 경로로 접속
```

- **Xorg/X11:** 데스크톱 화면을 관리하는 시스템.
- **GDM:** Ubuntu의 그래픽 로그인 관리자.
- **EDID:** 모니터가 제공하는 지원 해상도 등의 정보.
- **DISPLAY:** 공유할 X 서버 주소. 기준 PC는 `:0`이며 다른 PC에서는 다를 수 있음.
- **XAUTHORITY:** X 서버에 접근하는 인증 파일 경로. 내용은 문서에 기록하지 않음.
- **VNC 포트:** 기본 예시는 TCP 5900. X 서버 번호와 별도로 정하는 값.

독립 TigerVNC/Xvnc 데스크톱을 만들면 기존 로컬 프로그램과 다른 세션을 보게 될 수 있습니다. 기본 경로는 **실제 로그인한 사용자의 로컬 Xorg 데스크톱 공유**입니다.

## 3. 시작 전 조사와 PC별 변수

이후 명령은 **새로 설정할 대상 PC**에서 실행합니다. 문서 작성 과정에서 기준 PC에 실행한 설치 명령이 아닙니다.

### 3.1 OS·GPU·서비스

```bash
cat /etc/os-release
lspci -nnk | rg -A 3 -i 'vga|3d|display'
loginctl list-sessions
systemctl status display-manager --no-pager
systemctl list-units --all --type=service --no-pager | rg -i 'vnc|gdm|lightdm|sddm|tailscale|ssh'
systemctl --user list-unit-files --no-pager | rg -i 'vnc|display|remote'
ss -lntp | rg ':5900\b|:5901\b|:22\b'
```

`rg`가 없으면 `grep -E` 등으로 대체합니다. `systemctl --user`는 대상 사용자의 로그인 터미널에서 실행합니다. `sudo systemctl --user`로 root의 사용자 서비스를 조작하지 않습니다.

`loginctl`에서 물리 좌석 `seat0`의 세션을 선택한 뒤 아래 `SESSION_ID`를 실제 값으로 바꿉니다.

```bash
loginctl show-session SESSION_ID -p Name -p Type -p Service -p State -p Leader
ps -eo pid,user,comm,args | rg '[/](Xorg|x11vnc|Xtigervnc|Xvnc)'
```

기존 원격 화면이 정상 운영 중이면 그 구성을 먼저 기록합니다. 같은 포트에 서버를 중복 실행하거나 다른 원격 접속 서비스를 일괄 중지하지 않습니다.

### 3.2 사용자·화면 값

가능하면 **대상 Ubuntu 데스크톱 안에서 연 터미널**에서 확인합니다.

```bash
id
printf 'DISPLAY=%s\nXAUTHORITY=%s\nXDG_SESSION_TYPE=%s\n' "$DISPLAY" "$XAUTHORITY" "$XDG_SESSION_TYPE"
xrandr --query
xrandr --listmonitors
```

SSH의 `DISPLAY`는 비어 있거나 `localhost:10.0` 같은 포워딩 주소일 수 있으므로 로컬 데스크톱 주소로 쓰지 않습니다. 인증 경로는 Xorg 프로세스의 `-auth` 인자와 대상 사용자 정보를 통해 확인합니다.

이후 설치 예시는 **대상 사용자 본인의 일반 로그인 셸**에서 아래 변수를 설정한 상태를 전제로 합니다.

```bash
TARGET_USER="$(id -un)"
TARGET_UID="$(id -u)"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
TASK_ROOT="$TARGET_HOME/headless-vnc-setup"
mkdir -p "$TASK_ROOT/staging"
```

root 셸이면 대상 사용자의 셸로 전환합니다. root를 자동 로그인 사용자로 지정하지 않습니다. 터미널을 새로 열었다면 변수도 다시 설정합니다.

| 값 | 기준 PC 예시 | 대상 PC 확인 방법 |
|---|---|---|
| 사용자/홈/UID | `kmg`, `/home/kmg`, `1000` | `id`, `getent passwd` |
| DISPLAY/인증 경로 | `:0`, `/run/user/1000/gdm/Xauthority` | 데스크톱 환경, Xorg `-auth` |
| Xrandr 출력 | `HDMI-0` | `xrandr --query` |
| NVIDIA 출력 | `DFP-2` | NVIDIA 설정 도구, Xorg 초기 로그 |
| GPU BusID | `PCI:1:0:0` | `lspci`, Xorg 로그·설정 |
| 가상 해상도 | `1920x1080` | 실제 지원 모드·사용 목적 |
| VNC 포트 | `5900` | 기존 수신 포트 |
| 외부 경로 | 공유기 규칙 미확인 | 공인 주소·NAT·VNC 포트 조사 |

값을 [CHECKLIST.md](CHECKLIST.md)에 기록합니다. PCI 주소는 도구별 진법·형식이 다를 수 있으므로 구분 문자만 바꿔 BusID를 만들지 않습니다. `DFP-2`, `HDMI-0`, `card1-HDMI-A-1` 사이에도 숫자만으로 일반화할 수 있는 대응 규칙은 없습니다.

### 3.3 물리 연결 확인

```bash
python3 - <<'PY'
from pathlib import Path
for p in sorted(Path('/sys/class/drm').glob('card*-*/status')):
    try:
        edid = p.parent / 'edid'
        size = len(edid.read_bytes()) if edid.exists() else 0
        print(p.parent.name, p.read_text().strip(), 'EDID_bytes=', size)
    except OSError as exc:
        print(p.parent.name, type(exc).__name__)
PY
```

NVIDIA에서 연결을 강제로 표시하면 모니터가 없어도 Xrandr는 `connected`라고 표시할 수 있습니다. DRM 정보·실제 EDID·드라이버 정보·케이블 시험을 함께 확인합니다. EDID 캐시나 KVM·도킹 장치 때문에 판별이 달라질 수 있습니다.

## 4. 적용 경로 선택

| 대상 | 진행 방법 |
|---|---|
| 22.04 + NVIDIA + 단일 출력 | 기준 구성의 값을 치환하고 검증 |
| 24.04 + NVIDIA | Xorg/x11vnc 경로 적용 후 12장 추가 검증 |
| Intel/AMD/가상 GPU | NVIDIA 설정을 설치하지 않고 해당 드라이버 방식 조사 |
| 다중 GPU/혼합 그래픽 노트북 | 실제 출력 담당 GPU와 연산 GPU 구분 |
| 여러 모니터의 주 화면 추적 | 8장 구현·시험 필요 |

비 NVIDIA 환경에서는 드라이버별 가상 출력, 지원되는 EDID 에뮬레이션, 필요 시 물리 더미 플러그를 비교합니다. 독립 Xvnc나 dummy Xorg를 쓰면 **같은 세션 유지와 GPU 가속** 요구를 충족하는지 별도로 확인합니다. 이 자료에는 비 NVIDIA 장비에서 검증된 완성 설정은 없습니다.

## 5. 백업과 작업 파일

### 5.1 복구 경로

설치자는 그래픽 설정 적용에 실패했을 때 원복할 수 있도록 로컬 콘솔 또는 별도의 관리용 SSH 경로를 준비합니다. 이 SSH는 설치·장애 복구용이며, 일반 사용자의 VNC 접속 순서에 포함하지 않습니다. 사용 중인 원격 접속은 적용 전에 유지합니다. 관리용 SSH를 따로 운영할 때만 openssh-server가 필요하며 VNC 자체의 필수 설치 패키지는 아닙니다.

재부팅·로그아웃은 실행 중인 프로그램을 종료할 수 있습니다. 사용자가 이미 허용한 범위는 유지하되, 저장되지 않은 작업이나 적용 시점이 미정이면 마지막 적용 전에 조율합니다.

### 5.2 변경할 파일만 백업

아래 목록 외의 파일을 수정할 경우 **수정 전에 목록에 추가**합니다.

```bash
BACKUP_DIR="$TASK_ROOT/backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR/files"
chmod 700 "$BACKUP_DIR"
for path in \
  /etc/gdm3/custom.conf \
  /etc/X11/xorg.conf.d/20-nvidia-virtual-monitor.conf \
  /etc/systemd/system/x11vnc-physical.service \
  /usr/local/sbin/x11vnc-physical.sh \
  "$TARGET_HOME/.config/systemd/user/adaptive-display-mode.service" \
  "$TARGET_HOME/bin/adaptive-display-mode.sh"
do
  if sudo test -e "$path" || sudo test -L "$path"; then
    sudo cp -a --parents -- "$path" "$BACKUP_DIR/files/"
    printf 'PRESENT\t%s\n' "$path" >> "$BACKUP_DIR/files-before.tsv"
  else
    printf 'ABSENT\t%s\n' "$path" >> "$BACKUP_DIR/files-before.tsv"
  fi
done
systemctl is-enabled x11vnc-physical.service > "$BACKUP_DIR/vnc-enabled-before.txt" 2>&1 || true
systemctl is-active x11vnc-physical.service > "$BACKUP_DIR/vnc-active-before.txt" 2>&1 || true
systemctl --user is-enabled adaptive-display-mode.service > "$BACKUP_DIR/adaptive-enabled-before.txt" 2>&1 || true
systemctl --user is-active adaptive-display-mode.service > "$BACKUP_DIR/adaptive-active-before.txt" 2>&1 || true
printf '%s\n' "$BACKUP_DIR"
```

백업 경로를 기록합니다. 중간 명령이 실패하면 원인을 해결하고 모든 원본·존재 여부 기록이 저장됐는지 확인한 뒤 진행합니다. 기존 암호 파일은 재설치 때문에 덮어쓰지 않습니다. 암호·키·인증 쿠키를 배포 자료에 넣지 않습니다.

### 5.3 편집과 설치 분리

패키지의 `reference/current-pc/` 파일을 대상 PC의 `TASK_ROOT/staging/`에 복사합니다. 복사본에서 값을 수정하고 검토한 뒤 설치합니다. 참고 원본을 `/etc`로 일괄 복사하지 않습니다.

## 6. 패키지와 자동 로그인

### 6.1 패키지

```bash
apt-cache policy x11vnc x11-xserver-utils x11-utils mesa-utils
```

Ubuntu Desktop/GDM이 설치되어 있고 필요한 패키지가 없는 경우:

```bash
sudo apt update
sudo apt install x11vnc x11-xserver-utils x11-utils mesa-utils
```

드라이버가 정상이라면 이 작업 때문에 바꾸지 않습니다. 신규 설치나 드라이버 문제라면 `ubuntu-drivers devices`와 추가 드라이버 도구로 대상 GPU의 권장 패키지를 확인합니다. 기준 PC의 `590.48.01`을 다른 GPU에 고정 설치하지 않습니다. Secure Boot 키 등록이 필요하면 현장 조작 조건을 기록합니다. [Canonical 드라이버 도구](https://github.com/canonical/ubuntu-drivers-common/blob/master/README.md)

### 6.2 GDM 자동 로그인

`/etc/gdm3/custom.conf`의 기존 `[daemon]` 안에서 설정합니다. `TARGET_USER`를 실제 계정으로 바꾸고, 중복 절을 추가하지 않습니다.

```ini
[daemon]
WaylandEnable=false
AutomaticLoginEnable=true
AutomaticLogin=TARGET_USER
```

GDM 이외의 로그인 관리자를 쓰는 PC에는 이 파일을 그대로 적용하지 않습니다.

자동 로그인, 화면 잠금, 시스템 절전, 디스크 암호 해제는 서로 다른 기능입니다.

- 디스크 암호 해제가 필요한 PC는 전원 켜기만으로 접속 가능한지 별도 확인합니다.
- 기존 잠금·절전 정책을 조사하고 원격 복귀를 시험합니다.
- x11vnc의 `-nodpms`가 시스템 전체 suspend를 막는다고 가정하지 않습니다.
- 키링 비밀번호 제거·디스크 암호화 해제는 이 설치의 기본 절차가 아닙니다.

대상 사용자 세션에서 조회:

```bash
gsettings get org.gnome.desktop.session idle-delay
gsettings get org.gnome.desktop.screensaver lock-enabled
gsettings get org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type
gsettings get org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout
```


## 7. NVIDIA 가상 화면과 감지 서비스

### 7.1 Xorg 설정

기준 파일: [20-nvidia-virtual-monitor.conf](reference/current-pc/20-nvidia-virtual-monitor.conf)

핵심 값:

```text
Driver nvidia
BusID PCI:1:0:0
AllowEmptyInitialConfiguration true
ConnectedMonitor DFP-2
UseDisplayDevice DFP-2
```

`AllowEmptyInitialConfiguration`은 모니터 없는 X 서버 시작을 허용합니다. 이 옵션 하나가 VNC용 화면 크기까지 보장하지는 않습니다. `ConnectedMonitor`는 연결 검출을 덮어쓰고 `UseDisplayDevice`는 사용할 출력을 제한합니다. 단일 출력 설정을 다중 모니터 PC에 그대로 적용하면 다른 출력이 빠질 수 있습니다. [NVIDIA 공식 설명](https://download.nvidia.com/XFree86/Linux-x86_64/590.48.01/README/xconfigoptions.html)

작업 순서:

1. GPU·BusID·NVIDIA 출력·Xrandr 출력의 대응을 확인한다.
2. `/etc/X11/xorg.conf`와 `/etc/X11/xorg.conf.d/`의 충돌을 확인한다.
3. 참고 파일을 staging에 복사해 실제 값으로 수정한다.
4. 기본 가상 화면은 1920×1080으로 하고 실제 모니터는 지원 모드를 우선한다.
5. 기준 파일의 `3440x1440R`, `Virtual 5120 2160`, 광범위한 모드 검증 해제를 필수 설정으로 취급하지 않는다.
6. 변경 이유·최종 파일을 검토하고 설치한다.

기준 파일에는 고해상도 설정과 같은 `DFP-2`를 반복한 `MetaModes` 문자열이 남아 있지만 실제 관측 화면은 1920×1080입니다. 이 문자열을 범용 설정으로 전파하지 말고 대상 드라이버의 초기 로그와 실제 모드 목록을 기준으로 정리합니다. 물리 모니터의 주파수 제한을 일괄 해제해 해결하지 않습니다.

검토한 파일을 설치하는 예:

```bash
sudo install -d -m 755 /etc/X11/xorg.conf.d
sudo install -m 644 "$TASK_ROOT/staging/20-nvidia-virtual-monitor.conf" /etc/X11/xorg.conf.d/20-nvidia-virtual-monitor.conf
```

### 7.2 감지 스크립트

기준 파일: [adaptive-display-mode.sh](reference/current-pc/adaptive-display-mode.sh)

```text
약 10초마다 반복
  Xorg 접근 가능 여부 확인
  → 지정 출력의 논리적 연결 상태 확인
  → EDID 또는 실제 모니터 크기 정보 확인
       있음: preferred 해상도 적용
       없음: 1920×1080 @ 59.96Hz 적용
  → 같은 해상도이면 변경하지 않음
```

`59.96`은 기준 장비의 값입니다. 대상 모드 목록의 실제 주사율을 사용합니다. 모드가 없으면 임의 modeline 생성 전에 드라이버와 지원 목록을 확인합니다.

대상 PC에서 검토할 기존 코드의 한계:

- 지정 출력 하나만 처리하며 주 모니터 변경을 추적하지 않는다.
- EDID 캐시·KVM·도킹 장치로 실제 연결 판별이 달라질 수 있다.
- `preferred_mode()`가 일부 출력에서 여러 줄을 반환할 수 있으므로 모드 하나만 선택하는지 확인한다.
- 간헐적 `printf: write error: Broken pipe` 기록이 있다. 문자열 검사로 정리하는 경우 변경 이유를 남긴다.
- 해상도 문자열만 비교하므로 주사율만 다른 경우를 교정하지 않는다.

### 7.3 사용자 서비스

**자동 모니터 감지 경로 전용입니다.** Mac/iPad 수동 선택기 경로에서는 이 서비스를 disabled/inactive로 두고 아래 설치·enable을 건너뜁니다.

값 치환이 필요한 템플릿입니다. systemd의 `Environment=`에서는 셸 변수 `$TARGET_UID` 등을 자동 확장하지 않습니다.

```ini
[Unit]
Description=Adaptive display mode for physical VNC
After=graphical-session.target

[Service]
Type=simple
Environment=DISPLAY=DISPLAY_VALUE
Environment=XAUTHORITY=AUTH_FILE
Environment=ADAPTIVE_OUTPUT=OUTPUT_NAME
Environment=ADAPTIVE_FALLBACK_MODE=1920x1080
Environment=ADAPTIVE_FALLBACK_RATE=FALLBACK_RATE
Environment=ADAPTIVE_INTERVAL=10
ExecStart=TARGET_HOME/bin/adaptive-display-mode.sh
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

`DISPLAY_VALUE`, `AUTH_FILE`, `OUTPUT_NAME`, `FALLBACK_RATE`, `TARGET_HOME`을 실제 값으로 바꿉니다. 스크립트 기본값에도 기준 PC의 계정·UID·출력이 남아 있지 않은지 확인합니다.

```bash
mkdir -p "$TARGET_HOME/bin" "$TARGET_HOME/.config/systemd/user"
install -m 755 "$TASK_ROOT/staging/adaptive-display-mode.sh" "$TARGET_HOME/bin/adaptive-display-mode.sh"
install -m 644 "$TASK_ROOT/staging/adaptive-display-mode.service" "$TARGET_HOME/.config/systemd/user/adaptive-display-mode.service"
bash -n "$TARGET_HOME/bin/adaptive-display-mode.sh"
systemd-analyze --user verify "$TARGET_HOME/.config/systemd/user/adaptive-display-mode.service"
systemctl --user daemon-reload
systemctl --user enable adaptive-display-mode.service
```

여기서는 자동 시작을 등록합니다. 실제 화면 변경이 일어나는 서비스 시작은 11장의 적용 시점에 수행합니다.

## 8. 주 모니터만 공유하는 방법

### 8.1 단일 출력

기준 PC처럼 출력이 하나이면 전체 X 화면 공유와 주 모니터 공유가 일치합니다. 해당 출력의 모니터 연결·해제부터 시험합니다.

### 8.2 여러 출력과 주 모니터 변경

**이 절은 대상 PC에서 구현·검증할 확장 규칙입니다. 첨부 스크립트에 이미 구현된 기능이 아닙니다.**

1. 실제 모니터와 강제 가상 출력을 구분한다. `connected`만으로 판단하지 않는다.
2. 실제 모니터가 있으면 `primary`로 지정된 실제 출력을 선택한다.
3. 주 모니터가 없거나 가상 출력에 지정돼 있으면 작업표의 선호 실제 출력을 선택한다. 선호값도 없으면 일정한 순서를 정해 기록한다.
4. 선택 모니터의 `너비×높이+X+Y` 영역을 읽고 그 영역만 공유한다.
5. 실제 모니터가 없으면 가상 출력을 활성화하고 기본 해상도의 해당 영역을 공유한다.
6. 연결·주 모니터·배치 변경 시 영역을 갱신한다. Xorg와 실행 중인 프로그램을 종료하지 않는다.
7. 가상 출력을 끄기 전에 실제 출력과 공유 영역이 유효한지 확인한다.
8. NVIDIA 정적 설정이 다른 출력을 숨기면 출력 구성부터 조정하고 다시 시험한다.

x11vnc는 `-clip WxH+X+Y`로 공유 영역을 정하고 `-R clip:WxH+X+Y`로 변경할 수 있습니다. `-clip xinerama0`은 Ubuntu의 주 모니터를 의미하지 않습니다. [Ubuntu x11vnc 문서](https://manpages.ubuntu.com/manpages/jammy/man1/x11vnc.1.html)

예: 선택 모니터가 2560×1440, 전체 데스크톱에서 X=1920, Y=0에 있으면:

```text
-clip 2560x1440+1920+0
```

올바른 DISPLAY/XAUTHORITY에서 대상 x11vnc가 하나임을 확인한 후 실행할 변경 명령 예:

```bash
x11vnc -sync -R 'clip:2560x1440+1920+0'
```

이 명령은 화면을 바꾸므로 조사 단계에는 실행하지 않습니다. 같은 DISPLAY에 서버가 여러 개면 원격 제어 채널 충돌을 해결합니다. 회전·배율·오프셋과 마우스 좌표도 시험합니다.

고정 `UseDisplayDevice=DFP-2`만으로 여러 출력 자동 선택을 충족하지 않습니다. 확장 시험 전에는 “단일 출력 확인, 다중 모니터 미검증”으로 기록합니다.

## 9. VNC 인증과 자동 시작

### 9.1 비밀번호

대상 사용자 본인으로 실행합니다. 기존 파일이 있으면 재사용 여부를 확인하고 덮어쓰지 않습니다.

```bash
install -d -m 700 "$TARGET_HOME/.vnc"
x11vnc -storepasswd "$TARGET_HOME/.vnc/physical-passwd"
chmod 600 "$TARGET_HOME/.vnc/physical-passwd"
```

비밀번호는 대화형 프롬프트에 입력하고 명령줄·대화·보고서에 넣지 않습니다. 전통적인 VNC 인증은 첫 8자 제한이 있으므로 긴 비밀번호만으로 보안을 판단하지 않습니다. [Ubuntu x11vnc 문서](https://manpages.ubuntu.com/manpages/noble/man1/x11vnc.1.html)

### 9.2 실행 스크립트

기준 파일: [x11vnc-physical.sh](reference/current-pc/x11vnc-physical.sh)

staging 복사본에서 수정할 항목:

- `-display :0` → 실제 로컬 Xorg DISPLAY.
- 인증 경로의 `/run/user/1000/`, `/home/kmg/`, GDM UID → 실제 값.
- 기준은 읽을 수 있는 첫 인증 파일을 선택한다. 대상에서는 `xdpyinfo` 등으로 그 인증 파일이 해당 DISPLAY에 실제 접근되는지 확인하고 재시도하도록 개선한다.
- `-rfbauth` → 대상 사용자의 비밀번호 파일.
- `-rfbport` → 선택한 포트.
- `-listen 0.0.0.0` → 현재와 같은 직접 VNC 접속을 위한 기본값으로 유지. 사용자가 연결 방식을 별도로 바꾸기로 한 경우에만 변경.
- 다중 출력 PC → 8장의 주 모니터 영역 선택 반영.

`-forever`는 클라이언트 종료 후 서버를 유지하고 `-shared`는 동시 공유를 허용합니다. `-input KMBCF`에는 키보드·마우스·클립보드와 지원되는 파일 전송 입력이 포함됩니다. 사용할 기능과 뷰어 호환성을 확인합니다.

`-noxdamage`, `-noshm`, `-wireframe`, `-fixscreen V=10` 등은 기준 PC의 조정값입니다. 모든 장비에서 최적이라고 가정하지 않습니다. `-xrandr resize` 명시를 검토할 수 있으며 크기 변경 때 뷰어 동작은 실제 시험합니다. [Ubuntu x11vnc 옵션](https://manpages.ubuntu.com/manpages/noble/man1/x11vnc.1.html)

실행 계정의 `.x11vncrc`가 추가 옵션을 넣을 수 있습니다. 그 파일을 확인하거나 `-norc`로 사용할 옵션을 명확히 합니다. 기준 서비스는 root 실행이므로 설치 스크립트를 일반 사용자가 덮어쓸 수 없게 합니다.

### 9.3 시스템 서비스

기준 서비스에서 HOME 환경의 불필요한 재지정을 생략한 예입니다. 기본 시스템 서비스 계정은 root입니다.

```ini
[Unit]
Description=x11vnc physical display sharing
After=display-manager.service
Requires=display-manager.service

[Service]
Type=simple
ExecStart=/usr/local/sbin/x11vnc-physical.sh
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo install -m 755 "$TASK_ROOT/staging/x11vnc-physical.sh" /usr/local/sbin/x11vnc-physical.sh
sudo install -m 644 "$TASK_ROOT/staging/x11vnc-physical.service" /etc/systemd/system/x11vnc-physical.service
sh -n /usr/local/sbin/x11vnc-physical.sh
sudo systemd-analyze verify /etc/systemd/system/x11vnc-physical.service
sudo systemctl daemon-reload
sudo systemctl enable x11vnc-physical.service
```

Bash 구문을 추가했다면 shebang과 검사를 `bash`로 맞춥니다. 기준 PC의 별도 `:1`용 `remote-vnc.service`와 `x11vnc-physical-policy.service`는 비활성입니다. 재현을 위해 추가 활성화하지 않습니다.

## 10. VNC 뷰어로 직접 접속하기 — 기본 방식

### 10.1 사용자가 하는 일

1. 대상 PC가 켜져 있고 자동 로그인·VNC 자동 시작이 완료될 때까지 기다린다.
2. 접속할 기기에서 VNC 뷰어를 연다.
3. 대상 PC의 접속 주소와 VNC 포트를 입력한다.
4. VNC 비밀번호를 입력하고 화면을 사용한다.

**SSH 접속이나 SSH 터널 실행, VPN 로그인은 기본 사용 절차에 포함하지 않습니다.**

```text
내부망: VNC 뷰어 → 대상 PC의 내부 IP:5900
외부망: VNC 뷰어 → 공인 IP 또는 DDNS:외부 포트 → 대상 PC의 VNC 포트
```

위 그림의 화살표는 실제 연결 경로입니다. 대상 PC가 공유기 뒤에 있으면 공유기가 외부 포트를 내부 PC로 전달합니다. 이 네트워크 설정은 설치자가 준비하며, 사용자가 매번 중간 명령을 실행하지 않습니다.

### 10.2 서버의 기본 수신 설정

기준 PC와 같은 직접 접속의 기본 옵션은 다음과 같습니다.

```text
-rfbport 5900
-listen 0.0.0.0
-rfbauth 대상사용자의_VNC_비밀번호파일
```

`0.0.0.0`은 서버가 수신할 인터페이스를 뜻합니다. 뷰어의 접속 주소에는 실제 내부 IP·공인 IP·DDNS 호스트명을 입력합니다. 외부 포트와 서버 내부 포트는 다를 수 있습니다.

기본 설치에서 `-localhost`로 바꾸지 않습니다. 그 옵션은 VNC를 해당 PC 내부에서만 접근하게 만들어 사용자가 기대하는 직접 접속 경로를 바꿉니다. IPv6 수신 여부도 확인하여 의도한 주소에서만 접근되도록 기존 네트워크 정책과 맞춥니다.

### 10.3 설치자가 한 번 준비할 네트워크 설정

```bash
ss -lntp | rg ':5900\b'
ip -brief address
sudo ufw status verbose
```

1. 대상 PC의 VNC 포트가 실제로 열리고 내부망 뷰어에서 접속되는지 확인한다.
2. DHCP 예약 또는 기존 고정 주소 방식으로 대상 PC의 내부 IP를 유지한다.
3. 공유기를 사용하는 환경이면 공인 주소와 전달할 외부 TCP 포트를 확인한다.
4. 공유기에 `외부 TCP 포트 → 대상 PC 내부 IP:5900` 전달 규칙을 설정한다. 내부 VNC 포트를 다르게 정했다면 그 값을 사용한다.
5. PC·공유기 방화벽에서 의도한 원격 기기의 해당 VNC 연결을 허용한다. 기존 다른 서비스의 규칙은 유지한다.
6. 주소가 변하는 환경이라면 DDNS 또는 실제 주소 확인 방법을 기록한다.
7. 테더링 등 실제 외부망에서 SSH·VPN 없이 VNC 뷰어로 접속해 화면과 입력을 시험한다.

네트워크 관리자 권한이 없거나 이중 NAT·통신사 NAT 때문에 경로가 성립하지 않으면, 부족한 권한·주소·전달 규칙을 정확히 기록하고 그 부분을 요청합니다. Codex가 임의로 SSH 터널·VPN 방식으로 바꾸고 기본 목표를 완료했다고 보고하지 않습니다.

### 10.4 접속 정보를 사용자에게 전달

| 항목 | 기록 내용 |
|---|---|
| 내부망 접속 | 대상 PC 내부 IP / 내부 VNC 포트 |
| 외부망 접속 | 공인 IP 또는 DDNS / 외부 TCP 포트 |
| 포트 전달 | 외부 포트 → 내부 IP:VNC 포트 |
| 내부 주소 유지 | DHCP 예약 또는 고정 주소 |
| 허용 원격 기기 | 적용 중인 출발지·방화벽 정책 |
| 뷰어 설정 | 제품 이름, 서버 주소, 포트, 필요한 호환 옵션 |

뷰어의 서버 주소·포트 칸에는 전달받은 값을 입력합니다. 하나의 입력 칸만 있는 제품은 해당 제품의 주소 표기법을 따릅니다. 기본 절차에서 뷰어 주소를 `127.0.0.1:15900`으로 안내하지 않습니다. 그것은 별도 SSH 터널을 선택했을 때의 예입니다.

비밀번호는 문서에 평문으로 적지 않고 사용자가 설정한 VNC 비밀번호를 사용합니다. 기준 PC의 VNC 실행 옵션에는 자체 TLS가 없으므로, 직접 접속 구성을 재현했다는 사실과 통신 암호화 여부는 구분해서 기록합니다.

### 10.5 기준 PC와 선택 부록

기준 PC에는 외부 공인 IP에서 VNC를 사용한 로그가 있습니다. 공유기의 정확한 전달 규칙은 조사하지 않았으므로 새 PC에서 따로 확인합니다. 기준 PC의 Tailscale은 `NeedsLogin`이고 VPN IP가 없어 현재 VNC 사용의 전제 조건이 아닙니다.

사용자가 추후 연결 방식을 변경하려고 선택하는 경우에만 [SSH·VPN 선택 부록](OPTIONAL-REMOTE-ACCESS.md)을 참고합니다. 이 부록은 기본 설치·접속 시험의 필수 단계가 아닙니다.


## 11. 적용과 기본 확인

### 11.1 적용 전

- 모든 자리표시자를 실제 값으로 치환했다.
- 사용자·UID·DISPLAY·인증 경로·GPU·출력 포트가 대상 PC와 일치한다.
- 백업, 변경 내용, 기존 서비스 상태를 기록했다.
- VNC 수신 범위와 외부 접속 방법을 정했다.
- 저장되지 않은 작업과 적용 시점을 정리했고 로컬 콘솔 또는 관리용 SSH 복구 경로가 있다.

Xorg/GDM 설정은 저장만으로 현재 세션에 적용되지 않습니다. 합의된 시점에 재부팅해 자동 시작까지 확인하는 것을 기본으로 합니다.

```bash
sudo reboot
```

이 명령은 실제 재부팅입니다. 문서를 읽거나 준비하는 단계에서는 실행하지 않습니다. 기존 Xorg에 VNC만 추가했다면 Xorg 설정 적용·재부팅 시험과 구분해 기록합니다.

### 11.2 재부팅 후

사용자는 먼저 10.1절대로 VNC 뷰어에서 대상 주소·포트로 직접 접속합니다. 설치자가 아래 상태 명령을 확인할 때는 로컬 터미널 또는 관리용 SSH를 사용할 수 있습니다. 이 조회를 해야만 VNC가 열리는 것은 아닙니다.

```bash
loginctl list-sessions
systemctl status x11vnc-physical.service --no-pager
systemctl --user status adaptive-display-mode.service --no-pager
ss -lntp | rg ':5900\b'
journalctl -u x11vnc-physical.service -b --no-pager -n 60
journalctl --user -u adaptive-display-mode.service -b --no-pager -n 60
```

아래는 기준 PC의 예시입니다. 실제 DISPLAY와 인증 경로로 치환합니다.

```bash
env DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority xrandr --query
```

기대 결과:

- 대상 사용자의 자동 로그인 세션이며 `Type=x11`이다.
- VNC가 실행 중이다. 자동 모니터 경로에서는 감지 서비스도 실행 중이고, Mac/iPad 수동 경로에서는 감지 서비스가 disabled/inactive여야 한다.
- 실제 또는 가상 화면에 유효한 너비·높이가 있다.
- 의도한 주소·포트만 수신한다.
- 외부 뷰어에서 화면과 입력을 사용할 수 있다.

### 11.3 서비스만 별도 적용

아래 예시는 자동 모니터 감지/VNC 서비스 자체를 수정한 경우입니다. **Mac/iPad 선택기만 설치하는 경우는 이 절 전체를 건너뜁니다.**

이미 Xorg가 준비돼 있고 서비스·스크립트만 바꾼 경우, 현재 원격 작업을 확인하고 해당 서비스만 적용합니다.

```bash
systemctl --user daemon-reload
systemctl --user restart adaptive-display-mode.service
sudo systemctl daemon-reload
sudo systemctl restart x11vnc-physical.service
```

VNC 재시작은 원격 연결을 끊고 감지 서비스는 화면을 바꿀 수 있습니다. `systemctl restart gdm`은 데스크톱 자체를 종료할 수 있으므로 단순 연결 오류의 첫 해결책으로 쓰지 않습니다.

## 12. Ubuntu 24.04 적용 시 차이

24.04의 기본 GNOME 원격 공유는 RDP로 안내됩니다. 이 문서의 Xorg/x11vnc 경로는 별도로 준비합니다. [Ubuntu 공식 원격 공유 문서](https://ubuntu.com/desktop/docs/en/24.04/how-to/share-your-desktop-remotely/)

1. x11vnc 패키지 후보와 설치 버전을 확인한다. [24.04 x11vnc 문서](https://manpages.ubuntu.com/manpages/noble/man1/x11vnc.1.html)
2. `WaylandEnable=false` 적용 후 실제 세션이 `x11`인지 확인한다.
3. GDM UID, Xauthority, DISPLAY 번호를 다시 조사한다.
4. 대상 GPU에 맞는 NVIDIA 드라이버를 선택한다.
5. 기존 GNOME 원격 데스크톱 등의 포트·역할을 기록한다. 충돌이 없으면 이름만 보고 끄지 않는다.
6. 모니터 없는 부팅, 연결·해제, 잠금, 주 모니터 변경, 외부 접속을 재시험한다.

**22.04의 관측 결과를 24.04 검증 결과로 복사하지 않습니다.**

## 13. 실제 동작 시험

[CHECKLIST.md](CHECKLIST.md)에 `통과 / 실패 / 미실시 / 해당 없음`을 기록합니다. 미실시는 실패가 아니지만 완료된 기능으로 계산하지 않습니다.

| 시험 | 방법 | 통과 기준 |
|---|---|---|
| 모니터 없는 부팅 | 케이블 없이 재부팅 | 현장 로그인 없이 외부 VNC 접속·가상 화면 표시 |
| 모니터 있는 부팅 | 모니터 연결 후 부팅 | 로컬 주 화면과 VNC가 동일 |
| 실행 중 연결 | 터미널·편집기를 띄운 채 모니터 연결 | 화면 전환·기존 프로그램 유지 |
| 실행 중 해제 | 같은 상태에서 모니터 제거 | 가상 화면 전환·프로그램 유지 |
| 주 모니터 변경 | 모니터 2개에서 primary 변경 | 새 주 모니터만 공유 |
| 다른 포트 | 사용할 HDMI·DP별 시험 | 선택 규칙대로 공유 |
| 크기·좌표 | 해상도·배치·회전 변경 | 공유 영역·마우스 클릭 위치 일치 |
| 재접속 | VNC 닫고 다시 연결 | 같은 세션·프로그램 유지 |
| 입력 | 한/영·특수키·드래그·클립보드 | 실제 사용할 뷰어에서 정상 동작 |
| 잠금·절전 | 합의한 유휴·잠금 정책 시험 | 정한 정책대로 원격 복귀 |
| 외부망 | 테더링 등 별도 네트워크 | SSH·VPN 없이 VNC 뷰어에서 직접 인증·화면·입력 성공 |
| GPU | 필요한 3D 앱과 렌더러 조회 | 필요한 가속·렌더링 동작 확인 |
| 네트워크 복귀 | 허용된 범위에서 재연결 시험 | 자동 복구 또는 복구 절차 확인 |

기준 감지 주기는 10초지만 실제 전환에는 드라이버 감지·설정·뷰어 갱신 시간이 더해집니다. 항상 10초 이내라고 보장하지 말고 측정값을 기록합니다. 프로그램 유지와 VNC 소켓의 무중단 연결은 구분합니다. 화면 크기 변경으로 뷰어 재접속이 필요하면 명시합니다.

`nvidia-smi`만으로 데스크톱 OpenGL 가속을 판정하지 않습니다. 공유 대상 Xorg에서 `glxinfo -B`를 실행해 렌더러가 `llvmpipe` 등 소프트웨어인지 확인하고 실제 사용할 앱도 시험합니다. 로봇·장비 앱은 장치 동작을 유발하지 않는 화면 표시 범위에서 확인합니다.

## 14. 문제 해결

| 증상 | 먼저 확인 | 다음 조치 |
|---|---|---|
| 접속 거부 | 서비스·포트·바인딩 | 해당 로그와 주소 확인 |
| 연결되나 검은 화면 | Xorg·인증·화면 크기 | 올바른 DISPLAY/XAUTHORITY로 조회 |
| 모니터 제거 후 화면 사라짐 | 가상 출력·유효 모드 | 드라이버·감지 스크립트 실패 원인 확인 |
| Can't open display | SSH 환경인지·세션 준비 여부 | 로컬 Xorg 값 사용; 인증 내용 출력 금지 |
| 부팅 후 접속 불가 | 자동 로그인·절전·암호 해제 | 마지막 부팅 로그·서비스 enable 확인 |
| 다른 모니터가 보임 | primary·전체 공유·clip 영역 | 8장 선택 규칙 확인 |
| 모든 출력이 연결처럼 보임 | 강제 연결·EDID 캐시 | DRM·드라이버·물리 시험 교차 확인 |
| 주사율 적용 실패 | 지원 모드 목록 | 기준의 59.96을 강요하지 않고 실제 값 사용 |
| 서버 내부에서만 VNC 접속됨 | -localhost 적용 여부 | 기본 직접 접속 수신 설정으로 복구하고 포트 확인 |
| 로컬만 되고 외부는 안 됨 | 공유기·NAT·방화벽 | 실제 외부망에서 경로별 시험 |
| 마우스 좌표 어긋남 | 배율·회전·clip | 실제 배치와 공유 영역 비교 |
| 선택한 해상도가 몇 초 후 되돌아감 | 자동 watcher·이를 시작하는 서비스 | 수동 경로는 disabled/inactive 유지; DISPLAY-PROFILES 참고 |
| iPad 글씨가 흐림·아래 잘림 | VNC scale·실제 해상도·뷰어 배율 | 1600×1050, scale=1, 비율 유지·화면에 맞춤 확인 |
| 그래픽 앱이 느림 | 렌더러·화면 크기·네트워크 | GPU 가속과 갱신 옵션을 분리해 조사 |

로그는 필요한 범위만 읽습니다.

```bash
journalctl -u x11vnc-physical.service -b --no-pager -n 80
journalctl --user -u adaptive-display-mode.service -b --no-pager -n 80
tail -n 50 "$TARGET_HOME/.local/state/adaptive-display-mode.log"
```

Xorg 로그는 매우 클 수 있으므로 전체를 출력하지 않습니다. 초기 설정 조회 예:

```bash
sed -n '1,250p' "$TARGET_HOME/.local/share/xorg/Xorg.0.log"
```

실제 로그 경로·X 서버 번호가 다르면 먼저 파일을 찾습니다. 원인 기록 없이 재시작만 반복하지 않습니다.

## 15. 원복

SSH 또는 로컬 콘솔에서 진행합니다. `BACKUP_DIR`를 5장에서 기록한 실제 경로로 설정합니다. 이후 다른 작업자가 변경한 파일이 있으면 먼저 차이를 확인하고 그 변경까지 덮어쓰지 않습니다.

1. 이번에 적용한 서비스만 중지한다.
2. 이번에 새로 enable한 서비스는 unit 파일 제거 전에 disable한다. 기존 enabled였다면 그 상태를 나중에 복원한다.
3. `files-before.tsv`를 검토한다.
4. PRESENT 파일은 백업에서 원래 경로로 복원한다.
5. ABSENT 파일은 이번 작업이 새로 만든 해당 파일만 제거한다.
6. systemd를 다시 읽고 기록된 enabled/active 상태를 개별 복원한다.
7. Xorg/GDM을 되돌렸다면 합의된 시점에 재부팅하고 접속을 확인한다.

예:

```bash
sudo systemctl stop x11vnc-physical.service
systemctl --user stop adaptive-display-mode.service
cat "$BACKUP_DIR/files-before.tsv"
```

서비스 상태 기록에 따라 필요한 disable을 먼저 수행하고, 목록을 검토한 뒤 파일을 복원합니다.

```bash
while IFS=$'\t' read -r state path; do
  case "$state" in
    PRESENT)
      sudo cp -a -- "$BACKUP_DIR/files$path" "$path"
      ;;
    ABSENT)
      sudo rm -f -- "$path"
      ;;
    *)
      printf 'Unknown backup state: %s\n' "$state" >&2
      break
      ;;
  esac
done < "$BACKUP_DIR/files-before.tsv"
sudo systemctl daemon-reload
systemctl --user daemon-reload
```

원복 명령 실패 시 다음 단계로 넘어가지 말고 원인을 해결합니다. 디렉터리 전체를 삭제하지 않습니다. `*-enabled-before.txt`, `*-active-before.txt`에 맞춰 enable/disable 및 start/stop을 복원합니다. 원래 없던 서비스는 중지·등록 해제한 상태로 둡니다.

드라이버·방화벽·공유기·GNOME 설정도 변경했다면 파일 원복만으로 되돌아가지 않습니다. 작업표의 해당 항목별 원복을 수행합니다. SSH를 끊는 네트워크 원복을 먼저 하지 않습니다.

## 16. 완료 보고

```text
대상 PC / OS / GPU / 드라이버:
사용자 / Xorg DISPLAY / 인증 파일 경로:
실제 모니터 선택 규칙 / 가상 출력 / 기본 해상도:
VNC 주소·포트 / 외부 접속 경로:
자동 로그인 / 자동 시작 / 잠금·절전 정책:
변경한 파일·패키지·네트워크 규칙:
백업 경로 / 원복 방법:
통과한 시험:
실패한 시험과 관측된 원인:
실시하지 못한 시험:
현재 사용 가능한 범위:
```

비밀번호·인증 쿠키·개인키·토큰을 넣지 않습니다. 최종 설정 복사본과 이 보고서를 대상 PC 작업 폴더에 보관합니다.
