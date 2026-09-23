#!/bin/bash
# Undo install-system.sh (manual 15). Usage: sudo bash rollback-system.sh ~/headless-vnc-setup/backup-YYYYmmdd-HHMMSS
# Packages (x11vnc, mesa-utils) and the VNC password file are left in place.
set -euo pipefail
BACKUP_DIR="${1:?backup directory required}"
[ "$(id -u)" = 0 ] || { echo "sudo로 실행하세요." >&2; exit 1; }
[ -f "$BACKUP_DIR/files-before.tsv" ] || { echo "files-before.tsv 없음: $BACKUP_DIR" >&2; exit 1; }

systemctl stop x11vnc-physical.service || true
if [ "$(cat "$BACKUP_DIR/vnc-enabled-before.txt")" != enabled ]; then
  systemctl disable x11vnc-physical.service || true
fi

while IFS=$'\t' read -r state path; do
  case "$state" in
    PRESENT) cp -a -- "$BACKUP_DIR/files$path" "$path" ;;
    ABSENT)  rm -f -- "$path" ;;
    *) echo "Unknown backup state: $state" >&2; exit 1 ;;
  esac
done < "$BACKUP_DIR/files-before.tsv"
systemctl daemon-reload
echo "원복 완료. GDM/Xorg 원복은 다음 재부팅부터 적용됩니다."
