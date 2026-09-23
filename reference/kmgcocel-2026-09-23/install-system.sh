#!/bin/bash
# One-shot system install for KMGcocel headless VNC (manual Mac/iPad selector path).
# Run from kmg's desktop terminal:  sudo bash ~/headless-vnc-setup/install-system.sh
# Does NOT reboot. GDM/Xorg changes apply at the next boot; VNC starts now.
set -euo pipefail

TARGET_USER=kmg
TARGET_HOME=/home/kmg
TASK_ROOT="$TARGET_HOME/headless-vnc-setup"
STAGING="$TASK_ROOT/staging"
PASSWD_FILE="$TARGET_HOME/.vnc/physical-passwd"
GDM_CONF_SHA=ceee968ce021213814ef4f87e19f6e76fcb0333170786dd0c006760ad61810af

[ "$(id -u)" = 0 ] || { echo "sudo로 실행하세요." >&2; exit 1; }
[ "${SUDO_USER:-}" = "$TARGET_USER" ] || { echo "kmg 계정에서 sudo로 실행하세요." >&2; exit 1; }

SYSTEM_FILES=(
  "/etc/gdm3/custom.conf:gdm3-custom.conf"
  "/etc/X11/xorg.conf.d/20-nvidia-virtual-monitor.conf:20-nvidia-virtual-monitor.conf"
  "/etc/X11/edid/lg-ultrawide-dfp0.bin:lg-ultrawide-dfp0.bin"
  "/etc/systemd/system/x11vnc-physical.service:x11vnc-physical.service"
  "/usr/local/sbin/x11vnc-physical.sh:x11vnc-physical.sh"
)
already_installed() {
  local entry
  for entry in "${SYSTEM_FILES[@]}"; do
    cmp -s "${entry%%:*}" "$STAGING/${entry##*:}" || return 1
  done
}

# Resume after an interrupted run: files already match staging, so keep the first
# backup (the true originals) instead of backing up our own files.
RESUME=""
if already_installed; then
  BACKUP_DIR="$(ls -d "$TASK_ROOT"/backup-* 2>/dev/null | sort | head -n 1)"
  [ -f "$BACKUP_DIR/files-before.tsv" ] || { echo "설치본은 있으나 원본 백업을 찾지 못했습니다. 중단합니다." >&2; exit 1; }
  RESUME=1
  echo "이전 실행에서 파일 설치 완료 확인. 원본 백업 유지: $BACKUP_DIR"
elif [ "$(sha256sum /etc/gdm3/custom.conf | cut -d' ' -f1)" != "$GDM_CONF_SHA" ]; then
  # Refuse to overwrite a GDM config that changed after staging.
  echo "/etc/gdm3/custom.conf가 스테이징 이후 변경됐습니다. 중단합니다." >&2
  exit 1
fi

if [ -z "$RESUME" ]; then
# 1. Backup (manual 5.2): record presence and service state before any change.
BACKUP_DIR="$TASK_ROOT/backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR/files"
chmod 700 "$BACKUP_DIR"
for path in \
  /etc/gdm3/custom.conf \
  /etc/X11/xorg.conf.d/20-nvidia-virtual-monitor.conf \
  /etc/X11/edid/lg-ultrawide-dfp0.bin \
  /etc/systemd/system/x11vnc-physical.service \
  /usr/local/sbin/x11vnc-physical.sh
do
  if [ -e "$path" ] || [ -L "$path" ]; then
    cp -a --parents -- "$path" "$BACKUP_DIR/files/"
    printf 'PRESENT\t%s\n' "$path" >> "$BACKUP_DIR/files-before.tsv"
  else
    printf 'ABSENT\t%s\n' "$path" >> "$BACKUP_DIR/files-before.tsv"
  fi
done
systemctl is-enabled x11vnc-physical.service > "$BACKUP_DIR/vnc-enabled-before.txt" 2>&1 || true
systemctl is-active x11vnc-physical.service > "$BACKUP_DIR/vnc-active-before.txt" 2>&1 || true
dpkg-query -W -f='${Package} ${Status}\n' x11vnc mesa-utils > "$BACKUP_DIR/packages-before.txt" 2>&1 || true
chown -R "$TARGET_USER:$TARGET_USER" "$BACKUP_DIR"
echo "백업: $BACKUP_DIR"

# 2. Packages (driver untouched).
apt-get update
apt-get install -y x11vnc mesa-utils

# 3. Staged files.
install -d -m 755 /etc/X11/xorg.conf.d /etc/X11/edid
install -m 644 "$STAGING/lg-ultrawide-dfp0.bin" /etc/X11/edid/lg-ultrawide-dfp0.bin
install -m 644 "$STAGING/20-nvidia-virtual-monitor.conf" /etc/X11/xorg.conf.d/20-nvidia-virtual-monitor.conf
install -m 644 "$STAGING/gdm3-custom.conf" /etc/gdm3/custom.conf
install -m 755 "$STAGING/x11vnc-physical.sh" /usr/local/sbin/x11vnc-physical.sh
install -m 644 "$STAGING/x11vnc-physical.service" /etc/systemd/system/x11vnc-physical.service
fi
sh -n /usr/local/sbin/x11vnc-physical.sh
systemd-analyze verify /etc/systemd/system/x11vnc-physical.service

# 4. VNC password, typed interactively by kmg; never overwrite an existing one.
if [ ! -s "$PASSWD_FILE" ]; then
  runuser -u "$TARGET_USER" -- install -d -m 700 "$TARGET_HOME/.vnc"
  rm -f -- "$PASSWD_FILE"
  echo
  echo "VNC 접속 비밀번호를 설정합니다 (VNC 인증은 앞 8자만 사용됩니다)."
  if ! runuser -u "$TARGET_USER" -- /usr/bin/x11vnc -storepasswd "$PASSWD_FILE" || [ ! -s "$PASSWD_FILE" ]; then
    rm -f -- "$PASSWD_FILE"
    echo "비밀번호 설정이 취소됐습니다. 같은 명령을 다시 실행하면 이어서 진행합니다." >&2
    exit 1
  fi
  runuser -u "$TARGET_USER" -- chmod 600 "$PASSWD_FILE"
else
  echo "기존 VNC 비밀번호 파일을 그대로 사용합니다."
fi

# 5. Enable at boot and start now on the current desktop.
systemctl daemon-reload
systemctl enable --now x11vnc-physical.service
sleep 4
systemctl --no-pager --lines=5 status x11vnc-physical.service || true
ss -lntp | grep -E ':55100\b' || echo "경고: 55100 포트가 아직 열리지 않았습니다."
echo
echo "완료. Xorg/GDM 변경(자동 로그인·Wayland 끔·가상 모니터)은 다음 재부팅부터 적용됩니다."
echo "백업: $BACKUP_DIR"
