#!/bin/sh
set -eu

while :; do
  AUTH=""
  for f in /run/user/1000/gdm/Xauthority /home/kmg/.Xauthority /run/user/128/gdm/Xauthority; do
    if [ -r "$f" ]; then
      AUTH="$f"
      break
    fi
  done

  if [ -n "$AUTH" ]; then
    break
  fi

  sleep 1
done

exec /usr/bin/x11vnc \
  -display :0 \
  -auth "$AUTH" \
  -forever \
  -shared \
  -repeat \
  -xkb \
  -noxdamage \
  -noshm \
  -nodpms \
  -noscr \
  -nolookup \
  -speeds 6,1500,60 \
  -defer 20 \
  -wait 20 \
  -wireframe \
  -readtimeout 180 \
  -ping 5 \
  -always_inject \
  -allinput \
  -fixscreen V=10 \
  -rfbauth /home/kmg/.vnc/physical-passwd \
  -input KMBCF \
  -rfbport 5900 \
  -listen 0.0.0.0
