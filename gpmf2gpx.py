#!/usr/bin/env python3
"""
gpmf2gpx.py
===========
Extraherar GPS-data från GoPro MAX/MAX2 GPMF-binärfiler och sparar som GPX.
Använder STMP (mikrosekunder från videostart) + creation_time för tidsstämpling.

Krav:
  pip install gpxpy

Användning:
  python3 gpmf2gpx.py GS010004.bin GS010004.gpx --creation-time 2026-03-15T10:44:45
  python3 gpmf2gpx.py GS010004.bin GS010004.gpx --creation-time 2026-03-15T10:44:45 --verbose
"""

import struct
import sys
import os
import argparse
from datetime import datetime, timezone, timedelta

try:
    import gpxpy
    import gpxpy.gpx
except ImportError:
    print("[FEL] Installera gpxpy: pip install gpxpy")
    sys.exit(1)


# ──────────────────────────────────────────────
# GPMF-PARSER
# ──────────────────────────────────────────────

def read_header(data, offset):
    if offset + 8 > len(data):
        return None
    fourcc    = data[offset:offset+4].decode("latin-1")
    type_char = data[offset+4]
    size      = data[offset+5]
    repeat    = struct.unpack_from(">H", data, offset+6)[0]
    return fourcc, type_char, size, repeat


def next_offset(offset, size, repeat):
    total = 8 + size * repeat
    if total % 4 != 0:
        total += 4 - (total % 4)
    return offset + total


def parse_scal(data, offset, size, repeat, type_char):
    fmt_map = {ord('s'): '>h', ord('S'): '>H', ord('l'): '>l', ord('L'): '>L'}
    fmt = fmt_map.get(type_char, '>h')
    return [struct.unpack_from(fmt, data, offset + i * size)[0] for i in range(repeat)]


def parse_strm(data, offset, end, video_start_time, verbose=False):
    """
    Parsar en STRM-container.
    Använder STMP (mikrosekunder från videostart) för att tidsstämpla GPS9-punkter.
    """
    points    = []
    scal      = None
    gpsfix    = 3
    stnm      = ""
    stmp_us   = None   # mikrosekunder från videostart för detta kluster
    tsmp      = None   # totalt antal samples
    n_samples = None   # antal GPS-samples i detta kluster

    # Första pass: läs all metadata
    meta_offset = offset
    gps9_offset = None
    gps9_size   = None
    gps9_repeat = None

    while meta_offset + 8 <= end:
        hdr = read_header(data, meta_offset)
        if not hdr:
            break
        fourcc, type_char, size, repeat = hdr
        payload_start = meta_offset + 8
        payload       = data[payload_start:payload_start + size * repeat]

        if fourcc == "STNM":
            stnm = payload.rstrip(b"\x00").decode("latin-1", errors="replace")
        elif fourcc == "STMP":
            stmp_us = struct.unpack_from(">Q", payload, 0)[0]
        elif fourcc == "TSMP":
            tsmp = struct.unpack_from(">L", payload, 0)[0]
        elif fourcc == "SCAL":
            scal = parse_scal(data, payload_start, size, repeat, type_char)
        elif fourcc == "GPSF":
            gpsfix = struct.unpack_from(">l", payload, 0)[0] if size == 4 else payload[0]
        elif fourcc in ("GPS5", "GPS9"):
            gps9_offset = payload_start
            gps9_size   = size
            gps9_repeat = repeat

        meta_offset = next_offset(meta_offset, size, repeat)

    if verbose:
        print(f"    STRM '{stnm}'  stmp={stmp_us}µs  gpsfix={gpsfix}  scal={scal}")

    # Om ingen GPS-data i denna STRM, hoppa över
    if gps9_offset is None or scal is None:
        return []

    # Beräkna starttid för detta kluster
    if video_start_time and stmp_us is not None:
        cluster_start = video_start_time + timedelta(microseconds=stmp_us)
    else:
        cluster_start = None

    # Bygg skalvektor
    n_fields = gps9_size // 4
    if len(scal) == 1:
        scales = [scal[0]] * n_fields
    else:
        scales = list(scal) + [scal[-1]] * max(0, n_fields - len(scal))

    if verbose:
        print(f"      GPS9: {gps9_repeat} punkter, scales={scales[:5]}, cluster_start={cluster_start}")

    # Parsa GPS-punkter
    # GPS9 samplas med ~18 Hz, fördela jämnt inom klustret
    for i in range(gps9_repeat):
        base = gps9_offset + i * gps9_size
        try:
            vals = [struct.unpack_from(">l", data, base + j*4)[0] for j in range(n_fields)]
        except struct.error:
            continue

        lat   = vals[0] / scales[0]
        lon   = vals[1] / scales[1]
        alt   = vals[2] / scales[2]
        spd2d = vals[3] / scales[3]  # m/s

        if lat == 0.0 and lon == 0.0:
            continue

        # Tidsstämpel: fördela jämnt inom klustret
        if cluster_start:
            # ~18 Hz GPS-frekvens för GoPro MAX2
            t = cluster_start + timedelta(seconds=i / 18.0)
        else:
            t = None

        points.append({
            "lat":   lat,
            "lon":   lon,
            "alt":   alt,
            "speed": spd2d * 3.6,  # km/h
            "fix":   gpsfix,
            "time":  t,
        })

    return points


def parse_devc(data, offset, end, video_start_time, verbose=False):
    points = []
    while offset + 8 <= end:
        hdr = read_header(data, offset)
        if not hdr:
            break
        fourcc, type_char, size, repeat = hdr
        payload_start = offset + 8
        payload_end   = payload_start + size * repeat

        if fourcc == "STRM" and type_char == 0:
            pts = parse_strm(data, payload_start, payload_end,
                             video_start_time, verbose=verbose)
            points.extend(pts)

        offset = next_offset(offset, size, repeat)
    return points


def parse_gpmf(data, video_start_time, verbose=False):
    all_points = []
    offset     = 0
    length     = len(data)
    devc_count = 0

    while offset + 8 <= length:
        hdr = read_header(data, offset)
        if not hdr:
            break
        fourcc, type_char, size, repeat = hdr
        payload_start = offset + 8
        payload_end   = payload_start + size * repeat

        if fourcc == "DEVC" and type_char == 0:
            devc_count += 1
            if verbose:
                print(f"\nDEVC #{devc_count} @ offset={offset}")
            pts = parse_devc(data, payload_start, payload_end,
                             video_start_time, verbose=verbose)
            all_points.extend(pts)

        offset = next_offset(offset, size, repeat)

    if verbose:
        print(f"\nTotalt: {devc_count} DEVC-block, {len(all_points)} GPS-punkter")

    timed   = sorted([p for p in all_points if p["time"]], key=lambda p: p["time"])
    untimed = [p for p in all_points if not p["time"]]
    return timed + untimed


# ──────────────────────────────────────────────
# GPX-EXPORT
# ──────────────────────────────────────────────

def write_gpx(points, output_path, skip_nofix=True):
    gpx     = gpxpy.gpx.GPX()
    track   = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(track)
    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)

    skipped = 0
    for pt in points:
        if skip_nofix and pt.get("fix", 3) == 0:
            skipped += 1
            continue
        tp = gpxpy.gpx.GPXTrackPoint(
            latitude  = pt["lat"],
            longitude = pt["lon"],
            elevation = pt["alt"],
            time      = pt.get("time"),
        )
        segment.points.append(tp)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(gpx.to_xml())

    return len(segment.points), skipped


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extrahera GPS från GoPro MAX/MAX2 GPMF-binärfil till GPX"
    )
    parser.add_argument("input",  help="GPMF-binärfil (t.ex. GS010004.bin)")
    parser.add_argument("output", help="GPX-outputfil (t.ex. GS010004.gpx)")
    parser.add_argument("--creation-time", required=True,
                        help="Videons creation_time från ffprobe, t.ex. 2026-03-15T10:44:45")
    parser.add_argument("-v", "--verbose",  action="store_true")
    parser.add_argument("--keep-nofix",     action="store_true",
                        help="Behåll punkter utan GPS-fix (GPSFIX=0)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[FEL] Hittar inte: {args.input}")
        sys.exit(1)

    # Parsa creation_time
    try:
        ct = args.creation_time.replace("Z", "+00:00")
        if "+" not in ct and "-" not in ct[10:]:
            ct += "+00:00"
        video_start_time = datetime.fromisoformat(ct)
        if video_start_time.tzinfo is None:
            video_start_time = video_start_time.replace(tzinfo=timezone.utc)
    except Exception as e:
        print(f"[FEL] Kunde inte parsa creation-time: {e}")
        sys.exit(1)

    print(f"[INFO] Video starttid: {video_start_time}")
    print(f"[INFO] Läser {args.input} ({os.path.getsize(args.input)/1024:.0f} KB)...")
    with open(args.input, "rb") as f:
        data = f.read()

    print("[INFO] Parsar GPMF-telemetri...")
    points = parse_gpmf(data, video_start_time, verbose=args.verbose)

    if not points:
        print("[FEL] Inga GPS-punkter hittades!")
        sys.exit(1)

    print(f"[INFO] Hittade {len(points)} GPS-punkter")
    n_ok, n_skip = write_gpx(points, args.output, skip_nofix=not args.keep_nofix)

    print(f"\n✅ Klar!")
    print(f"   Sparade:  {n_ok} punkter → {args.output}")
    if n_skip:
        print(f"   Hoppade:  {n_skip} punkter utan GPS-fix")

    valid = [p for p in points if p.get("fix", 3) != 0]
    if valid:
        lats   = [p["lat"]   for p in valid]
        lons   = [p["lon"]   for p in valid]
        alts   = [p["alt"]   for p in valid]
        speeds = [p["speed"] for p in valid]
        print(f"\n   Latitud:   {min(lats):.5f} – {max(lats):.5f}")
        print(f"   Longitud:  {min(lons):.5f} – {max(lons):.5f}")
        print(f"   Höjd:      {min(alts):.0f} – {max(alts):.0f} m")
        print(f"   Hastighet: 0 – {max(speeds):.1f} km/h")
        timed = [p for p in valid if p["time"]]
        if timed:
            print(f"   Starttid:  {timed[0]['time']}")
            print(f"   Sluttid:   {timed[-1]['time']}")


if __name__ == "__main__":
    main()
