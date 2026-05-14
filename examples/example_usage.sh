#!/bin/bash
# Exempel: Extrahera GPS från GoPro MAX2 .360-fil
#
# Byt ut filnamnen mot dina egna

VIDEO="GS010004.mp4"
RAW360="GS010004.360"
OUTPUT_BIN="GS010004.bin"
OUTPUT_GPX="GS010004.gpx"

# Steg 1: Hämta creation_time från MP4-filen
echo "=== Hämtar creation_time ==="
CREATION_TIME=$(ffprobe -v quiet -show_format "$VIDEO" | grep creation_time | cut -d= -f2 | cut -dT -f1,2 | cut -d. -f1)
echo "creation_time: $CREATION_TIME"

# Steg 2: Extrahera GPMF-telemetri
echo "=== Extraherar GPMF-telemetri ==="
ffmpeg -y -i "$RAW360" -codec copy -map 0:3 -f rawvideo "$OUTPUT_BIN"

# Steg 3: Konvertera till GPX
echo "=== Konverterar till GPX ==="
python3 gpmf2gpx.py "$OUTPUT_BIN" "$OUTPUT_GPX" --creation-time "$CREATION_TIME"

echo "=== Klar! ==="
echo "GPX-fil: $OUTPUT_GPX"
