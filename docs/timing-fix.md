# GPS timestamp interpolation fix

## Problem

`gpmf2gpx.py` timestamped points within a GPS9 cluster using a fixed
assumed sample rate:

```python
t = cluster_start + timedelta(seconds=i / 18.0)
```

This assumes 18 Hz spacing *within* every cluster. In practice, a GoPro
MAX2 GPS9 cluster (one per `DEVC` block, roughly once per second) contains
around 7-10 points, not 18. Using `i / 18.0` packed those 7-10 points into
only 0.4-0.55 seconds of synthetic time, then jumped to the next cluster's
real STMP-derived start time. The result was a "burst, then gap" pattern
instead of an even time grid:

```
55.6ms, 55.6ms, 55.6ms, 55.6ms, 55.6ms, 55.6ms, 359.6ms, 55.6ms, ...
```

Position and altitude values were unaffected (they come straight from the
GPS9 payload), but this made the exported GPX unsuitable for anything that
derives motion from consecutive timestamps — instantaneous speed
recalculation, smoothing windows tuned for a nominal rate, or frame-accurate
sync in a downstream tool like OVRLEY.

## Root cause

The camera's actual point rate is not a fixed 18 Hz. Each cluster's `STMP`
value gives an accurate real-world anchor time, but the number of points
inside that cluster (and therefore the real spacing between them) varies.
The old code had the right anchor but the wrong intra-cluster spacing
assumption.

## Fix

`parse_gpmf` now works in two passes:

1. Collect every GPS cluster in the file as `(cluster_start, points)`,
   in file order, without assigning per-point times yet.
2. For each cluster, compute the real elapsed time to the *next* cluster's
   `STMP`-derived start (`span`), and divide by that cluster's point count
   to get the true per-point interval (`step = span / n`). Each point's
   timestamp is `cluster_start + j * step`.

The last cluster in the file has no "next" cluster to interpolate against,
so it falls back to the previous cluster's computed step, or a nominal
10 Hz (`0.1s`) if no earlier cluster is available (e.g. a file with only
one cluster). A sanity check discards implausible spans (`<= 0` or `> 5`
seconds), which would indicate a dropped/corrupt cluster, and falls back
the same way.

## Verification

Simulated against the actual cluster sizes and STMP values observed in
`GS010068.360` (7, 10, 10, 10, 10 points at STMP 413576, 1106522, 2105865,
3107697, 4108000 µs): the fix produces an even ~99-100ms spacing between
points, matching the reference output from
[gopro-telemetry-tool](https://github.com/zekesixniner/gopro-telemetry-tool)
(Juan Irache's `gopro-telemetry`), which interpolates the same way.

Re-running on the full `GS010068.360` file:

| | Before fix | After fix | Reference (gopro-telemetry-tool) |
|---|---|---|---|
| Points | 14076 | 14076 | 14077 |
| End time | 16:35:18.554336 | 16:35:18.952205 | 16:35:19.499000 |
| Delta pattern | 55ms burst + 360-500ms gaps | Even ~100ms | Even ~100ms |

Position, altitude and speed ranges were identical before and after the
fix, as expected — only the timestamp distribution changed.
