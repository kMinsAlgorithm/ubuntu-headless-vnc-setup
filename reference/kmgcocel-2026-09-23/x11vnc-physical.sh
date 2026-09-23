#!/bin/sh
# Share kmg's local Xorg desktop (the real session, not a new one) over VNC.
# Runs as kmg (see x11vnc-physical.service): a root x11vnc cannot attach MIT-SHM
# segments to kmg's rootless Xorg (X_ShmAttach BadAccess, 2026-09-23).
set -eu

TARGET_UID=1000
PASSWD_FILE=/home/kmg/.vnc/physical-passwd
PORT=55100

log() { printf '%s\n' "$*" >&2; }

# Print "DISPLAY AUTHFILE" for uid $1's Xorg once it accepts X connections.
find_display() {
  for pid in $(pgrep -u "$1" -x Xorg || true); do
    auth=$(tr '\0' '\n' <"/proc/$pid/cmdline" 2>/dev/null | sed -n '/^-auth$/{n;p;q;}')
    [ -n "$auth" ] && [ -r "$auth" ] || continue
    for sock in /tmp/.X11-unix/X*; do
      [ -S "$sock" ] && [ "$(stat -c %u "$sock")" = "$1" ] || continue
      dpy=":${sock##*/X}"
      if DISPLAY="$dpy" XAUTHORITY="$auth" /usr/bin/xdpyinfo >/dev/null 2>&1; then
        printf '%s %s\n' "$dpy" "$auth"
        return 0
      fi
    done
  done
  return 1
}

# Never serve an unauthenticated desktop.
if [ ! -r "$PASSWD_FILE" ]; then
  log "waiting for VNC password file $PASSWD_FILE"
  while [ ! -r "$PASSWD_FILE" ]; do sleep 5; done
fi

announced=""
while :; do
  found=$(find_display "$TARGET_UID") || found=""
  [ -n "$found" ] && break
  [ -n "$announced" ] || log "waiting for the local Xorg desktop of uid $TARGET_UID"
  announced=1
  sleep 2
done

set -- $found
log "sharing DISPLAY=$1 on port $PORT"

exec /usr/bin/x11vnc \
  -norc \
  -display "$1" \
  -auth "$2" \
  -forever \
  -shared \
  -norepeat -1 \
  -xkb \
  -noxdamage \
  -nodpms \
  -noscr \
  -nolookup \
  -defer 20 \
  -wait 20 \
  -wireframe \
  -readtimeout 180 \
  -ping 5 \
  -always_inject \
  -allinput \
  -rfbauth "$PASSWD_FILE" \
  -input KMBCF \
  -rfbport "$PORT" \
  -listen 0.0.0.0 \
  -no6 -rfbportv6 "$PORT"
# -no6 + -rfbportv6: otherwise libvncserver also opens its default [::]:5900
# next to x11vnc's own [::]:$PORT listener (observed 2026-09-23).
# Reference-PC tuning dropped here (2026-09-23, 3440x1440 on 1 Gbps LAN):
#   -noshm       fb read 426 MB/s vs 2336 MB/s with MIT-SHM (needs non-root x11vnc)
#   -speeds 6,1500,60   forced "slow network" heuristics; let x11vnc measure
#   -fixscreen V=10     full 3440x1440 resend every 10 s
#   -repeat      kept X autorepeat on while viewing; a key-up delayed by a big
#                screen update then auto-repeated on the server (runaway Tab).
#                -norepeat -1: re-disable even if GNOME turns autorepeat back on.
# -noxdamage kept: GNOME's compositor can make DAMAGE hints miss updates;
# with MIT-SHM a full poll of 3440x1440 is cheap.
