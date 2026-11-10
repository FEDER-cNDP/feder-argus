---
name: toksearch-mast-imas
description: "Reach MAST / MAST-U data by IMAS path rather than by group name: MastImasSignal('summary.global_quantities.ip') and list_imas_paths(shot, ids=...) to discover what a shot actually carries. USE for MAST or MAST-U when the quantity is known by its IMAS path, or when the group and variable names for a shot are unknown."
user-invocable: false
license: Apache-2.0
compatibility: standard library plus toksearch_mast; runs in the image or locally
metadata:
  author: DeepTok, correcting GA-FDP toksearch_mast 0.1.3
  version: "1.1"
  url: https://github.com/GA-FDP/toksearch_mast
---

# toksearch-mast-imas -- MAST by IMAS path

FAIR MAST level-2 is IMAS-native: each diagnostic group is an IDS, and every
variable carries its own IMAS path. So a quantity can be fetched by path
without first knowing which group holds it.

```python
from toksearch import Pipeline
from toksearch_mast import MastImasSignal, setup_environment

setup_environment()
pipe = Pipeline([30421])
pipe.fetch("ip", MastImasSignal("summary.global_quantities.ip"))
```

Everything in [[toksearch-mast-fdp]] applies here too: times come back in
MILLISECONDS, absent samples are NaN rather than missing, and no token is
ever needed.

## Discovering what a shot carries

`list_imas_paths` reads the shot's Zarr store directly, so it works in this
environment:

```python
from toksearch_mast import list_imas_paths
df = list_imas_paths(shot, ids="summary")   # name the IDS -- much faster
```

It returns one row per variable with columns `imas`, `ids`, `variable`,
`units`, `uda_name`. Measured on shot 30421: `ids="summary"` returned 6 paths
in about two seconds, where scanning every IDS opens one store per group and
takes far longer. Name the IDS whenever you know it.

Use this before reporting that MAST lacks a quantity. Coverage varies by shot
and campaign, so "this shot does not carry it" and "MAST does not have it"
are different statements and only the first is supportable from one shot.

## The catalog helpers do not work here

`list_shots()` and `list_signals()` query `https://mastapp.site`, which is not
reachable from this environment: both hang for about 130 seconds and then
raise `URLError: Connection timed out`. `list_imas_paths` is unaffected
because it reads the store on S3 instead.

To enumerate shots rather than signals, list the S3 store -- see
[[toksearch-mast-fdp]].

## Relation to the DIII-D IMAS route

This is the MAST analogue of `toksearch_d3d.D3dImasSignal`, and it resolves a
path by direct attribute lookup, so no composer step is involved. The two
devices expose different IDS coverage: a path that resolves on one may be
absent on the other, and that is a property of the delivery rather than of
the lookup. Check each device separately rather than carrying a path across.
