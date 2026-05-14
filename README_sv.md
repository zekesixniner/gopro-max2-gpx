# GoPro MAX2 – GPS-extraktion till GPX

Verktyg för att extrahera GPS-data från GoPro MAX2 `.360`-filer och spara som standard GPX-format.

---

## Innehåll

- [Bakgrund](#bakgrund)
- [Krav](#krav)
- [Installation](#installation)
- [Steg-för-steg](#steg-for-steg)
- [Verifiera resultatet](#verifiera-resultatet)
- [Tekniska detaljer](#tekniska-detaljer)
- [Kända begränsningar](#kanda-begransningar)

---

## Bakgrund

GoPro MAX2 lagrar GPS-data som **GPMF-telemetri** inbäddad i `.360`-filen – inte som vanlig GPX. Formatet använder `GPS9`-taggar (9 fält, 32 bytes per punkt) och `STMP`-tidsstämplar istället för det äldre `GPS5`/`GPSU`-formatet som används av äldre GoPro-kameror.

Scriptet `gpmf2gpx.py` hanterar detta format och producerar en standard GPX-fil med tidsstämplar, koordinater och höjd.

---

## Krav

### System

```bash
sudo apt-get install -y ffmpeg python3 python3-pip python3-venv
```

### Python-miljö

```bash
python3 -m venv ~/gpx360env
source ~/gpx360env/bin/activate
pip install gpxpy
```

> **OBS:** Aktivera alltid den virtuella miljön innan du kör scriptet:
> ```bash
> source ~/gpx360env/bin/activate
> ```

---

## Installation

```bash
git clone <detta-repo>
cd <detta-repo>

python3 -m venv ~/gpx360env
source ~/gpx360env/bin/activate
pip install gpxpy
```

---

## Steg-för-steg

### Steg 1: Hämta videons starttid

Hämta `creation_time` från **MP4-filen** exporterad av GoPro Player (inte från `.360`-filen):

```bash
ffprobe -v quiet -show_format GS010004.mp4 | grep creation_time
```

Exempel:
```
TAG:creation_time=2026-03-15T10:44:45.000000Z
```

> **Viktigt:** Använd alltid `creation_time` från MP4-filen. `.360`-filens interna tid kan ha fel datum.

---

### Steg 2: Extrahera GPMF-telemetri

GPS-datan ligger i spår 3 (`GoPro MET`) i `.360`-filen:

```bash
ffmpeg -y -i GS010004.360 -codec copy -map 0:3 -f rawvideo GS010004.bin
```

Verifiera att rätt spår används:

```bash
ffprobe -v quiet -show_streams GS010004.360 | grep handler_name
```

Leta efter raden med `GoPro MET`. Om det inte är spår 3, justera `-map`-argumentet.

---

### Steg 3: Konvertera till GPX

```bash
python3 gpmf2gpx.py GS010004.bin GS010004.gpx \
  --creation-time 2026-03-15T10:44:45
```

Flaggor:

| Flagga | Beskrivning |
|---|---|
| `--creation-time` | Videons starttid från steg 1 (obligatorisk) |
| `--keep-nofix` | Behåll punkter utan GPS-fix |
| `--verbose` | Visa detaljerad parsing-info |

Förväntat output:
```
[INFO] Video starttid: 2026-03-15 10:44:45+00:00
[INFO] Läser GS010004.bin (4585 KB)...
[INFO] Parsar GPMF-telemetri...
[INFO] Hittade 3485 GPS-punkter

OK Klar!
   Sparade:  3485 punkter -> GS010004.gpx
   Latitud:   56.26577 - 56.32257
   Longitud:  12.85556 - 12.92190
   Hojd:      17 - 708 m
   Hastighet: 0 - 214.8 km/h
   Starttid:  2026-03-15 10:44:45.628247+00:00
   Sluttid:   2026-03-15 10:50:33.602820+00:00
```

---

## Verifiera resultatet

```bash
python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('GS010004.gpx')
root = tree.getroot()
ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
pts = root.findall('.//gpx:trkpt', ns)
times = [p.find('gpx:time', ns).text for p in pts if p.find('gpx:time', ns) is not None]
eles = [float(p.find('gpx:ele', ns).text) for p in pts if p.find('gpx:ele', ns) is not None]
print(f'Punkter: {len(pts)}')
print(f'Start:   {times[0]}')
print(f'Slut:    {times[-1]}')
print(f'Hojd:    {min(eles):.0f} - {max(eles):.0f} m')
"
```

---

## Tekniska detaljer

`gpmf2gpx.py` hanterar GoPro MAX2:s specifika GPMF-format:

- Parsar rekursiv GPMF-struktur: `DEVC` -> `STRM` -> `GPS9`
- Hanterar `GPS9`-format (32 bytes, 8 fält per punkt)
- Använder `STMP` (mikrosekunder från videostart) för tidsstämpling
- Ignorerar okända taggar som `PRJT` utan att krascha
- GPS-frekvens: ~18 Hz

---

## Kända begränsningar

| Problem | Orsak | Lösning |
|---|---|---|
| Spårnummer inte 3 | Beror på kamerainställningar | Kör `ffprobe` och leta efter `GoPro MET` |
| Inga tidsstämplar i GPX | MAX2 använder inte `GPSU` | Scriptet använder `STMP` + `--creation-time` |
| Fel datum i GPX | `.360`-filens interna tid | Använd alltid `creation_time` från MP4-filen |

---

## Testat med

- GoPro MAX2, firmware H24.02.01.22.00
- Ubuntu 24.04 / WSL2 på Windows 11
- Python 3.14
- ffmpeg 8.0.1
