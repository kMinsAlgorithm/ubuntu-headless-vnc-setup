# KMGcocel 적용 사본 — 2026-09-23

두 번째 대상 PC(Ubuntu 24.04.5, RTX 5080, 드라이버 595.91.07, LG 3440×1440 HDMI-0)에 **실제로 설치한 파일**의 사본입니다. 수동 Mac/iPad 선택기 경로이며 VNC 포트는 55100입니다. `reference/current-pc`와 마찬가지로 다른 PC에 그대로 복사하는 템플릿이 아닙니다. 사용자·UID·BusID·DFP 이름·포트·EDID 경로는 PC마다 조사해서 바꿔야 합니다.

| 파일 | 설치 경로 | 비고 |
|---|---|---|
| `20-nvidia-virtual-monitor.conf` | `/etc/X11/xorg.conf.d/` | `ConnectedMonitor DFP-0`, `CustomEDID`, `AllowNonEdidModes`, iPad modeline |
| `gdm3-custom.conf` | `/etc/gdm3/custom.conf` | Wayland 끄기와 자동 로그인만 바꿈 |
| `x11vnc-physical.sh` | `/usr/local/sbin/` | 사용자 Xorg를 찾아서 공유. 옵션 선택 근거는 파일 끝 주석 참고 |
| `x11vnc-physical.service` | `/etc/systemd/system/` | `User=kmg`로 실행 (MIT-SHM 때문) |
| `install-system.sh` / `rollback-system.sh` | 작업 폴더 | sudo로 한 번 실행하는 설치와 원복. 중단된 뒤 다시 실행해도 원본 백업을 유지 |
| `CHECKLIST-KMGcocel.md` | — | 설정값, 백업 위치, 통과/미실시 기록 (내부 IP는 가림) |

- EDID 바이너리(`/etc/X11/edid/lg-ultrawide-dfp0.bin`)는 모니터 시리얼이 들어 있어서 넣지 않았습니다. 대상 PC에서 `/sys/class/drm/<card>-<output>/edid`를 복사하고 체크섬을 확인합니다.
- 비밀번호 파일, Xauthority, 접속 로그는 포함하지 않았습니다.
- Xorg/GDM 변경은 이 사본을 커밋한 시점까지 **재부팅 검증을 하지 않았습니다**. VNC 실행 스크립트와 서비스는 현재 세션에서 실행 중인 것을 확인했습니다.
