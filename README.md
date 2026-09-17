# ubuntu-headless-vnc-setup

Ubuntu 가상 디스플레이 · VNC 설정 매뉴얼

작성일: 2026-09-15 · 해상도 선택기 추가: 2026-09-17

Ubuntu 22.04를 기본으로, 모니터가 있으면 주 화면을 공유하고 없으면 가상 화면으로 같은 데스크톱을 유지하기 위한 매뉴얼입니다. Ubuntu 24.04의 적용 및 검증 절차도 포함합니다.

## 설정 후 사용 방법

1. VNC 뷰어를 엽니다.
2. 대상 PC의 주소와 VNC 포트를 입력합니다.
3. VNC 비밀번호를 입력하고 화면을 사용합니다.

**기본 방식은 현재 PC와 같은 VNC 직접 접속입니다.** SSH 터널 실행이나 VPN 로그인은 필요하지 않습니다. 설치자는 외부 주소·포트 전달·방화벽을 한 번 구성하고, 사용자는 매번 뷰어로 바로 접속합니다.

## Mac / iPad에서 화면 크기 바꾸기

기존 VNC에 **바탕화면 해상도 선택기**를 추가했습니다. iPad에서 확인한 최종값은 **1600×1050, 원본 픽셀 전송(scale=1)**이며 Mac은 1920×1080입니다. 글씨 흐림과 하단 잘림을 줄인 설정입니다.

- 설치·사용·Codex 명령·복구: **[DISPLAY-PROFILES.md](DISPLAY-PROFILES.md)**
- Codex 자동 작업 지침: [AGENTS.md](AGENTS.md), [CODEX-RUNBOOK.md](CODEX-RUNBOOK.md)
- 수동 선택기 사용 중에는 자동 감지 서비스를 disabled/inactive로 둡니다. 아래 상세 매뉴얼의 자동 모니터 전환 경로와 구분합니다.

## VNC 한/영 전환과 직접 키보드 사용

[키보드 모드 매뉴얼](KEYBOARD-MODE.md)에 Caps Lock→한/영 전환, 기존 설정 복구, Mac/iPad 입력 언어와 조합 문제 점검 절차를 정리했습니다. 바탕화면 ‘VNC 키보드 모드’에서 켜고 끕니다.

## 읽는 순서

| 문서 | 용도 |
|---|---|
| [DISPLAY-PROFILES.md](DISPLAY-PROFILES.md) | Mac/iPad 선택기 설치·CLI·문제 해결·복구 |
| [MANUAL.md](MANUAL.md) | 사람이 따라 하는 조사·설치·접속·복구 절차 |
| [CODEX-RUNBOOK.md](CODEX-RUNBOOK.md) | 대상 PC의 Codex에게 전달할 작업 지침과 시작 프롬프트 |
| [CHECKLIST.md](CHECKLIST.md) | PC별 설정값·백업 위치·시험 결과 기록 |
| [REFERENCE-STATE.md](REFERENCE-STATE.md) | 기준 PC에서 확인한 실제 설정과 한계 |
| [reference/current-pc](reference/current-pc) | 2026-09-15 시스템 설정 파일 6개의 참고 복사본 |
| [reference/source-manifest.json](reference/source-manifest.json) | 원본 경로와 SHA-256 지문 |
| [VALIDATION.md](VALIDATION.md) | 문서·도구·실제 화면 검증 범위 |
| [OPTIONAL-REMOTE-ACCESS.md](OPTIONAL-REMOTE-ACCESS.md) | 사용자가 연결 방식 변경을 선택한 경우에만 보는 SSH·VPN 부록 |

## Codex에게 맡기기

1. 이 폴더 전체 또는 ZIP을 대상 PC로 옮깁니다.
2. ZIP이면 압축을 풉니다.
3. CODEX-RUNBOOK.md의 시작 프롬프트에서 폴더 경로를 실제 경로로 바꿔 전달합니다.
4. Codex가 대상 PC를 조사하고 CHECKLIST.md에 실제 값을 기록하도록 합니다.

## 적용 범위

- 기준 환경: Ubuntu 22.04.5, NVIDIA RTX 2070 SUPER, Xorg, x11vnc.
- 최신 상태(2026-09-17): 모니터 없는 단일 Xorg 화면, 자동 로그인·VNC 자동 시작, iPad 수동 모드 1600×1050, scale=1. 자동 화면 감지 서비스는 disabled/inactive.
- 이전 상태(2026-09-15): 기본 1920×1080, 10초 주기의 자동 감지 서비스. 이 경로는 실물 모니터 자동 전환이 필요한 별도 선택지입니다.
- 대상 PC에서 검증할 항목: 실제 모니터 연결·해제, 주 모니터 변경, 재부팅 후 접속, Ubuntu 24.04, 다른 GPU.
- 첨부 설정은 참고 원본이며 범용 설치 프로그램이 아닙니다. 사용자명·UID·GPU 주소·출력 번호를 검토 없이 복사하지 않습니다.
- 다중 모니터 자동 선택은 기준 PC의 기존 기능이 아닙니다. MANUAL.md의 구현 규칙과 시험을 충족해야 완료로 기록합니다.

2026-09-15 자료는 읽기 전용 조사 기록이고, 2026-09-17 선택기는 실제 기준 PC에 적용해 사용자 화면 확인을 받았습니다. 재부팅·다른 PC/GPU 검증은 별도입니다. 비밀번호 파일, Xauthority 내용, SSH 키, 인증 상태 파일, 개인 화면과 접속 로그는 포함하지 않습니다.
