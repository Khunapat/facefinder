#!/usr/bin/env bash
# Review sheets for a rendered film, or for a folder of stills.
#
#   review.sh out/final.mp4 [fast_action_second ...]   contact sheet (2 fps), phone test, strips
#   review.sh out/stills                                one contact sheet of every still
#
# Then open the PNGs and look at them properly.
set -euo pipefail
IN="$1"; shift || true
DIR="$(dirname "$IN")"
if [ -d "$IN" ]; then
  n=$(ls "$IN"/*.png | wc -l); cols=$(( n < 10 ? n : 10 )); rows=$(( (n + cols - 1) / cols ))
  ffmpeg -loglevel error -y -pattern_type glob -i "$IN/*.png" \
    -vf "scale=216:-1,tile=${cols}x${rows}:padding=6:color=gray" -frames:v 1 "$IN/../contact.png"
  echo "-> $(cd "$IN/.." && pwd)/contact.png"
  exit 0
fi
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$IN")
n=$(python3 -c "import math;print(math.ceil(float('$dur')*2))"); rows=$(( (n + 9) / 10 ))
ffmpeg -loglevel error -y -i "$IN" -vf "fps=2,scale=216:-1,tile=10x${rows}:padding=6:color=gray" -frames:v 1 "$DIR/contact.png"
ffmpeg -loglevel error -y -i "$IN" -vf "fps=1,scale=360:-1,tile=5x$(( ($(printf '%.0f' "$dur") + 4) / 5 ))" -frames:v 1 "$DIR/phone.png"
ffmpeg -loglevel error -y -ss 1 -i "$IN" -frames:v 1 "$DIR/poster.png"
for s in "$@"; do
  ffmpeg -loglevel error -y -ss "$(python3 -c "print(max(0,$s-0.1))")" -i "$IN" -vf "fps=12,scale=180:-1,tile=12x1" -frames:v 1 "$DIR/strip_$s.png"
done
echo "loudness:"; ffmpeg -hide_banner -i "$IN" -af ebur128=peak=true -f null - 2>&1 | grep -A14 Summary | grep -E " I:|Peak:" || echo "  (no audio)"
echo "-> $DIR/contact.png $DIR/phone.png $DIR/poster.png"
