# ubuntu-headless-vnc-setup

Ubuntu 가상 디스플레이 · VNC 설정 매뉴얼

작성일: 2026-09-15

Ubuntu 22.04를 기본으로, 모니터가 있으면 주 화면을 공유하고 없으면 가상 화면으로 같은 데스크톱을 유지하기 위한 매뉴얼입니다. Ubuntu 24.04의 적용 및 검증 절차도 포함합니다.

## 읽는 순서

| 문서 | 용도 |
|---|---|
| [MANUAL.md](MANUAL.md) | 사람이 따라 하는 조사·설치·접속·복구 절차 |
| [CODEX-RUNBOOK.md](CODEX-RUNBOOK.md) | 대상 PC의 Codex에게 전달할 작업 지침과 시작 프롬프트 |
| [CHECKLIST.md](CHECKLIST.md) | PC별 설정값·백업 위치·시험 결과 기록 |
| [REFERENCE-STATE.md](REFERENCE-STATE.md) | 기준 PC에서 확인한 실제 설정과 한계 |
| [reference/current-pc](reference/current-pc) | 현재 설정 파일 6개의 참고 복사본 |
| [reference/source-manifest.json](reference/source-manifest.json) | 원본 경로와 SHA-256 지문 |
| [VALIDATION.md](VALIDATION.md) | 문서 검증 결과 |

## Codex에게 맡기기

1. 이 폴더 전체 또는 ZIP을 대상 PC로 옮깁니다.
2. ZIP이면 압축을 풉니다.
3. CODEX-RUNBOOK.md의 시작 프롬프트에서 폴더 경로를 실제 경로로 바꿔 전달합니다.
4. Codex가 대상 PC를 조사하고 CHECKLIST.md에 실제 값을 기록하도록 합니다.

## 적용 범위

- 기준 환경: Ubuntu 22.04.5, NVIDIA RTX 2070 SUPER, Xorg, x11vnc.
- 확인된 상태: 모니터 없는 1920×1080 화면, 자동 로그인 세션, VNC 자동 시작, 10초 주기의 화면 감지 서비스.
- 대상 PC에서 검증할 항목: 실제 모니터 연결·해제, 주 모니터 변경, 재부팅 후 접속, Ubuntu 24.04, 다른 GPU.
- 첨부 설정은 참고 원본이며 범용 설치 프로그램이 아닙니다. 사용자명·UID·GPU 주소·출력 번호를 검토 없이 복사하지 않습니다.
- 다중 모니터 자동 선택은 기준 PC의 기존 기능이 아닙니다. MANUAL.md의 구현 규칙과 시험을 충족해야 완료로 기록합니다.

이번 작업은 문서와 참고 복사본 작성입니다. 시스템 설정 변경, 서비스 재시작, 재부팅, VPN 로그인은 수행하지 않았습니다. 비밀번호 파일, Xauthority 내용, SSH 키, Tailscale 인증 상태 파일은 포함하지 않았습니다.
