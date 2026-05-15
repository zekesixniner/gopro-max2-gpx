# GoPro MAX2 – GPS Extraction to GPX

Tools for extracting GPS data from GoPro MAX2 `.360` files and saving as standard GPX format.

---

## Table of Contents

- [Background](#background)
- [Requirements](#requirements)
- [Installation](#installation)
- [Step-by-step](#step-by-step)
- [Verifying the result](#verifying-the-result)
- [Technical details](#technical-details)
- [Known limitations](#known-limitations)

---

## Background

The GoPro MAX2 stores GPS data as **GPMF telemetry** embedded inside the `.360` file – not as standard GPX. The format uses `GPS9` tags (9 fields, 32 bytes per point) and `STMP` timestamps instead of the older `GPS5`/`GPSU` format used by earlier GoPro cameras.

The script `gpmf2gpx.py` handles this format and produces a standard GPX file with timestamps, coordinates and altitude.

---

## Requirements

### System

```bash
sudo apt-get install -y ffmpeg python3 python3-pip python3-venv
```

### Python environment

```bash
python3 -m venv ~/gpx360env
source ~/gpx360env/bin/activate
pip install gpxpy
```

> **Note:** Always activate the virtual environment before running the script:
> ```bash
> source ~/gpx360env/bin/activate
> ```

---

## Installation

```bash
cd ~/bin
git clone https://github.com/zekesixniner/gopro-max2-gpx
cd <working PATH>

python3 -m venv ~/gpx360env
source ~/gpx360env/bin/activate
pip install gpxpy
```

---

## Step-by-step

### Step 1: Get the video start time

Get `creation_time` from the **360 file**:

```bash
ffprobe -v quiet -show_format GS010004.360 | grep creation_time
```

Example output:
```
TAG:creation_time=2026-03-15T10:44:45.000000Z
```

> **Important:** Always use `creation_time` from the 360 file. The `.mp4` file's internal timestamp may have the wrong date.

---

### Step 2: Extract GPMF telemetry

GPS data is stored in track 3 (`GoPro MET`) inside the `.360` file:

```bash
ffmpeg -y -i GS010004.360 -codec copy -map 0:3 -f rawvideo GS010004.bin
```

Verify that the correct track is used:

```bash
ffprobe -v quiet -show_streams GS010004.360 | grep handler_name
```

Look for the line containing `GoPro MET`. If it is not track 3, adjust the `-map` argument accordingly.

---

### Step 3: Convert to GPX

```bash
python3 gpmf2gpx.py GS010004.bin GS010004.gpx \
  --creation-time 2026-03-15T10:44:45
```

Flags:

| Flag | Description |
|---|---|
| `--creation-time` | Video start time from step 1 (required) |
| `--keep-nofix` | Keep points without GPS fix (GPSFIX=0) |
| `--verbose` | Show detailed parsing info |

Expected output:
```
[INFO] Video start time: 2026-03-15 10:44:45+00:00
[INFO] Reading GS010004.bin (4585 KB)...
[INFO] Parsing GPMF telemetry...
[INFO] Found 3485 GPS points

Done!
   Saved:     3485 points -> GS010004.gpx
   Latitude:  56.26577 - 56.32257
   Longitude: 12.85556 - 12.92190
   Altitude:  17 - 708 m
   Speed:     0 - 214.8 km/h
   Start:     2026-03-15 10:44:45.628247+00:00
   End:       2026-03-15 10:50:33.602820+00:00
```

---

## Verifying the result

```bash
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

- Parses recursive GPMF structure: `DEVC` -> `STRM` -> `GPS9`
- Handles `GPS9` format (32 bytes, 8 fields per point)
- Uses `STMP` (microseconds from video start) for timestamping
- Gracefully ignores unknown tags such as `PRJT`
- GPS sampling rate: ~18 Hz

---

## Known limitations

| Issue | Cause | Solution |
|---|---|---|
| Track number is not 3 | Depends on camera settings | Run `ffprobe` and look for `GoPro MET` |
| No timestamps in GPX | MAX2 does not use `GPSU` | Script uses `STMP` + `--creation-time` |
| Wrong date in GPX | `.360` file internal timestamp | Always use `creation_time` from the MP4 file |

---

## Tested with

- GoPro MAX2, firmware H24.02.01.22.00
- Ubuntu 24.04 / WSL2 on Windows 11
- Python 3.14
- ffmpeg 8.0.1
