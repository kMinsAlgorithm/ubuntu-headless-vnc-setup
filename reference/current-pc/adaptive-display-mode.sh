#!/usr/bin/env bash
set -u

OUTPUT="${ADAPTIVE_OUTPUT:-HDMI-0}"
FALLBACK_MODE="${ADAPTIVE_FALLBACK_MODE:-1920x1080}"
FALLBACK_RATE="${ADAPTIVE_FALLBACK_RATE:-59.96}"
FALLBACK_MODELINE="${ADAPTIVE_FALLBACK_MODELINE:-}"
INTERVAL="${ADAPTIVE_INTERVAL:-10}"
LOG_FILE="${ADAPTIVE_LOG_FILE:-$HOME/.local/state/adaptive-display-mode.log}"

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/run/user/$(id -u)/gdm/Xauthority}"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
  printf '%s %s\n' "$(date '+%F %T')" "$*" >>"$LOG_FILE"
}

query_xrandr() {
  xrandr --query 2>/dev/null
}

verbose_section() {
  xrandr --verbose 2>/dev/null | awk -v output="$OUTPUT" '
    $0 ~ "^" output " " { active = 1; print; next }
    active && /^[A-Za-z0-9-]+ (connected|disconnected)/ { exit }
    active { print }
  '
}

is_connected() {
  query_xrandr | awk -v output="$OUTPUT" '$1 == output && $2 == "connected" { found = 1 } END { exit found ? 0 : 1 }'
}

current_mode() {
  query_xrandr | awk -v output="$OUTPUT" '
    $1 == output && $2 == "connected" {
      for (i = 3; i <= NF; i++) {
        if ($i ~ /^[0-9]+x[0-9]+\+/) {
          sub(/\+.*/, "", $i)
          print $i
          exit
        }
      }
    }
  '
}

has_real_edid() {
  local section
  section="$(verbose_section)"

  if printf '%s\n' "$section" | grep -q '^[[:space:]]*EDID:'; then
    return 0
  fi

  printf '%s\n' "$section" | head -n 1 | grep -Eq '[1-9][0-9]*mm x [1-9][0-9]*mm'
}

preferred_mode() {
  verbose_section | awk '
    /^[[:space:]]+[0-9]+x[0-9]+/ && /preferred/ {
      print $1
      exit
    }
    /^[[:space:]]+[0-9]+x[0-9]+/ && /\+/ && first == "" {
      first = $1
    }
    END {
      if (first != "") print first
    }
  '
}

mode_available() {
  local mode="$1"
  verbose_section | awk -v mode="$mode" '$1 == mode { found = 1 } END { exit found ? 0 : 1 }'
}

ensure_fallback_mode() {
  if mode_available "$FALLBACK_MODE"; then
    return 0
  fi

  if [[ -z "$FALLBACK_MODELINE" ]]; then
    return 1
  fi

  local mode_name rest
  read -r mode_name rest <<<"$FALLBACK_MODELINE"

  if [[ "$mode_name" != "$FALLBACK_MODE" ]]; then
    log "fallback modeline name '$mode_name' does not match fallback mode '$FALLBACK_MODE'"
    return 1
  fi

  xrandr --newmode $FALLBACK_MODELINE 2>/dev/null || true
  xrandr --addmode "$OUTPUT" "$FALLBACK_MODE" 2>/dev/null || true
  mode_available "$FALLBACK_MODE"
}

apply_mode() {
  local mode="$1"
  local rate="${2:-}"
  local current
  current="$(current_mode)"

  if [[ "$current" == "$mode" ]]; then
    return 0
  fi

  if [[ -n "$rate" ]]; then
    if xrandr --output "$OUTPUT" --mode "$mode" --rate "$rate" 2>/dev/null; then
      log "set $OUTPUT to $mode@$rate"
      return 0
    fi
  fi

  if xrandr --output "$OUTPUT" --mode "$mode" 2>/dev/null; then
    log "set $OUTPUT to $mode"
    return 0
  fi

  log "failed to set $OUTPUT to $mode"
  return 1
}

settle_once() {
  if ! query_xrandr >/dev/null; then
    log "xrandr is not ready for DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY"
    return 1
  fi

  if ! is_connected; then
    log "$OUTPUT is disconnected"
    return 1
  fi

  if has_real_edid; then
    local preferred
    preferred="$(preferred_mode)"
    if [[ -n "$preferred" ]]; then
      apply_mode "$preferred"
      return $?
    fi
    log "$OUTPUT has EDID but no preferred mode; leaving current mode"
    return 0
  fi

  if ensure_fallback_mode; then
    apply_mode "$FALLBACK_MODE" "$FALLBACK_RATE"
    return $?
  fi

  log "fallback mode $FALLBACK_MODE is not available on $OUTPUT"
  return 1
}

status() {
  query_xrandr | sed -n "1p;/^$OUTPUT /p"
  if has_real_edid; then
    printf 'adaptive-state: real-edid\n'
    printf 'preferred-mode: %s\n' "$(preferred_mode)"
  else
    printf 'adaptive-state: fallback-no-edid\n'
    printf 'fallback-mode: %s@%s\n' "$FALLBACK_MODE" "$FALLBACK_RATE"
    if [[ -n "$FALLBACK_MODELINE" ]]; then
      printf 'fallback-modeline: %s\n' "$FALLBACK_MODELINE"
    fi
  fi
}

case "${1:-}" in
  --once)
    settle_once
    ;;
  --status)
    status
    ;;
  *)
    log "starting adaptive display watcher for $OUTPUT"
    while true; do
      settle_once || true
      sleep "$INTERVAL"
    done
    ;;
esac
