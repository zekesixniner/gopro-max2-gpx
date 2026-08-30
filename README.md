# GoPro MAX2 – GPS Extraction to GPX

Tool for extracting GPS data from GoPro MAX2 `.360` files and saving as standard GPX format.

---

## Table of Contents

- [Background](#background)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Verifying the result](#verifying-the-result)
- [Technical details](#technical-details)
- [Known limitations](#known-limitations)

---

## Background

The GoPro MAX2 stores GPS data as **GPMF telemetry** embedded inside the `.360` file – not as standard GPX. The format uses `GPS9` tags (9 fields, 32 bytes per point) and `STMP` timestamps instead of the older `GPS5`/`GPSU` format used by earlier GoPro cameras.

`gpmf2gpx.py` handles this format end to end: it reads the video's `creation_time` and locates the GoPro MET track via `ffprobe`, extracts the GPMF stream via `ffmpeg`, parses the GPS9 data, and writes a standard GPX file with timestamps, coordinates and altitude — in a single command.

---

## Requirements

### System

Ubuntu or [WSL](https://en.wikipedia.org/wiki/Windows_Subsystem_for_Linux) in Windows

```
sudo apt-get install -y ffmpeg python3 python3-pip python3-venv
```

### Python environment

```
python3 -m venv ~/gpx360env
source ~/gpx360env/bin/activate
pip install gpxpy
```

`gpmf2gpx.py` uses a shebang pointing directly at this venv's Python
(`~/gpx360env/bin/python3`), so once installed it can be run directly
without manually activating the venv first.

---

## Installation

```
cd ~/dev
git clone https://github.com/zekesixniner/gopro-max2-gpx.git
cd gopro-max2-gpx
chmod +x gpmf2gpx.py

# Symlink into ~/bin, same pattern as the other tools
ln -sf ~/dev/gopro-max2-gpx/gpmf2gpx.py ~/bin/gopro-max2-gpx
```

---

## Usage

```
gopro-max2-gpx GS010004.360 GS010004.gpx
```

That's it — `creation_time` and the GoPro MET track are auto-detected via `ffprobe`.

Flags:

| Flag              | Description                                                        |
| ----------------- | ------------------------------------------------------------------- |
| `--track`         | Force a specific stream index instead of auto-detecting "GoPro MET" |
| `--creation-time` | Force video start time instead of reading it via ffprobe            |
| `--keep-nofix`    | Keep points without GPS fix (GPSFIX=0)                               |
| `--keep-bin`      | Keep the extracted GPMF binary instead of deleting it after use      |
| `--verbose`       | Show detailed parsing info                                          |

A pre-extracted `.bin` file (from an older workflow) is still accepted directly;
in that case `--creation-time` is required, since `ffprobe` can't read it from a raw GPMF binary.

Expected output:

```
[INFO] Läser metadata från GS010004.360 (ffprobe)...
[INFO] Video starttid: 2026-03-15 10:44:45+00:00
[INFO] Extraherar GPMF-spår 3 med ffmpeg...
[INFO] Parsar GPMF-telemetri...
[INFO] Hittade 3485 GPS-punkter

✅ Klar!
   Sparade:  3485 punkter → GS010004.gpx

   Latitud:   56.26577 – 56.32257
   Longitud:  12.85556 – 12.92190
   Höjd:      17 – 708 m
   Hastighet: 0 – 214.8 km/h
   Starttid:  2026-03-15 10:44:45.628247+00:00
   Sluttid:   2026-03-15 10:50:33.602820+00:00
```

---

## Verifying the result

```
python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('GS010004.gpx')
root = tree.getroot()
ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
pts = root.findall('.//gpx:trkpt', ns)
times = [p.find('gpx:time', ns).text for p in pts if p.find('gpx:time', ns) is not None]
eles = [float(p.find('gpx:ele', ns).text) for p in pts if p.find('gpx:ele', ns) is not None]
print(f'Points:   {len(pts)}')
print(f'Start:    {times[0]}')
print(f'End:      {times[-1]}')
print(f'Altitude: {min(eles):.0f} - {max(eles):.0f} m')
"
```

---

## Technical details

`gpmf2gpx.py` handles the GoPro MAX2's specific GPMF format:

- Locates the GoPro MET track and `creation_time` via `ffprobe`, extracts it via `ffmpeg`
- Parses recursive GPMF structure: `DEVC` → `STRM` → `GPS9`
- Handles `GPS9` format (32 bytes, 8 fields per point)
- Uses `STMP` (microseconds from video start) for timestamping
- Gracefully ignores unknown tags such as `PRJT`
- GPS sampling rate: ~18 Hz

---

## Known limitations

| Issue                        | Cause                          | Solution                                              |
| ----------------------------- | ------------------------------- | ------------------------------------------------------ |
| No "GoPro MET" track found    | Unusual track layout/encoding  | Use `--track` to force the correct stream index         |
| No timestamps in GPX          | MAX2 does not use `GPSU`       | Script uses `STMP` + `creation_time` automatically      |
| Wrong date in GPX             | `.360` file internal timestamp | Always uses `creation_time` from the `.360` file itself |

---

## Tested with

- GoPro MAX2, firmware H24.02.01.22.00
- Ubuntu 24.04 / WSL1 on Windows 11
- Python 3.14
- ffmpeg 8.0.1
