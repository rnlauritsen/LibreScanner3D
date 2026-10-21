#!/bin/bash
# Record 30 s of STRIPED frames from the scanner's camera A (macOS, avfoundation).
# Verified on one device only. Requires: ffmpeg, uvc-util (github.com/jtfrey/uvc-util), python3 with numpy + pillow.
#
# usage: ./record.sh OUT_DIR
# env:   EXP=25  FFMPEG=ffmpeg  UVC=~/uvc-util/src/uvc-util  PY=python3  AVF_INDEX=1  CAM_A=0  CAM_B=1
#
# Why the probe: opening the stream alternates between striped and plain frames. We open once, check, and
# do a throwaway open if needed so the recording itself is striped.
set -u
OUT=${1:?usage: record.sh OUT_DIR}
EXP=${EXP:-25}; FFMPEG=${FFMPEG:-ffmpeg}; UVC=${UVC:-$HOME/uvc-util/src/uvc-util}; PY=${PY:-python3}
AVF_INDEX=${AVF_INDEX:-1}; CAM_A=${CAM_A:-0}; CAM_B=${CAM_B:-1}
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT" && cd "$OUT" || exit 1

# exposure 25 / gain 0 keeps a pale object from saturating (saturation destroys the stripe code)
for i in $CAM_A $CAM_B; do $UVC -I $i -s auto-exposure-mode=1; $UVC -I $i -s backlight-compensation=2; done
$UVC -I $CAM_A -s exposure-time-abs=$EXP; $UVC -I $CAM_A -s gain=0
$UVC -I $CAM_B -s exposure-time-abs=5;    $UVC -I $CAM_B -s gain=0

cap1() { $FFMPEG -loglevel error -y -f avfoundation -pixel_format uyvy422 -framerate 10 -video_size 1280x720 -i "$AVF_INDEX" -frames:v 3 -pix_fmt gray -update 1 probe.png; }
sleep 2; cap1; printf "probe: "
if $PY "$HERE/chk_stripes.py" probe.png; then
  echo "that open was striped, so the next open will be plain - doing one throwaway open"; sleep 1; cap1
else
  echo "that open was plain, so the next open should be striped"
fi
sleep 1
echo "Start turning the base slowly NOW. Recording 30 s..."
$FFMPEG -loglevel error -y -f avfoundation -pixel_format uyvy422 -framerate 10 -video_size 1280x720 -i "$AVF_INDEX" -t 30 -pix_fmt gray f_%04d.png
echo "frames: $(ls f_*.png | wc -l)"
printf "check frame 100: "; $PY "$HERE/chk_stripes.py" f_0100.png
printf "check frame 250: "; $PY "$HERE/chk_stripes.py" f_0250.png

# restore this device's defaults as observed (exposure 78, auto exposure mode 8)
for i in $CAM_A $CAM_B; do $UVC -I $i -s gain=0; $UVC -I $i -s backlight-compensation=1; $UVC -I $i -s auto-exposure-mode=1; $UVC -I $i -s exposure-time-abs=78; $UVC -I $i -s auto-exposure-mode=8; done
