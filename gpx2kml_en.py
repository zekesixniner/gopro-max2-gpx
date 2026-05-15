#!/usr/bin/env python3
"""
gpx2kml.py
==========
Converts GPX files to KML for viewing in Google Earth.

Creates:
  - Vertical lines down to ground level (every N points)
  - A line along the flight path at correct altitude

Usage:
  python3 gpx2kml.py input.gpx
  python3 gpx2kml.py input.gpx --output output.kml
  python3 gpx2kml.py input.gpx --interval 20
  python3 gpx2kml.py input.gpx --color ff0000ff --width 3
"""

import argparse
import os
import sys
import xml.etree.ElementTree as ET


def gpx2kml(gpx_path, output_path, interval, color, width):
    tree = ET.parse(gpx_path)
    root = tree.getroot()
    ns   = {"gpx": "http://www.topografix.com/GPX/1/1"}
    pts  = root.findall(".//gpx:trkpt", ns)

    if not pts:
        print(f"[ERROR] No trackpoints found in {gpx_path}")
        sys.exit(1)

    # Vertical stakes every N points
    stakes = []
    for i, p in enumerate(pts):
        if i % interval != 0:
            continue
        lat = p.get("lat")
        lon = p.get("lon")
        ele = p.find("gpx:ele", ns)
        alt = ele.text if ele is not None else "0"
        stakes.append(f"""    <Placemark>
      <styleUrl>#stake</styleUrl>
      <LineString>
        <altitudeMode>absolute</altitudeMode>
        <coordinates>
          {lon},{lat},{alt}
          {lon},{lat},0
        </coordinates>
      </LineString>
    </Placemark>""")

    # Flight path
    coords = []
    for p in pts:
        lat = p.get("lat")
        lon = p.get("lon")
        ele = p.find("gpx:ele", ns)
        alt = ele.text if ele is not None else "0"
        coords.append(f"{lon},{lat},{alt}")

    route = f"""    <Placemark>
      <styleUrl>#route</styleUrl>
      <LineString>
        <altitudeMode>absolute</altitudeMode>
        <coordinates>
          {' '.join(coords)}
        </coordinates>
      </LineString>
    </Placemark>"""

    name = os.path.splitext(os.path.basename(gpx_path))[0]

    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{name}</name>
    <Style id="stake">
      <LineStyle>
        <color>{color}</color>
        <width>{width}</width>
      </LineStyle>
    </Style>
    <Style id="route">
      <LineStyle>
        <color>{color}</color>
        <width>{width}</width>
      </LineStyle>
    </Style>
{route}
{''.join(stakes)}
  </Document>
</kml>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(kml)

    print(f"Done!")
    print(f"  GPX points: {len(pts)}")
    print(f"  Stakes:     {len(stakes)} (every {interval} points)")
    print(f"  Output:     {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert GPX to KML with vertical stakes and flight path"
    )
    parser.add_argument("input",             help="GPX input file")
    parser.add_argument("--output",          help="KML output file (default: same name as input)")
    parser.add_argument("--interval", type=int, default=10,
                        help="Number of points between each stake (default: 10)")
    parser.add_argument("--color",    default="ff00ffff",
                        help="Line color in KML AABBGGRR format (default: ff00ffff = yellow)")
    parser.add_argument("--width",    type=int, default=2,
                        help="Line width in pixels (default: 2)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[ERROR] File not found: {args.input}")
        sys.exit(1)

    output = args.output or args.input.replace(".gpx", ".kml")
    gpx2kml(args.input, output, args.interval, args.color, args.width)


if __name__ == "__main__":
    main()
