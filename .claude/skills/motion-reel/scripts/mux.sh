#!/usr/bin/env bash
# Put the score under the picture, loudness-normalised for social platforms.
#   mux.sh out/silent.mp4 out/mix.wav out/final.mp4 [LUFS, default -14]
set -euo pipefail
ffmpeg -loglevel error -y -i "$1" -i "$2" -filter:a "loudnorm=I=${4:--14}:TP=-1.5:LRA=11" \
  -c:v copy -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart "$3"
echo "-> $3"
