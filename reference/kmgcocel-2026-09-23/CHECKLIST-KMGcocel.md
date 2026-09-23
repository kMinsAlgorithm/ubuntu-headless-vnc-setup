# KMGcocel 설정·검증 기록

양식: `~/ubuntu-headless-vnc-setup/CHECKLIST.md` · 작성일: 2026-09-23 · 작업자: Claude Code (사용자 kmg 승인·sudo 입력)

## 1. 장비와 작업 범위

| 항목 | 대상 PC 값 |
|---|---|
| PC 이름 / 작성일 / 작업자 | KMGcocel / 2026-09-23 / Claude Code + kmg |
| Ubuntu 버전 / 커널 / 데스크톱 | Ubuntu 24.04.5 LTS / 7.0.0-34-generic / GNOME (ubuntu) |
| GPU / 출력 담당 GPU / 드라이버 | NVIDIA GeForce RTX 5080 (GB203) 단일 GPU / nvidia-driver-595-open 595.91.07 (변경 안 함) |
| 사용자 / UID / 홈 | kmg / 1000 / /home/kmg |
| 로그인 관리자 / 세션 종류 | GDM3 / x11 (gdm-x-session, 사용자 소유 Xorg) |
| DISPLAY / XAUTHORITY 경로 | 작업 시점 `:1` / `/run/user/1000/gdm/Xauthority`. 재부팅 후 번호가 바뀔 수 있어 실행 스크립트가 매번 탐색 |
| GPU BusID | `PCI:1:0:0` (Xorg 로그 `GPU-0 at PCI:1:0:0`) |
| NVIDIA 출력 ↔ Xrandr 출력 ↔ DRM 대응 | `DFP-0` ↔ `HDMI-0` ↔ `card1-HDMI-A-1` (nvidia-settings -q dpys로 확인) |
| 실제 모니터 수 / 주 모니터 | 1대, LG ULTRAWIDE 3440×1440 @100Hz, HDMI-0 primary |
| 가상 출력 / 기본 해상도 / 주사율 | HDMI-0 강제 연결 + LG EDID 고정 (다음 부팅부터). 부팅 기본은 EDID 선호 모드 3440×1440 |
| 주 모니터 부재 시 선택 규칙 | 단일 출력 HDMI-0 고정. 다중 모니터 자동 선택은 구현·검증하지 않음 |
| 정책 선택: 자동 모니터 / 수동 Mac·iPad | **수동 Mac·iPad** (사용자 선택) |
| 감지 방식 / 주기 / enable·active 상태 | adaptive-display-mode.service 미설치 (not-found / inactive) |
| 수동 프로필 / 서버 화면 / VNC scale | ipad 1600×1050 · mac 1920×1080 / scale=1. 현재 화면 3440×1440, 프로필 미적용 |
| VNC 프로그램 / 버전 / 서비스 이름 | x11vnc 0.9.16-10 / `x11vnc-physical.service` (시스템 서비스, **User=kmg**로 실행) |
| VNC 바인딩 / 포트 / IPv6 | 0.0.0.0:**55100** / IPv6 [::]:55100만 (5900 추가 수신 제거 확인) |
| 뷰어 프로그램 / 접속 기기 OS | 미확인 (Mac 화면 공유, iPad RVNC 예정) |
| 자동 로그인 / 잠금 / 절전 | kmg 자동 로그인 (다음 부팅부터) / 유휴 300초 후 잠금 켜짐 / AC 자동 절전 시간 0 = 사용 안 함 |
| 디스크 암호 해제 등 부팅 시 입력 | LUKS 없음. Secure Boot 켜짐 (드라이버는 이미 동작 중) |
| 작업 승인 범위 / 적용 시점 | 설치·설정까지 진행. 재부팅은 사용자가 직접 |

## 2. 외부 접속과 복구

| 항목 | 값 |
|---|---|
| 사용자 접속 방식 | VNC 뷰어에서 대상 주소·포트로 직접 접속 |
| 내부망 주소 / 포트 | <내부 IP> : 55100 |
| 외부 주소 / 외부 포트 | 미확인. 공유기 전달 규칙 필요: 외부 TCP 포트 → <내부 IP>:55100 |
| 내부 주소 유지 방식 | 미확인. 공유기에서 DHCP 예약 권장 |
| NAT 전달 규칙 / 확인한 관리자 | 미설정 / 사용자 작업 필요 |
| 설치자의 복구 경로 | 로컬 콘솔, openssh-server (22번 포트, active) |
| 암호화 구간 | VNC 자체 TLS 없음. VNC 인증은 앞 8자만 사용 |
| IPv4·IPv6 방화벽 상태 | ufw ENABLED=no. 공유기 방화벽 미확인 |
| VNC 뷰어 접속 전 별도 명령이 필요한가? | 필요 없음 |
| 기타 원격 서비스 | gnome-remote-desktop 시스템 서비스 active (RDP), 3389 수신 없음. 변경하지 않음 |

## 3. 변경과 백업

시스템 백업: `~/headless-vnc-setup/backup-20260923-222020/` (`files-before.tsv`, 서비스 이전 상태)

| 변경 대상 | 변경 전 | 변경 내용 | 원복 |
|---|---|---|---|
| `/etc/gdm3/custom.conf` | PRESENT (기본값) | `WaylandEnable=false`, `AutomaticLoginEnable = true`, `AutomaticLogin = kmg` | rollback-system.sh |
| `/etc/X11/xorg.conf.d/20-nvidia-virtual-monitor.conf` | ABSENT | `ConnectedMonitor DFP-0`, `CustomEDID`, `AllowNonEdidModes`, iPad modeline 2개 | 〃 (삭제) |
| `/etc/X11/edid/lg-ultrawide-dfp0.bin` | ABSENT | 현재 LG 모니터 EDID 256바이트 (체크섬 정상) | 〃 (삭제) |
| `/usr/local/sbin/x11vnc-physical.sh` | ABSENT | kmg Xorg 탐색, 포트 55100, MIT-SHM 사용, `-norepeat -1`, `-nomodtweak`, `-no6 -rfbportv6` (설계 메모) | 〃 (삭제) |
| `/etc/systemd/system/x11vnc-physical.service` | ABSENT, not-found | enabled + active, `User=kmg` | 〃 (disable + 삭제) |
| 패키지 | x11vnc·mesa-utils 없음 | `apt install x11vnc mesa-utils` | 필요하면 `apt remove` |
| VNC 비밀번호 | 없음 | `~/.vnc/physical-passwd` (600, 사용자가 직접 입력) | 문서에 기록 안 함 |
| 해상도 선택기 GUI·CLI·바탕화면 항목 | 없음 | `~/.local/share/vnc-resolution-switcher/`, 바탕화면 `화면 해상도 선택.desktop` | 영수증 `~/.local/state/vnc-resolution-switcher/install-backups/20260923T132728.092395Z/` |
| VNC 키보드 모드 | 없음 | `~/.local/share/vnc-keyboard-mode/`, 바탕화면 아이콘, **켜짐**(vnc 모드, 재적용 서비스 active), 클립보드 보호 켜짐. Option(Meta)→Super 추가 | 영수증 `~/.local/state/vnc-keyboard-mode/install-backups/20260923T132733.139749Z/` |
| GNOME 스크린샷 단축키 | `screenshot=['<Shift>Print']`, `show-screenshot-ui=['Print']` | `<Control><Shift>3` (전체), `<Control><Shift>4` (선택 UI) 추가. Mac Cmd+Shift+3/4 대응 | `gsettings set org.gnome.shell.keybindings screenshot "['<Shift>Print']"` / `show-screenshot-ui "['Print']"` |
| GNOME 잠금·절전, 드라이버, 방화벽 | — | 변경 없음 | — |

원복: `sudo bash ~/headless-vnc-setup/rollback-system.sh ~/headless-vnc-setup/backup-20260923-222020` (패키지와 비밀번호 파일은 그대로 둠)

설계 메모:
- 2026-09-23 성능·입력 조정: 기준 PC 옵션 `-noshm`(화면 읽기 426 vs 2336 MB/s), `-speeds 6,1500,60`, `-fixscreen V=10`, `-repeat`을 뺐습니다. root x11vnc는 kmg의 Xorg에 MIT-SHM을 붙이지 못해(`X_ShmAttach BadAccess`) 반복 종료됐고, 서비스를 `User=kmg`로 바꿔 해결했습니다. GNOME 컴포지터 경고 때문에 `-noxdamage`는 유지했습니다. `-repeat`은 화면 갱신이 키 뗌 신호를 늦추면 서버가 Tab을 계속 반복하게 만들어서 `-norepeat -1`로 바꿨습니다.
- `-nomodtweak`: Cmd가 눌려 있으면 Mac은 Shift가 적용되지 않은 `3`을 보내고, 기본 modtweak는 그 순간 Shift를 떼서 Ctrl+3으로 만들었습니다 (수정키와 3·4만 걸러 관찰). 먼저 `x11vnc -R nomodtweak`으로 임시 적용해 사용자 확인을 받은 뒤 실행 스크립트에 넣었습니다.
- kmg로 실행하면 GDM 로그인 화면 인증 파일을 읽을 수 없습니다. 원격에서 로그아웃하면 VNC로 다시 로그인할 수 없고, 로컬 콘솔이나 SSH가 필요합니다.
- 원래 드라이버는 EDID에 없는 모드를 거부했습니다. 2026-09-23 현재 세션에서 `xrandr --addmode HDMI-0 1600x1050`을 시험했더니 `BadMatch`가 나왔고, 시험한 모드는 바로 지웠습니다. 그래서 `AllowNonEdidModes`를 넣고 Xorg 설정에 모드라인을 등록했습니다.
- 모니터 없이 부팅해도 HDMI-0에 같은 LG 모드 목록이 생기도록 EDID를 고정했습니다. HDMI-0에 다른 모니터를 꽂아도 LG로 인식하므로, 그때는 `CustomEDID` 줄을 지워야 합니다.
- x11vnc 0.9.16은 `-rfbport`와 따로 IPv6 5900을 한 번 더 엽니다. 55199 포트 격리 인스턴스로 확인했고, `-no6 -rfbportv6 PORT`로 한 포트만 열립니다.

## 4. 검증

| ID | 시험 | 결과 | 실제 관측·미실시 사유 |
|---|---|---|---|
| T01 | 스크립트 구문·서비스 정의 검증 | 통과 | `sh -n`, `bash -n`, `systemd-analyze verify`, 레포 unittest 42개 OK |
| T02 | 자동 로그인 Xorg 세션 | 미실시 | 재부팅 전 |
| T03 | 모니터 없는 부팅 후 외부 VNC 접속 | 미실시 | 재부팅·케이블 분리 필요 |
| T04 | 모니터 있는 부팅 후 동일 화면 | 미실시 | 재부팅 필요 |
| T05~T08 | 자동 모니터 전환 / 다중 모니터 | 해당 없음 | 수동 선택기 정책 (watcher 없음) |
| T09 | 화면 크기·배치·클릭 좌표 | 미실시 | 사용자가 LAN에서 Mac 화면 공유 접속 성공 보고. 좌표 정밀 확인은 안 함 |
| T10 | VNC 재접속 후 같은 프로그램 | 미실시 | 뷰어 접속 필요 |
| T11 | 한/영·특수키·드래그·클립보드 | 부분 | Mac 화면 공유 관측: Cmd→Alt_L(→Ctrl), Option→Meta_L(→Super), Ctrl→Control_L, Fn+←→Home. Mac Ctrl+←는 Mac이 가로챔. modtweak가 Shift를 떼는 문제(한국어 입력 대문자, 터미널 Cmd+Shift+C/V, Cmd+Shift+3/4)를 `-nomodtweak`으로 해결, **사용자 Mac 확인 통과** (23:42 스크린샷 2개 저장). Cmd+Tab은 macOS가 가로챔. Option+←/Option+Tab은 사용자 확인 대기. iPad 화면 키보드 대문자는 미검증 |
| T12 | 잠금·유휴 후 원격 복귀 | 미실시 | |
| T13 | SSH·VPN 없이 외부망에서 직접 접속 | 미실시 | 공유기 포트 전달 미설정 |
| T14 | 의도하지 않은 외부 접근 차단 | 부분 | 서버 수신은 55100(IPv4·IPv6)만 확인. 공유기 쪽 미확인 |
| T15 | VPN | 해당 없음 | |
| T16 | OpenGL 렌더러 | 통과 | `:1`에서 `glxinfo -B`: direct rendering Yes, NVIDIA GeForce RTX 5080 (재부팅 후 재확인 필요) |
| T18 | 로컬 콘솔·관리용 SSH 복구 | 준비됨 | sshd active, rollback 스크립트 작성 (실제 원복은 미실시) |

| ID | 시험 | 결과 | 실제 관측 |
|---|---|---|---|
| P01 | 의존성·오프라인 검사 / 설치본 지문 | 통과 | `--check` missing 없음, 영수증 sha256 기록 |
| P02 | watcher disabled/inactive / 다른 서비스 재시작 여부 | 통과 | adaptive·policy 서비스 모두 not-found. GDM/Xorg 재시작 없음 |
| P03 | iPad 1600×1050 / scale=1 / 35초 유지 | 미실시 | 1600×1050은 Xorg 설정이 적용된 재부팅 뒤에만 가능 (현재 드라이버가 거부) |
| P04~P07 | 실제 iPad·Mac 화면, 미리보기 복구, 창 조정 | 미실시 | 재부팅·실제 기기 필요 |
| P08 | CLI status | 통과 | `desktop 3440x1440, HDMI-0, 100Hz, vnc_scale 1, native_pixels true` |
| P09 | 파일 백업·서비스 이전 상태 영수증 | 통과 | 위 3절 경로 |
| P10 | 재부팅 후 아이콘으로 다시 선택 | 미실시 | |

## 5. 최종 인계

- 현재 사용 가능한 기능: 내부망 `<내부 IP>:55100`에서 현재 데스크톱 VNC 공유 (서버 수신 확인, 실제 뷰어 접속은 미확인), 부팅 시 VNC 자동 시작 등록, 선택기·키보드 모드 아이콘
- 적용했지만 아직 시험하지 못한 항목: 자동 로그인, Wayland 끄기, 가상 모니터, iPad 1600×1050 (모두 재부팅 후)
- 사용자에게 필요한 다음 행동: (1) 뷰어로 내부망 접속 시험 (2) 원하는 시점에 재부팅 (3) 외부 접속이 필요하면 공유기 포트 전달과 DHCP 예약
- 재부팅 후 마지막 해상도 선택을 자동 복원하는 기능은 없습니다 (현재 X 세션에서만 유지).
- 설정 복사본: `~/headless-vnc-setup/staging/`
