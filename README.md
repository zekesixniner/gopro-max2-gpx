# GoPro MAX2 – GPS Extraction to GPX

Extracts GPS data from GoPro MAX2 `.360` files and saves it as standard GPX. One command, no manual ffprobe/ffmpeg steps.

---

## Table of Contents

- [Background](#background)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Advanced: pre-extracted .bin input](#advanced-pre-extracted-bin-input)
- [Verifying the result](#verifying-the-result)
- [Technical details](#technical-details)
- [Known limitations](#known-limitations)
- [Tested with](#tested-with)

---

## Background

The GoPro MAX2 stores GPS data as **GPMF telemetry** embedded inside the `.360` file – not as standard GPX. The format uses `GPS9` tags (9 fields, 32 bytes per point) and `STMP` timestamps instead of the older `GPS5`/`GPSU` format used by earlier GoPro cameras.

`gpmf2gpx.py` handles this format end to end: it reads the video's `creation_time` and locates the `GoPro MET` stream via `ffprobe`, extracts that stream via `ffmpeg`, parses the GPS9 data, and writes a standard GPX file with timestamps, coordinates and altitude.

---

## Requirements

```
sudo apt-get install -y ffmpeg python3 python3-venv
```

---

## Installation

```
mkdir -p ~/dev
cd ~/dev
git clone https://github.com/zekesixniner/gopro-max2-gpx.git
cd gopro-max2-gpx

python3 -m venv venv
source venv/bin/activate
pip install gpxpy
deactivate

chmod +x gpmf2gpx.py
ln -sf ~/dev/gopro-max2-gpx/gpmf2gpx.py ~/bin/gopro-max2-gpx
```

> The script's shebang points directly at `~/dev/gopro-max2-gpx/venv/bin/python3`, so once it's symlinked into `~/bin` you can call it directly — no need to activate the venv by hand.
>
> If your home directory or username differs from `peter`/`/home/peter`, edit the first line of `gpmf2gpx.py` accordingly after cloning.

---

## Usage

```
gopro-max2-gpx GS010068.360 GS010068.gpx
```

That's the whole workflow. The script:

1. Reads `creation_time` from the `.360` file via `ffprobe`
2. Auto-detects the `GoPro MET` stream index via `ffprobe` (no hardcoded track number)
3. Extracts that stream via `ffmpeg` to a temporary file
4. Parses the GPS9 data and writes the GPX
5. Deletes the temporary file

### Flags

| Flag              | Description                                                              |
| ----------------- | ------------------------------------------------------------------------- |
| `--track N`       | Force a stream index instead of auto-detecting "GoPro MET"                |
| `--creation-time` | Force the video start time instead of reading it via `ffprobe`            |
| `--keep-nofix`    | Keep points without GPS fix (GPSFIX=0)                                    |
| `--keep-bin`      | Save the extracted GPMF binary next to the output instead of deleting it  |
| `-v`, `--verbose` | Show detailed parsing info — one block per DEVC, very long for a full flight; redirect to a file if you want to keep it (`... -v > log.txt`) |

### Expected output

```
[INFO] Läser metadata från GS010068.360 (ffprobe)...
[INFO] creation_time hittad via ffprobe: 2026-06-02T16:11:51.000000Z
[INFO] GoPro MET-spår hittat: index 3 (handler_name='GoPro MET')
[INFO] Extraherar GPMF-spår 3 med ffmpeg...
[INFO] Video starttid: 2026-06-02 16:11:51+00:00
[INFO] Parsar GPMF-telemetri...
[INFO] Hittade 14076 GPS-punkter

✅ Klar!
   Sparade:  14076 punkter → GS010068.gpx
   Latitud:   55.90343 – 55.95050
   Longitud:  14.02875 – 14.09070
   Höjd:      17 – 369 m
   Hastighet: 0 – 210.8 km/h
   Starttid:  2026-06-02 16:11:51.413576+00:00
   Sluttid:   2026-06-02 16:35:18.554336+00:00
```

---

## Advanced: pre-extracted .bin input

If you already have a raw GPMF binary — e.g. from an older workflow or manual `ffmpeg` extraction — you can still pass it directly. In that case `--creation-time` is required, since `ffprobe` can't read a timestamp out of a raw GPMF binary:

```
gopro-max2-gpx GS010068.bin GS010068.gpx --creation-time 2026-06-02T16:11:51
```

---

## Verifying the result

```
python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('GS010068.gpx')
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
- Handles `GPS9` format (32 bytes, 9 fields per point)
- Uses `STMP` (microseconds from video start) for timestamping
- Gracefully ignores unknown tags such as `PRJT`
- GPS sampling rate: ~18 Hz
- Auto-detects the `GoPro MET` stream and `creation_time` via a single `ffprobe -show_format -show_streams` call, instead of relying on a hardcoded stream index

---

## Known limitations

| Issue                | Cause                        | Solution                                                        |
| --------------------- | ----------------------------- | ---------------------------------------------------------------- |
| No timestamps in GPX  | MAX2 does not use `GPSU`      | Script uses `STMP` + `creation_time` (auto-read, or `--creation-time` to override) |
| Wrong date in GPX     | Manual `--creation-time` typo | Let the script read `creation_time` from the `.360` file automatically; only an issue if you override it by hand |

---

## Tested with

- GoPro MAX2, firmware H24.02.01.22.00
- Ubuntu 24.04 / WSL1 on Windows 11
- Python 3.14
- ffmpeg 8.0.1
