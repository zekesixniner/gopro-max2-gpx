#!/home/peter/dev/gopro-max2-gpx/venv/bin/python3
"""
gpmf2gpx.py
===========
Extraherar GPS-data från en GoPro MAX/MAX2 .360-fil och sparar som GPX.
Ett enda kommando: hittar GoPro MET-spåret och creation_time via ffprobe,
extraherar GPMF-strömmen via ffmpeg till en temporär fil, parsar GPS9-data
(STMP-tidsstämplar) och skriver GPX. Temp-filen städas bort automatiskt.

Krav:
  pip install gpxpy
  ffmpeg/ffprobe måste finnas i PATH

Användning:
  gpmf2gpx.py GS010004.360 GS010004.gpx
  gpmf2gpx.py GS010004.360 GS010004.gpx --verbose
  gpmf2gpx.py GS010004.360 GS010004.gpx --track 3 --creation-time 2026-03-15T10:44:45

Manuella overrides (normalt onödiga, auto-detekteras):
  --track            Forcera streamindex istället för auto-detektion av "GoPro MET"
  --creation-time    Forcera video-starttid istället för ffprobe-värdet

Direkt .bin-input stöds fortfarande (hoppar över ffprobe/ffmpeg-steget):
  gpmf2gpx.py GS010004.bin GS010004.gpx --creation-time 2026-03-15T10:44:45

Tidsstämpling:
  Varje GPS9-kluster har en egen starttid (STMP, mikrosekunder från videostart).
  Punkterna INOM ett kluster tidsstämplas genom att interpolera jämnt mellan
  klustrets egen starttid och NÄSTA klusters starttid (dvs. den verkliga
  förfluta tiden delat på antalet punkter i klustret) — inte en fast antagen
  samplingsfrekvens. GPS9 levereras i kluster om typiskt 7-10 punkter per
  ~1 sekund, vilket INTE är samma sak som 18Hz jämnt fördelat inom klustret.
"""

import struct
import sys
import os
import json
import argparse
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta

try:
    import gpxpy
    import gpxpy.gpx
except ImportError:
    print("[FEL] Installera gpxpy: pip install gpxpy")
    sys.exit(1)


# ──────────────────────────────────────────────
# FFPROBE / FFMPEG-HJÄLPFUNKTIONER
# ──────────────────────────────────────────────

def run_ffprobe_json(input_file):
    """Kör ffprobe en gång och returnerar full JSON (format + streams)."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", input_file],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        print("[FEL] ffprobe hittades inte. Är ffmpeg/ffprobe installerat och i PATH?")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[FEL] ffprobe misslyckades: {e.stderr.strip()}")
        sys.exit(1)
    return json.loads(result.stdout)


def find_creation_time(ffprobe_data, verbose=False):
    tags = ffprobe_data.get("format", {}).get("tags", {})
    ct = tags.get("creation_time")
    if verbose and ct:
        print(f"[INFO] creation_time hittad via ffprobe: {ct}")
    return ct


def find_gopro_met_track(ffprobe_data, verbose=False):
    """Hittar streamindex för spåret vars handler_name innehåller 'GoPro MET'."""
    for stream in ffprobe_data.get("streams", []):
        handler = stream.get("tags", {}).get("handler_name", "")
        if "gopro met" in handler.lower():
            idx = stream["index"]
            if verbose:
                print(f"[INFO] GoPro MET-spår hittat: index {idx} (handler_name='{handler}')")
            return idx
    return None


def extract_gpmf_track(input_file, track_index, tmp_path, verbose=False):
    cmd = ["ffmpeg", "-y", "-i", input_file, "-codec", "copy",
           "-map", f"0:{track_index}", "-f", "rawvideo", tmp_path]
    if verbose:
        print(f"[INFO] Kör: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        print("[FEL] ffmpeg hittades inte. Är ffmpeg installerat och i PATH?")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[FEL] ffmpeg-extraktion misslyckades: {e.stderr.strip()}")
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
    Returnerar (cluster_start, points) där points saknar 'time' — det sätts
    senare i ett interpoleringssteg som känner till NÄSTA klusters starttid.
    """
    scal      = None
    gpsfix    = 3
    stnm      = ""
    stmp_us   = None   # mikrosekunder från videostart för detta kluster

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

    if gps9_offset is None or scal is None:
        return None, []

    if video_start_time and stmp_us is not None:
        cluster_start = video_start_time + timedelta(microseconds=stmp_us)
    else:
        cluster_start = None

    n_fields = gps9_size // 4
    if len(scal) == 1:
        scales = [scal[0]] * n_fields
    else:
        scales = list(scal) + [scal[-1]] * max(0, n_fields - len(scal))

    if verbose:
        print(f"      GPS9: {gps9_repeat} punkter, scales={scales[:5]}, cluster_start={cluster_start}")

    points = []
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

        points.append({
            "lat":   lat,
            "lon":   lon,
            "alt":   alt,
            "speed": spd2d * 3.6,  # km/h
            "fix":   gpsfix,
        })

    return cluster_start, points


def parse_devc(data, offset, end, video_start_time, verbose=False):
    """Returnerar en lista av (cluster_start, points) — en post per GPS-kluster i detta DEVC-block."""
    clusters = []
    while offset + 8 <= end:
        hdr = read_header(data, offset)
        if not hdr:
            break
        fourcc, type_char, size, repeat = hdr
        payload_start = offset + 8
        payload_end   = payload_start + size * repeat

        if fourcc == "STRM" and type_char == 0:
            cluster_start, pts = parse_strm(data, payload_start, payload_end,
                                             video_start_time, verbose=verbose)
            if pts:
                clusters.append((cluster_start, pts))

        offset = next_offset(offset, size, repeat)
    return clusters


def parse_gpmf(data, video_start_time, verbose=False):
    """
    Samlar alla GPS-kluster i filordning, tidsstämplar sedan punkterna genom
    att interpolera mellan varje klusters starttid och nästa klusters
    starttid (istället för att anta en fast samplingsfrekvens).
    """
    all_clusters = []
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
            clusters = parse_devc(data, payload_start, payload_end,
                                  video_start_time, verbose=verbose)
            all_clusters.extend(clusters)

        offset = next_offset(offset, size, repeat)

    if verbose:
        print(f"\nTotalt: {devc_count} DEVC-block, {len(all_clusters)} GPS-kluster")

    # Dela upp i kluster med känd starttid (interpolerbara) och utan (okända).
    timed_clusters   = [(t, pts) for t, pts in all_clusters if t is not None]
    untimed_clusters = [(t, pts) for t, pts in all_clusters if t is None]

    # Klustren ska redan komma i stigande STMP-ordning ur filen, men var säker.
    timed_clusters.sort(key=lambda c: c[0])

    all_points = []
    prev_span_per_point = None  # fallback om sista klustrets nästa-starttid saknas

    for i, (start, pts) in enumerate(timed_clusters):
        n = len(pts)
        if i + 1 < len(timed_clusters):
            next_start = timed_clusters[i + 1][0]
            span = (next_start - start).total_seconds()
            # Skydd mot avvikande/negativa spann (t.ex. filhopp) — falla tillbaka
            if span <= 0 or span > 5:
                span = None
        else:
            span = None

        if span is not None and n > 0:
            step = span / n
        elif prev_span_per_point is not None:
            step = prev_span_per_point
        else:
            step = 1.0 / 10.0  # rimlig defaultfallback (~10Hz) om inget annat finns

        if n > 0 and span is not None:
            prev_span_per_point = step

        for j, p in enumerate(pts):
            p["time"] = start + timedelta(seconds=j * step)
            all_points.append(p)

    for _, pts in untimed_clusters:
        for p in pts:
            p["time"] = None
            all_points.append(p)

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

def parse_creation_time(ct_str):
    ct = ct_str.replace("Z", "+00:00")
    if "+" not in ct and "-" not in ct[10:]:
        ct += "+00:00"
    dt = datetime.fromisoformat(ct)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def main():
    parser = argparse.ArgumentParser(
        description="Extrahera GPS från en GoPro MAX/MAX2 .360-fil (eller redan extraherad "
                     ".bin-fil) till GPX"
    )
    parser.add_argument("input",  help="GoPro .360-fil (eller .bin om redan extraherad)")
    parser.add_argument("output", help="GPX-outputfil (t.ex. GS010004.gpx)")
    parser.add_argument("--track", type=int, default=None,
                        help="Forcera streamindex (annars auto-detekteras 'GoPro MET' via ffprobe)")
    parser.add_argument("--creation-time", default=None,
                        help="Forcera video-starttid, t.ex. 2026-03-15T10:44:45 "
                             "(annars läses den från .360-filen via ffprobe)")
    parser.add_argument("-v", "--verbose",  action="store_true")
    parser.add_argument("--keep-nofix",     action="store_true",
                        help="Behåll punkter utan GPS-fix (GPSFIX=0)")
    parser.add_argument("--keep-bin",       action="store_true",
                        help="Spara den extraherade GPMF-binärfilen istället för att radera den")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[FEL] Hittar inte: {args.input}")
        sys.exit(1)

    is_bin_input = args.input.lower().endswith(".bin")
    tmp_bin = None

    try:
        if is_bin_input:
            if not args.creation_time:
                print("[FEL] --creation-time krävs när input redan är en .bin-fil "
                      "(ffprobe kan inte läsa creation_time ur en råbinär GPMF-fil).")
                sys.exit(1)
            video_start_time = parse_creation_time(args.creation_time)
            gpmf_path = args.input
        else:
            print(f"[INFO] Läser metadata från {args.input} (ffprobe)...")
            ffprobe_data = run_ffprobe_json(args.input)

            ct_str = args.creation_time or find_creation_time(ffprobe_data, verbose=args.verbose)
            if not ct_str:
                print("[FEL] Kunde inte hitta creation_time via ffprobe. Ange manuellt med --creation-time.")
                sys.exit(1)
            video_start_time = parse_creation_time(ct_str)

            track = args.track if args.track is not None else find_gopro_met_track(ffprobe_data, verbose=args.verbose)
            if track is None:
                print("[FEL] Hittade inget 'GoPro MET'-spår via ffprobe. Ange manuellt med --track.")
                sys.exit(1)

            if args.keep_bin:
                tmp_bin = os.path.splitext(args.output)[0] + ".bin"
            else:
                fd, tmp_bin = tempfile.mkstemp(suffix=".bin")
                os.close(fd)

            print(f"[INFO] Extraherar GPMF-spår {track} med ffmpeg...")
            extract_gpmf_track(args.input, track, tmp_bin, verbose=args.verbose)
            gpmf_path = tmp_bin

        print(f"[INFO] Video starttid: {video_start_time}")
        print(f"[INFO] Läser {gpmf_path} ({os.path.getsize(gpmf_path)/1024:.0f} KB)...")
        with open(gpmf_path, "rb") as f:
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
    finally:
        if tmp_bin and not args.keep_bin and os.path.exists(tmp_bin) and not is_bin_input:
            os.remove(tmp_bin)


if __name__ == "__main__":
    main()
