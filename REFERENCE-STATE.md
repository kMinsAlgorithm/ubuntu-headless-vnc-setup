# 기준 PC에서 확인한 상태

아래 1~5절의 조사일: 2026-09-15 · 조사 방식: 설정 파일·프로세스·서비스·화면 정보·기존 로그의 읽기 전용 확인.

## 최신 변경 — 2026-09-17 Mac/iPad 수동 선택

| 항목 | 현재 기준값 |
|---|---|
| 승인된 iPad 화면 | **1600×1050**, HDMI-0, 약 59.97Hz |
| VNC 배율 | **1**, 원본 픽셀 전송 |
| 다른 선택지 | Mac 1920×1080, iPad 1184×824 / 1024×768 |
| 자동 감지 서비스 | `adaptive-display-mode.service` **disabled/inactive** |
| 정책 보조 서비스 | `x11vnc-physical-policy.service` disabled/inactive 유지 |
| VNC 서비스 | 기존 `x11vnc-physical.service` 계속 사용 |
| 바탕화면 선택기 | `화면 해상도 선택.desktop` |
| 복구 | 확인 20초, 취소·시간 초과·UI 종료 시 기존 화면/배율/창 배치 복구 시도 |

사용자는 iPad에서 원본 전송의 선명도를 확인했고, 화면 높이를 1050으로 낮춘 뒤 “지금 딱 적절한듯? 이만하면 됐어.”라고 확인했습니다. 1600×1200 + 3/5 서버 축소 전송은 채택하지 않았습니다. 실제 x11vnc 로그에서도 마지막 framebuffer 갱신 1600×1050을 확인했습니다.

수동 해상도를 자동 서비스가 10초 주기로 덮어쓰는 충돌을 확인해 서비스를 중지/비활성화했습니다. 기존 서비스 정의와 스크립트 파일은 보존했습니다. [선택기 코드](resolution-switcher/resolution_switcher.py), [설정 기록](reference/display-profile-state.json), [적용 절차](DISPLAY-PROFILES.md)를 참조합니다.

프로그램 창 크기·위치 조정은 libwnck의 실제 프레임 좌표를 사용합니다. 로봇 제어 프로그램 내부 기능은 변경하지 않았습니다. 이번 선택기 변경에 GDM/VNC 재시작이나 재부팅은 하지 않았습니다. 재부팅 후 마지막 프로필 자동 복원은 구현하지 않았습니다.

**아래는 2026-09-15의 이전 조사 기록입니다.** 당시 1920×1080·자동 watcher 활성 상태를 최신 목표로 다시 적용하지 않습니다. `reference/current-pc` 6개 파일은 당시 참고 원본을 유지합니다. 서비스 파일 내용과 서비스 enable/active 상태는 별개입니다.

## 1. 관측한 실행 상태

| 항목 | 확인 결과 |
|---|---|
| OS | Ubuntu 22.04.5 LTS |
| GPU | NVIDIA GeForce RTX 2070 SUPER |
| 드라이버 | 590.48.01, nvidia-driver-590-open 패키지 |
| X 서버 | Xorg 21.1.4 계열, 로컬 DISPLAY `:0` |
| 로그인 | `kmg`의 `gdm-autologin` 세션, `Type=x11` |
| 인증 경로 | `/run/user/1000/gdm/Xauthority` |
| 물리 연결 | DRM의 HDMI/DP 출력 모두 disconnected, EDID 0바이트 |
| 논리적 화면 | `HDMI-0 connected primary 1920x1080+0+0`, 크기 정보 `0mm x 0mm` |
| 현재 주사율 | 59.96Hz |
| VNC | x11vnc 0.9.16-8, 시스템 서비스 enabled/active |
| VNC 수신 | TCP 5900, IPv4 전체 인터페이스 및 IPv6 수신 소켓 관측 |
| 화면 감지 | adaptive-display-mode 사용자 서비스 enabled/active |
| 재접속·공유 | 명령줄에 `-forever`, `-shared` |
| 비밀번호 | `-rfbauth` 파일 경로 지정. 파일 내용은 읽거나 복사하지 않음 |

즉, 물리 모니터가 검출되지 않아도 NVIDIA가 가상으로 연결된 출력을 제공하며, 같은 로컬 데스크톱을 VNC로 공유하는 상태를 확인했습니다.

## 2. 설정 파일과 역할

첨부 파일은 조사 시점 원문입니다. 다른 PC에 직접 설치할 템플릿은 아닙니다.

| 첨부 파일 | 기준 PC 원본 경로 | 역할 |
|---|---|---|
| [20-nvidia-virtual-monitor.conf](reference/current-pc/20-nvidia-virtual-monitor.conf) | `/etc/X11/xorg.conf.d/20-nvidia-virtual-monitor.conf` | NVIDIA 화면과 출력 강제 설정 |
| [gdm3-custom.conf](reference/current-pc/gdm3-custom.conf) | `/etc/gdm3/custom.conf` | Wayland 비활성·kmg 자동 로그인 |
| [x11vnc-physical.service](reference/current-pc/x11vnc-physical.service) | `/etc/systemd/system/x11vnc-physical.service` | 디스플레이 관리자 이후 VNC 시작·재시도 |
| [x11vnc-physical.sh](reference/current-pc/x11vnc-physical.sh) | `/usr/local/sbin/x11vnc-physical.sh` | 인증 파일 대기·로컬 Xorg 공유 |
| [adaptive-display-mode.service](reference/current-pc/adaptive-display-mode.service) | `/home/kmg/.config/systemd/user/adaptive-display-mode.service` | 화면·인증·출력·fallback 값 지정 |
| [adaptive-display-mode.sh](reference/current-pc/adaptive-display-mode.sh) | `/home/kmg/bin/adaptive-display-mode.sh` | 약 10초마다 EDID·해상도 점검 |

복사본 SHA-256은 [source-manifest.json](reference/source-manifest.json)에 있습니다.

### 화면 감지의 동작

- 대상은 `HDMI-0` 하나로 고정.
- EDID 또는 실물 크기 정보가 있으면 선호 모드 사용.
- 정보가 없으면 1920×1080, 59.96Hz로 조정.
- Xorg·사용자 프로그램을 종료하는 명령은 없고 해상도만 변경.
- 다중 모니터의 primary 선택과 x11vnc 공유 영역 갱신은 미구현.

2026-09-05 부팅 기록에서 감지 서비스가 15:17:00에 시작하고 15:17:11에 1920×1080을 적용한 로그가 있습니다. 이번 조사에서 새로 재부팅한 결과는 아닙니다.

### 기준 파일에 남아 있는 사항

- Xorg 파일에 고해상도 modeline, 넓은 Virtual 크기, 여러 모드 검증 해제 옵션이 있음.
- 동일 DFP 출력을 반복하는 MetaModes 문자열이 있음.
- 화면 감지 로그에 간헐적 Broken pipe 메시지가 있음.
- 모드 선택·EDID 판별·주사율 비교에는 MANUAL 7장에 적은 한계가 있음.

이 자료를 복제할 때는 동작의 원리와 필요한 값을 가져오되, 남아 있는 조정값이나 경고를 모든 PC의 필수 설정으로 간주하지 않습니다.

## 3. 외부 접속

- x11vnc 로그에 외부 공인 IP의 연결 기록과 화면·키보드·마우스 사용 통계가 있습니다.
- 공유기 관리자 설정을 조회하지 않았으므로 정확한 NAT·포트포워딩 규칙은 미확인입니다.
- Tailscale 1.98.4의 서비스 프로세스는 실행 중이지만 상태는 `NeedsLogin`, VPN IP는 없음, `SelfOnline=false`였습니다.
- 따라서 이 PC의 외부 VNC 접속을 Tailscale 경로로 설명할 수 없습니다.
- VNC 실행 명령에는 TLS 설정이 없습니다. 다른 네트워크 계층의 암호화 여부까지 확인한 것은 아닙니다.
- `/etc/ufw/ufw.conf`에는 `ENABLED=no`가 있습니다. 관리자 권한이 필요한 실제 방화벽 규칙 전체는 확인하지 못했습니다. 이것만으로 모든 방화벽이 꺼져 있다고 단정하지 않습니다.

외부 IP 주소 자체와 상세 접속 로그는 휴대용 문서에 포함하지 않았습니다.

## 4. 활성 경로가 아닌 기존 파일

- `remote-vnc.service`: 별도 `:1` TigerVNC용 정의가 남아 있지만 disabled/inactive.
- `x11vnc-physical-policy.service`: disabled/inactive.
- GNOME 원격 데스크톱 사용자 서비스에는 failed 상태가 있으나 현재 공유 경로는 실행 중인 x11vnc입니다.

현재 VNC 경로를 재현하기 위해 위 서비스를 함께 활성화할 필요는 없습니다. 다른 PC에서는 실제 역할과 충돌 여부를 조사합니다.

## 5. 확인 범위의 한계

| 항목 | 이번 조사 결과 |
|---|---|
| 현재 모니터 없는 화면 | 확인 |
| 실행 중인 VNC·자동 시작 설정 | 확인 |
| 현재 자동 로그인 세션 | 확인 |
| 기존 외부 VNC 사용 로그 | 확인 |
| 이번 작업에서 실제 VNC 뷰어 접속 | 미실시 |
| 새 재부팅 후 접속 시험 | 미실시 |
| 실제 케이블 연결·해제 | 미실시 |
| 주 모니터 자동 선택 | 현재 코드에 미구현 |
| Ubuntu 24.04 실제 설치 | 미실시 |
| 다른 GPU 검증 | 미실시 |
| 그래픽 앱의 가속·성능 시험 | 미실시 |
| 공유기 설정·전체 방화벽 규칙 | 미확인 |

2026-09-15 문서 작업에서는 설정 변경, 서비스 재시작, 재부팅, 네트워크 인증을 수행하지 않았습니다. 참고 복사본과 문서만 작성했습니다.
