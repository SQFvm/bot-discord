#!/bin/sh
set -eu
cd "$(dirname "$0")"

while true; do
    git pull --ff-only || echo "Update failed. Starting from the current checkout." >&2
    status=0
    cargo run --locked --release || status=$?
    case "$status" in
        0|130|143) exit 0 ;;
        75) continue ;; # Admin requested a restart.
        *) sleep 5 ;;
    esac
done
