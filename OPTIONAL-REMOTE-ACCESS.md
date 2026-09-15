# 선택 부록: SSH 터널과 VPN

이 문서는 사용자가 연결 방식을 별도로 변경하기로 선택했을 때만 적용합니다.

기본 설정과 사용자 접속 흐름은 **VNC 뷰어에 대상 주소·포트를 입력하고 VNC 비밀번호로 바로 접속**하는 것입니다. 일반 사용자는 SSH 터미널을 열거나 Tailscale에 로그인할 필요가 없습니다.

Codex는 기본 설치에서 이 부록을 자동 적용하지 않습니다. 특히 `-listen 0.0.0.0`을 `-localhost`로 바꾸면 직접 VNC 접속이 되지 않으므로, 사용자가 해당 변경을 선택한 경우에만 적용합니다.

기본 절차는 [MANUAL.md](MANUAL.md)의 10장을 참고합니다.

## 1. SSH 터널

외부 SSH 접속이 되는 경우 사용할 수 있습니다. 서버 스크립트의 `-listen 0.0.0.0`을 **`-localhost`로 교체**하고 IPv4·IPv6 모두 루프백 수신인지 확인합니다.

접속할 PC에서 실행합니다. 대문자 자리표시자는 실제 값으로 바꿉니다.

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:15900:127.0.0.1:5900 -p SSH_PORT USER@SSH_HOST
```

뷰어에서 **서버 `127.0.0.1`, 포트 `15900`**으로 접속하고 VNC 비밀번호를 입력합니다. 터널을 사용하는 동안 SSH 프로세스를 유지합니다. TigerVNC 명령줄 뷰어처럼 포트와 디스플레이 번호를 구분하는 제품은 `127.0.0.1::15900` 등 제품 문법을 따릅니다.

이는 `ssh -X`의 X11 포워딩과 다릅니다. SSH 호스트 키를 확인하고 검사를 우회하지 않습니다.

## 2. Tailscale 또는 기존 VPN

기존 VPN이 있으면 먼저 사용 가능 여부를 확인합니다. Tailscale을 선택하면:

1. [공식 Linux 설치 안내](https://tailscale.com/docs/install/linux)의 대상 Ubuntu 버전용 패키지 절차를 따른다.
2. `sudo tailscale up`으로 로그인·등록한다. 인증 토큰은 문서에 기록하지 않는다.
3. `tailscale status`, `tailscale ip -4`로 실제 연결과 주소를 확인한다.
4. 허용된 기기·사용자만 필요한 포트에 접근하도록 VPN 접근 정책을 확인한다.
5. 인증 만료 후 복구 방법과 부팅 시 자동 연결을 기록한다. 만료 비활성화를 필수로 간주하지 않는다.

연결은 둘 중 하나로 정합니다.

- **VPN 안의 SSH 터널:** 1장의 SSH_HOST에 VPN 주소를 사용. VNC는 `-localhost` 유지.
- **VPN 주소로 VNC 직접 접속:** VPN에서 VNC 수신 허용. `-localhost` 상태로 VPN 주소에 직접 접속하면 동작하지 않습니다. 바인딩·IPv6·방화벽·VPN 정책을 함께 확인합니다.

Tailscale은 보통 수동 포트포워딩 없이 암호화 경로를 만듭니다. 네트워크에 따라 중계 경로가 쓰일 수 있으므로 성능은 실제 환경에서 시험합니다. [Tailscale 네트워크 안내](https://tailscale.com/docs/reference/faq/firewall-ports)

## 3. 연결 방식을 변경할 때의 방화벽 순서

1. 현재 SSH/VNC 경로와 필요한 기존 서비스를 기록한다.
2. **기존 접속을 유지한 채 별도의 새 경로 접속을 성공시킨다.**
3. 필요한 포트·출발지를 허용하도록 규칙을 준비한다.
4. 합의된 범위에서 적용하고 외부망에서 다시 접속한다.
5. 원치 않는 공용 접근이 막혔는지 IPv4·IPv6를 확인한다.

Tailscale 자체 netfilter 규칙과 VPN 접근 정책도 확인합니다. UFW 한 줄로 전체 정책을 판정하지 않습니다. 검증 전에 SSH 허용을 삭제하거나 `ufw reset`을 하지 않습니다. [Tailscale Ubuntu 방화벽 안내](https://tailscale.com/docs/how-to/secure-ubuntu-server-with-ufw)
