#!/usr/bin/env python3
"""
gpx2kml.py
==========
Konverterar GPX-filer till KML för visning i Google Earth.

Skapar:
  - Gula vertikala linjer ner till marken (var N:e punkt)
  - Gul linje längs flygvägen på korrekt höjd

Användning:
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
        print(f"[FEL] Inga trackpoints hittades i {gpx_path}")
        sys.exit(1)

    # Vertikala linjer var N:e punkt
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

    # Flygvägen
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

    print(f"Klar!")
    print(f"  GPX-punkter: {len(pts)}")
    print(f"  Pinnar:      {len(stakes)} (var {interval}:e punkt)")
    print(f"  Output:      {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Konverterar GPX till KML med vertikala pinnar och flygväg"
    )
    parser.add_argument("input",             help="GPX-fil")
    parser.add_argument("--output",          help="KML-outputfil (standard: samma namn som input)")
    parser.add_argument("--interval", type=int, default=10,
                        help="Antal punkter mellan varje pinne (standard: 10)")
    parser.add_argument("--color",    default="ff00ffff",
                        help="Linjefärg i KML AABBGGRR-format (standard: ff00ffff = gul)")
    parser.add_argument("--width",    type=int, default=2,
                        help="Linjebredd i pixlar (standard: 2)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[FEL] Hittar inte: {args.input}")
        sys.exit(1)

    output = args.output or args.input.replace(".gpx", ".kml")
    gpx2kml(args.input, output, args.interval, args.color, args.width)


if __name__ == "__main__":
    main()
