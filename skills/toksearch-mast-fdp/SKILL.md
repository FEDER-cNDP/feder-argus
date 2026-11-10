---
name: toksearch-mast-fdp
description: "MAST / MAST-U data access through the FAIR MAST public Zarr store: the mast FDP device, MastSignal('group/signal'), which level-2 diagnostic groups exist, the millisecond time convention, and why a MAST fetch never needs a token. USE for MAST or MAST-U shots. For DIII-D use the DIII-D skills instead: the devices differ in auth, in which groups exist, and in how absent samples are represented."
user-invocable: false
license: Apache-2.0
compatibility: standard library plus toksearch_mast; runs in the image or locally
metadata:
  author: DeepTok, correcting GA-FDP toksearch_mast 0.1.3
  version: "1.1"
  url: https://github.com/GA-FDP/toksearch_mast
---

# toksearch-mast-fdp -- MAST / MAST-U via FAIR MAST

```python
from toksearch import Pipeline
from toksearch_mast import MastSignal, setup_environment

setup_environment()                      # device="mast"
pipe = Pipeline([30421])
pipe.fetch("ip", MastSignal("summary/ip"))
for rec in pipe.compute_serial():
    sig = rec.get("ip", None)            # Record.get REQUIRES a default
    data, times = sig["data"], sig["times"]
```

`help(toksearch_mast)` holds the full reference. What follows is what this
environment adds to it, and one place where the upstream skill was wrong.

## Times are MILLISECONDS, not seconds

FAIR MAST stores seconds, but `MastSignal` converts: `times` comes back in
**milliseconds** with `units["times"] == "ms"`, matching the toksearch
convention DIII-D already uses. Pass `time_in_ms=False` to get native seconds.

Verified on shot 30421: `summary/ip` returns times -100.0 .. 666.0 with
`units['times'] == 'ms'`.

This matters because the upstream skill states the opposite. Do not insert a
seconds-to-milliseconds conversion: the conversion has already happened, and
applying it again multiplies every MAST timestamp by a thousand. A DIII-D and
a MAST time axis can be compared directly, with no scaling.

## A MAST fetch never needs a token

The FAIR MAST store is public and read anonymously. The `mast` device is
registered with no auth requirement, which `fdp device list` shows as
`[none]`.

So when a MAST fetch fails, the cause is never authentication. Do not run
`%fdp_login`, do not report an expired token, and do not ask the user for
credentials. Diagnose a MAST failure as a missing shot, a missing signal in
that shot, or a network problem, and report which.

## Absent samples are NaN, not missing

A MAST array covers a window wider than the discharge and pads the rest with
NaN. The array has full length and the right units; only some values are
real.

Reduce accordingly, or every answer comes back as nan:

```python
import numpy as np
finite = np.isfinite(data)
peak = np.nanmax(np.abs(data))           # not data.max()
coverage = float(finite.mean())          # how much of the window is real
```

`data.min()` and `data.max()` propagate NaN: a single NaN anywhere makes both
print `nan`. That looks identical to an empty array and is not one. Measure
coverage with `np.isfinite(...).mean()` before concluding a signal is absent.

## Shot discovery: use the store, not the catalog

`list_shots()` and `list_signals()` query the parquet catalog at
`https://mastapp.site`, which is **not reachable from this environment** --
the call hangs and then raises `URLError: Connection timed out`. Do not wait
on it and do not report it as the dataset being unavailable.

The Zarr store on S3 is reachable, so enumerate from it instead:

```python
import urllib.request, re
url = ("https://s3.echo.stfc.ac.uk/mast?list-type=2"
       "&prefix=level2/shots/&delimiter=/&max-keys=1000")
xml = urllib.request.urlopen(url, timeout=60).read().decode()
shots = sorted({int(m) for m in re.findall(r"shots/(\d+)\.zarr/", xml)})
```

A shot absent from the store yields no record at all from `compute_serial()`
rather than an error. Treat that as an expected outcome and say which shots
returned nothing.

## Which groups exist

A shot's level-2 store is a set of IMAS-named groups. List them for the shot
in hand rather than assuming, because coverage varies by shot and campaign:

```python
from toksearch_mast import list_imas_paths
paths = list_imas_paths(shot, ids="summary")   # one IDS is much faster
```

`summary/` carries the global quantities, `equilibrium/` the reconstruction.
Both are per-shot: confirm a signal exists for the shot you are using before
reporting that MAST lacks it.

## Where files go

Write every file you produce into the working folder for this notebook, as
with any other skill. Nothing about MAST changes that.
