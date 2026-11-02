# Windows 10/11 VNC · 헤드리스 화면 도구

Windows x64에서 **같은 로그인 세션을 TightVNC로 공유**하고, 서명된 가상 모니터와 Mac/iPad 해상도 선택기, 선택형 한/영 키보드 모드를 설치합니다. Ubuntu용 Xorg·IBus·systemd 도구와 별도 구현입니다. 설치 파일·코드는 이 저장소에서 관리하고 비밀번호·장비별 상태는 로컬에만 둡니다.

## 설치

Python 3.9 이상과 tkinter가 필요합니다. Microsoft Store 실행 별칭 대신 실제 `python.exe`를 사용합니다. 먼저 저장소 루트에서 **일반 PowerShell**로 확인합니다.

```powershell
python --version
.\windows\install-tools.ps1 -Action Check
.\windows\setup-vnc.ps1 -Action Check
python .\windows\vnc_desktop.py status
```

PowerShell 실행 정책 때문에 파일 실행이 막히면, 검토한 스크립트를 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\install-tools.ps1 -Action Check`처럼 한 프로세스에서 실행할 수 있습니다. 시스템 전체 실행 정책은 변경하지 않습니다.

### 1. VNC 서버

새 서버가 필요할 때 **관리자 Windows PowerShell**에서 실행합니다.

```powershell
.\windows\setup-vnc.ps1 -Action InstallVnc
```

비밀번호는 터미널의 숨김 입력으로 받습니다. 표준 VNC 인증은 8자리 ASCII만 지원하므로 스크립트가 정확히 8자리인지 검사합니다. 비밀번호를 명령 인수·스크립트·채팅·커밋에 적지 않습니다. MSI 내부 전달에는 일시적으로 평문이 사용되며 속성 로그 숨김을 설정합니다. 접속용 암호와 설정 변경용 암호를 구분합니다.

신규 설치는 인증 필수, 부팅 시 서비스 자동 시작, Java HTTP 접속 끔, 지정 TCP 포트와 서버 실행 파일에 한정한 인바운드 방화벽 규칙을 구성합니다. 기본 포트는 5900, 기본 주소 범위는 Any입니다. 필요한 경우 신규 설치 시 `-Port 5901 -RemoteAddress '192.168.1.0/24'`로 제한합니다. **정상 서버가 이미 있으면 재설치·암호 변경·설정 덮어쓰기를 하지 않고 상태만 반환**합니다. 이 경우 기존 포트·방화벽·자동 시작 상태를 별도로 확인합니다. 일반 사용자에게 레지스트리 읽기 권한이 없으면 `Check`의 인증·포트는 null, `ConfigurationAccess`는 administrator-required-or-unavailable입니다. 이를 인증 비활성화로 해석하지 않습니다.

기본 사용자 흐름은 VNC 뷰어 → 대상 주소와 포트 → VNC 비밀번호입니다. 공유기 전달 규칙은 별도로 구성합니다. 기존 직접 접속을 localhost 전용이나 VPN 필수로 바꾸지 않습니다. 표준 TightVNC 2 세션은 암호화되지 않으므로 외부망 암호화가 필요할 때만 [선택형 원격 접속 부록](OPTIONAL-REMOTE-ACCESS.md)을 사용합니다. [TightVNC 공식 FAQ](https://www.tightvnc.com/faq.php)

### 2. 모니터 없이 쓰기 위한 가상 디스플레이

관리자 Windows PowerShell에서 실행합니다. 설치 중 화면이 갱신될 수 있습니다.

```powershell
.\windows\setup-vnc.ps1 -Action InstallVirtualDisplay
```

공식 **Virtual Display Driver 25.7.23의 x64 패키지**와 **NefCon 1.14.0**을 고정 URL/SHA-256으로 내려받고, 드라이버 카탈로그와 설치 도구의 유효한 게시자 서명을 검사합니다. 파일명 `x86.Driver.Only.zip`은 상위 프로젝트의 명명이며, 포함 INF의 대상은 NTamd64입니다. ARM64는 이 설치기의 지원 대상이 아닙니다. 새 루트 장치 `Root\MttVDD` 하나를 설치하며 오디오 드라이버·테스트 서명·Secure Boot·메모리 무결성·인증서 저장소는 변경하지 않습니다. 설치 중 Windows가 게시자 확인을 요청하면 사용자가 확인합니다.

가상 화면 1개, SDR, 60Hz와 아래 해상도만 설정합니다. 기존 가상 드라이버가 있으면 보존하고 자동으로 중복 설치하거나 설정을 덮어쓰지 않습니다. 필요한 모드가 없으면 기존 가상 드라이버의 설정을 먼저 확인합니다.

| 프로필 | 해상도 |
|---|---|
| `mac` | 1920×1080 |
| `ipad` | 1600×1050 |
| `ipad-landscape` | 1184×824 |
| `ipad-large-text` | 1024×768 |

설정은 `%SystemDrive%\VirtualDisplayDriver\vdd_settings.xml`, 패키지·설치 영수증·이전 XML 백업은 `%ProgramData%\VncDesktopTools`에 보관합니다. 실제 모니터 모드를 강제로 추가하지 않습니다. 물리 모니터 연결 상태에서는 Windows가 가상 화면을 확장 화면으로 활성화할 수 있어 VNC 전체 바탕화면이 커질 수 있습니다.

### 3. 바탕화면 도구

**로그인한 일반 사용자 PowerShell**에서 실행합니다. 관리자 계정으로 사용자 도구를 설치하지 않습니다.

```powershell
.\windows\install-tools.ps1 -Action Install
```

바탕화면 **VNC Desktop Tools**에서 화면·프로필을 선택합니다. `선택한 화면 해상도`는 해당 활성 출력만 바꿉니다. **가상 화면만 사용**은 물리 출력을 끄고 가상 화면을 주 화면으로 사용합니다. 20초 안에 유지하지 않으면 원래 출력 배치·모드·일반 창 위치를 복구합니다. GUI/CLI가 종료돼도 별도 복구 프로세스가 EOF를 받아 복구를 시도합니다. 모니터를 실제로 분리하거나 Windows 세션/OS가 종료되면 복구를 보장할 수 없으며 로컬 백업과 Windows 디스플레이 설정을 사용합니다.

설치 자체는 해상도·현재 키 매핑·VNC 비밀번호를 변경하지 않습니다. 실행 중인 프로그램과 VNC 서비스는 그대로 유지합니다.

키보드 보정과 접속 감시에는 **현재 사용자의 일반 권한 예약 작업 두 개**를 설치합니다. Windows 작업 스케줄러가 로그인한 사용자 세션에서 실행하므로 도구를 켠 Codex/터미널을 닫아도 유지됩니다. 계정 비밀번호를 저장하거나 SYSTEM/최고 권한으로 실행하지 않습니다. 사용자 로그인이 시작되고 약 5초 뒤, 이전에 켜 둔 기능만 재개합니다. `keyboard run`·`auto run`은 직접 실행하는 진단 명령이며 지속 실행은 `on`을 사용합니다.

일부 데스크톱 앱은 AppData 쓰기 경로를 가상화합니다. 설치기는 실제 파일 핸들로 경로를 확인해 예약 작업과 바탕화면 바로가기에 기록합니다. 설치 결과/`Check`의 `AppDirectory`가 `Packages\…\LocalCache` 아래라면 아래 `$tool`을 그 실제 폴더의 `vnc_desktop.py`로 지정합니다. 상태·설치 영수증·백업은 실제 `app` 폴더의 상위 `VncDesktopTools` 아래에 유지합니다.

## 접속 중 가상 화면 하나만 자동 공유

바탕화면 도구의 **자동 전환 켜기**를 선택합니다. 신규 설치의 기본값은 꺼짐이며 사용자가 켠 선택만 다음 Windows 로그인 때 재개합니다.

1. 인증된 VNC 접속을 감지하면 직전 물리/가상 출력 배치와 일반 창 위치를 로컬에 백업합니다.
2. 물리 모니터 출력을 비활성화하고 가상 화면 하나를 주 화면으로 사용합니다. 기본 원격 프로필은 Mac 1920×1080입니다. PC 자체는 절전하지 않으며 같은 로그인 세션의 프로그램을 계속 사용합니다. 모니터의 실제 절전 진입 시간은 기기 설정에 따릅니다.
3. 마지막 연결이 닫힌 뒤 약 4초의 재접속 여유를 두고 직전 출력 배치·모드·창 위치를 복구합니다. 두 번째 뷰어가 남아 있으면 원격 모드를 유지합니다.

```powershell
$tool = Join-Path $env:LOCALAPPDATA 'VncDesktopTools\app\vnc_desktop.py'
python $tool auto status
python $tool auto on --profile mac
python $tool auto off
```

표준 포트가 다르면 `auto on --profile mac --port 5901`처럼 실제 포트를 지정합니다. 프로필은 `mac`, `ipad`, `ipad-landscape`, `ipad-large-text`입니다. 자동 모드를 켠 상태에서 해상도를 바꾸려면 선택기의 가상 출력에 `선택한 화면 해상도`를 적용합니다. 물리/가상 배치를 수동으로 바꾸는 `headless`·`restore`는 자동 모드를 끈 뒤 사용합니다.

관측은 기존 Application 로그의 **tvnserver 인증 성공 이벤트**와 해당 VNC 서비스 PID가 소유한 현재 TCP 연결을 결합합니다. 포트 검사·인증 실패만으로는 화면을 바꾸지 않습니다. VNC 암호·관리 암호·패킷·클립보드·키 입력은 읽지 않으며 추가 키 입력 로그도 켜지 않습니다. 주소는 관측 프로세스 메모리에서만 사용하고 도구의 상태 파일이나 저장소에 남기지 않습니다.

동일 NAT 주소의 다른 TCP 연결이 남아 있으면 보수적으로 그 연결이 닫힐 때까지 복구가 지연될 수 있습니다. 관측 시작 시 최근 인증 기록을 확인할 수 없는 기존 연결은 재접속해야 합니다. 서비스 재시작이나 실제 접속이 사라지면 이전 인증 근거를 폐기합니다.

별도 복구 프로세스는 감시 프로그램의 종료·통신 끊김·8초 이상 응답 없음에도 복구를 시도합니다. 원본 배치는 `%LOCALAPPDATA%\VncDesktopTools\state\session-recovery.json`에 먼저 저장하며 복구 성공 뒤에만 지웁니다. 원래 물리 모니터가 분리돼 복구하지 못하면 가상 화면을 유지하고 `restore-pending`으로 표시합니다. 모니터를 다시 연결하고 자동 모드를 끄면 남은 복구를 시도할 수 있습니다. 실패한 원본을 가상 화면 배치로 덮어쓰지 않습니다.

자동 감시기는 일반 사용자 로그인 시 예약 작업으로 실행합니다. 새 부팅의 로그인 이전 화면과 케이블 분리 실기는 별도 검증 대상입니다. **끄기 · 물리 화면 복구**는 감시와 다음 로그인 재개를 끄고 해당 원격 접속 직전 배치로 돌아갑니다. 화면 코드 갱신 시에는 활성 감시기를 안전하게 중지·복구한 뒤 기존 선택으로 재개하며, 키보드 코드만 바뀌면 화면 감시기를 유지합니다.

`auto status`의 `running`은 최근 상태 갱신, `worker_active`는 감시기의 프로세스 잠금 소유를 나타냅니다. `running=false`, `worker_active=true`라면 상태 갱신이 멈춘 것입니다. `auto off`는 이 경우에도 기존 감시기에 종료를 요청하고 잠금 해제까지 기다린 뒤 남은 화면 복구를 진행합니다. 새 감시기를 중복 실행하지 않습니다. Windows의 일시적인 상태 파일 공유 충돌은 재시도하며 원본 JSON을 보존합니다.

## Codex / 터미널에서 사용

설치 후 `$tool` 경로를 사용합니다. 저장소에서 시험할 때는 `windows\vnc_desktop.py`로 바꿀 수 있습니다.

```powershell
$tool = Join-Path $env:LOCALAPPDATA 'VncDesktopTools\app\vnc_desktop.py'
python $tool status
python $tool profiles
# 활성 출력 해상도: 미리보기 후 자동 복구
python $tool apply mac
# 가상 화면만 사용: 물리 모니터가 잠시 꺼졌다가 자동 복구
python $tool headless ipad
# 요청한 가상 화면을 확인한 뒤 유지
python $tool headless ipad --keep
# 최초 도구 사용 전 배치로 복구: 미리보기 후 복구를 확정
python $tool restore --keep
```

`apply`의 기본 대상은 주 화면입니다. 다른 출력을 명시하려면 `--display '\\.\DISPLAY5'`처럼 **status에서 실제 조사한 이름**을 씁니다. `headless`는 가상 화면을 자동 선택하며 물리 출력 지정은 거부합니다. 드라이버가 해상도를 제공하지 않으면 변경 전에 실패합니다. 변경 작업은 프로세스 간 잠금으로 직렬화합니다.

`apply`는 세션 내 동적 모드 변경이고 마지막 프로필의 재부팅 복원을 구현하지 않습니다. `headless --keep`은 Windows에 가상 출력 단독 배치를 저장합니다. 부팅·로그인 화면 접근과 케이블 분리/재연결은 실제 장비에서 별도로 검증합니다. 자동 모드를 켜면 위 접속 정책이 배치를 관리합니다. 자동 모드를 끈 상태에서는 Windows의 케이블 재배치와 수동 `headless`·`restore`를 사용합니다.

## 한/영·Mac 키보드

```powershell
python $tool keyboard status
python $tool keyboard on
python $tool keyboard off
# 실제 Mac Cmd가 Left Alt로 전달되는 것을 확인한 경우에만 선택
python $tool keyboard on --command-as-control
```

기본은 꺼짐입니다. 켜면 Windows의 **주입된 Caps Lock 이벤트**를 VK_HANGUL로 전달하고, 정상적인 한 쌍의 누름·떼기에서 한 번 전환합니다. 물리 Caps Lock과 Shift/기존 Ctrl은 바꾸지 않습니다. Windows에 한국어 Microsoft IME를 설치·선택해야 합니다. 훅은 같은 사용자 데스크톱에서만 동작하고 Windows 보안 화면이나 더 높은 권한의 앱에서는 제한될 수 있습니다. SendInput이 차단되면 원래 키를 통과시킵니다. 끌 때 대체 Ctrl 등 눌린 수정키를 해제합니다.

Mac이 전환 키를 로컬에서 처리하고 **한글 낱자만 전송하는 경우**도 보정합니다. 주입된 Unicode 단일 두벌식 자모 33개를 원래 영문 키로 변환하고, 현재 입력칸의 Windows Korean IME를 한글 모드로 맞춥니다. 예를 들어 `ㄱㅏㄴㅏㄷㅏ` → `rkskek` → **가나다**로 조합합니다. ㄲ·ㅃ·ㅒ 등에는 필요한 Shift를 적용합니다. 그 뒤 클라이언트에서 영문 알파벳이 들어오면 Windows IME도 영문 모드로 맞춥니다. Ctrl/Alt/Win 단축키는 이 자동 전환의 대상에서 제외합니다.

이 보정은 Windows에서 **한국어 Microsoft IME가 선택된 입력칸**에 적용됩니다. 다른 입력 언어를 강제로 선택하지 않으며, 완성된 음절·복합 자모·클립보드는 변환하지 않습니다. 세벌식·여러 클라이언트의 입력 소스를 개별 동기화하는 기능은 아닙니다. 전환 키가 서버에 도착하는 기존 방식도 사용할 수 있습니다. 실제 Mac VNC에서 사용자가 **한글 조합과 영문 전환 모두 정상**을 확인했습니다. 다른 앱·기기의 결과는 [검증 기록](VALIDATION.md)과 구분합니다.

스페이스 한 번이 두 칸처럼 넓다면 한국어 IME의 전각 모드일 수 있습니다. 키보드 모드는 한/영 상태를 맞출 때 전각 플래그도 해제하고, 주입된 일반 스페이스를 처리하기 전에 해당 입력칸을 반각으로 맞춥니다. 원래 스페이스 이벤트는 한 번 그대로 전달하며 한/영 상태와 나머지 변환 플래그는 보존합니다. 물리 스페이스·Ctrl/Alt/Win 단축키·클라이언트가 명시적으로 보낸 전각 Unicode 공백 자체는 재매핑하지 않습니다. [Microsoft IME 변환 모드](https://learn.microsoft.com/en-us/windows/win32/intl/ime-conversion-mode-values)

VNC 서버를 바꾸거나 재시작하지 않습니다. 클라이언트 신원을 식별하는 훅은 아니므로 **다른 프로그램이 주입한 같은 키도 영향을 받습니다.** Cmd→Ctrl은 선택형 Left Alt 변환이며 Right Alt/AltGr는 보존합니다. 실제 전달 키를 확인하지 않은 상태에서 모든 Mac에 켜지 않습니다. 키 입력 문자·클립보드 내용을 기록하지 않습니다.

현재 확인한 Mac VNC에서는 Command가 Left Alt로 도착했습니다. 위 `--command-as-control` 옵션을 켠 뒤 사용자가 **⌘C/⌘V 복사·붙여넣기 정상**을 확인했습니다. 이 환경에서는 해당 옵션을 켠 상태로 저장합니다. 다른 클라이언트에서는 먼저 전달 키를 확인합니다.

로그인 시 예약 작업은 이전에 켜 둔 키보드 모드만 다시 시작합니다. 기존 Startup 재개 바로가기도 보존하며 중복 실행은 막습니다. `keyboard off`를 실행하면 다음 로그인에서도 꺼진 상태를 유지합니다. Windows의 자모 보정은 위 범위의 별도 구현이며, Ubuntu의 iPad RVNC 잠금 상태 보정 모듈·클립보드 보호는 포함하지 않습니다.

### Mac에서 원격 Windows 화면 캡처

Mac 프로필(`keyboard on --command-as-control`)에는 다음 VNC 단축키도 포함됩니다. 캡처는 **Windows 클립보드에만** 복사하며 이미지 파일은 만들지 않습니다. Windows 앱에서 ⌘V로 붙여넣습니다.

| 단축키 | 동작 |
|---|---|
| Control+Shift+3 | 현재 Windows 전체 바탕화면 캡처 |
| Control+Shift+F12 | 마우스로 드래그한 영역 캡처 · 기능키 대체 경로 |
| Control+Shift+S / Control+Shift+4 | 영역 캡처 호환 키 · 해당 클라이언트가 전달할 때 사용 |
| Esc / 마우스 오른쪽 버튼 | 영역 캡처 취소, 기존 클립보드 유지 |

영역 선택은 화면을 잠시 고정하고 **VNC 영역 캡처 - Esc 취소** 안내를 표시합니다. 화면 사진을 일반 불투명 창에 그리므로 VNC의 투명 창 전송 동작에 의존하지 않습니다. 선택한 부분은 안내창을 띄우기 전의 메모리 이미지에서 잘라 복사합니다. 전체 화면 캡처는 선택창 없이 복사되므로 VNC 안의 Windows 앱에 붙여넣어 확인합니다.

현재 Mac VNC 진단에서는 Control/Shift는 도착했지만 숫자 4는 Windows 키 이벤트에 나타나지 않았고, S 조합도 영역 요청으로 인식되지 않았습니다. 이 전송 경로에는 문자 변환을 거치지 않는 F12 대체 키를 사용합니다. Mac의 F12가 볼륨 키로 동작하면 **fn+Control+Shift+F12**, 표준 기능키 설정이면 **Control+Shift+F12**를 누릅니다. [Apple 기능키 안내](https://support.apple.com/en-gb/102439)

기본 Mac의 ⌘⇧3/4는 Mac 자체가 먼저 처리하므로 그대로 유지합니다. Windows로 전달된 주입 이벤트만 보정하며, 물리 Windows 키보드·기존 ⌘C/V·AltGr/Win 조합·일반 숫자는 바꾸지 않습니다. 숫자 키의 반복 누름으로 여러 캡처를 만들지 않고, 조합 키를 뗀 뒤 캡처를 시작합니다. 캡처 도우미는 사용자 데스크톱에서 실행하고 키보드 모드를 끄면 열려 있던 영역 선택도 종료합니다.

## 복구·제거

물리 모니터를 다시 연결한 상태에서 `python $tool restore --keep`, `python $tool keyboard off`를 먼저 실행합니다. 화면이 보이지 않으면 Windows **Win+P** 또는 로컬 디스플레이 설정을 사용합니다. 최초 배치와 직전 변경 백업은 `%LOCALAPPDATA%\VncDesktopTools\state`에 있습니다.

```powershell
# 일반 사용자: 마지막 설치 전 파일·바로가기 복구. 사용자 상태·백업은 보존
.\windows\install-tools.ps1 -Action Uninstall
# 관리자: 이 설치기가 기록한 가상 장치만 제거. Driver Store 패키지는 보존
.\windows\setup-vnc.ps1 -Action RemoveVirtualDisplay
```

가상 모니터만 남아 있는 동안 드라이버를 제거하지 않습니다. XML이 설치 후 수정됐으면 제거기가 그 수정본을 덮어쓰지 않습니다. TightVNC는 Windows 설치된 앱에서 별도로 제거할 수 있습니다. 가상 드라이버의 주요 GPU/칩셋 업데이트 관련 주의사항은 [상위 프로젝트](https://github.com/VirtualDrivers/Virtual-Display-Driver)를 확인합니다.

도구 파일은 `%LOCALAPPDATA%\VncDesktopTools\app`, 파일 지문과 설치 전 백업은 `install-backups`에 있습니다. 설치 실패 시 파일·바로가기를 복구하며 기존 비밀번호는 백업·커밋하지 않습니다. 장비별 기록은 [Windows 체크리스트](windows/CHECKLIST.md)의 로컬 복사본으로 남깁니다.

## 개발 검증

```powershell
python -m unittest discover -s tests -p "test_windows*.py" -v
.\windows\install-tools.ps1 -Action Check
.\windows\setup-vnc.ps1 -Action Check
git diff --check
```

Ubuntu 전체 회귀 검사는 Linux에서 `python3 -m unittest discover -s tests -v`를 사용합니다. Windows 테스트에서 모의 장치의 복구가 성공한 사실을 케이블 분리·Mac/iPad 실기·새 재부팅 성공으로 바꾸어 기록하지 않습니다.

상위 소스: [Virtual Display Driver](https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/tag/25.7.23), [NefCon](https://github.com/nefarius/nefcon/releases/tag/v1.14.0), [Windows 디스플레이 API](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-changedisplaysettingsexa), [주입된 키 이벤트](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-kbdllhookstruct). 외부 바이너리를 저장소에 재배포하지 않습니다.
