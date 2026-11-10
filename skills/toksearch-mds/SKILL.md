---
name: toksearch-mds
description: MDSplus-specific data access in TokSearch - trees, signal paths, tag enumeration, and DIII-D data retrieval over Pelican
license: Apache-2.0
compatibility: Designed for deepagents CLI with fdp-d3d
metadata:
  author: GA-FDP / DeepTok
  version: "2.0"
  url: https://ga-fdp.github.io/toksearch/
---

# TokSearch MDSplus Skill

## Note on Data Access

In this environment DIII-D data is served from the Pelican mirror. Run every data
script with the fdp wrapper; read the `d3d-shot-fetcher` skill first for the exact
execution command. For D-alpha filterscopes read `d3d-filterscopes`.

## MdsSignal API (toksearch 2.8.1)

```python
from toksearch import MdsSignal

# Expression and tree name are SEPARATE arguments. Use a raw string for the
# backslash. Do NOT use the "\tree::signal" combined syntax. Do NOT pass a shot
# (the Pipeline supplies it).
sig = MdsSignal(r"\ipmhd", "efit01")

# 2D / multi-dim signals declare their dims and data order:
psirz = MdsSignal(r"\psirz", "efit01", dims=("r", "z", "times"),
                  data_order=["times", "z", "r"])
```

Signature: `MdsSignal(expression, treename, location=None, dims=('times',),
data_order=None, fetch_units=True)`. There is no `shot` parameter.

## Trees that work here

- `efit01` — computed equilibrium (EFIT). Verified.
- `spectroscopy` — raw diagnostics incl. D-alpha filterscopes. Verified.
- Many others (efit variants, transp, zipfit, onetwo, electrons, ...) are set up
  by the environment and are generally reachable. A tree/signal that is missing
  for a shot appears in `rec.errors`, it does not crash the run.

Common `efit01` signals: `\kappa` (elongation), `\ipmhd` (plasma current, A),
`\psirz` (2D flux), `\betap`, `\betat`, `\q95`, `\wmhd`, `\ne`, `\t_e`.

## Signals return DICTS, not tuples

A fetched signal is a dict with keys `data`, `times`, `units`. Extract the array
before using numpy — never unpack it as a tuple.

```python
sig = rec["ip"]                 # {'data':..., 'times':..., 'units':...}
data = sig["data"]              # numpy array
times = sig["times"]            # time base (often in ms for DIII-D)
units = sig["units"]["data"]    # e.g. 'A'
import numpy as np
print(np.max(data), units)
```

## Error handling (2.8.1)

`rec.errors` is a dict of {field_name: error} for fetches that failed. There is
NO `rec.has_error(...)` method.

Check one field on a record:

```python
if "ip" in rec.errors:           # this field failed to fetch
    print(rec.errors["ip"])
```

Drop every record that had a fetch error, using a separate pipeline step:

```python
pipeline = Pipeline(shots)
pipeline.fetch("ip", MdsSignal(r"\ip", "efit01"))

@pipeline.where                  # `where` and `map` DO work as decorators
def ok(rec):
    return not rec.errors        # keep only records with no fetch errors
```

## Fetch example

```python
from toksearch import Pipeline, MdsSignal
import numpy as np

p = Pipeline([165340, 165920])
p.fetch("ip", MdsSignal(r"\ipmhd", "efit01"))   # fetch() mutates in place, returns None
results = p.compute_serial()                     # or compute_multiprocessing()

for rec in results:
    if "ip" in rec.errors:
        print(rec["shot"], "no ip"); continue
    data = rec["ip"]["data"]
    print(rec["shot"], "Ip max", np.max(data), rec["ip"]["units"]["data"])
```

Run with (see `d3d-shot-fetcher` -- do NOT hardcode an absolute path to
`fdp`/`python`, it varies by environment):
```
fdp run python script.py
```

## Enumerating what a tree holds (tags)

To discover signal names for a shot, open the tree with the MDSplus API and list
its tags. `findTags` returns BYTES — decode them. Resolve a tag to its real node
path with `getNode(tag).getFullPath()`.

```python
from MDSplus import Tree
t = Tree("spectroscopy", 165920)
tags = sorted({x.decode() if isinstance(x, bytes) else str(x) for x in t.findTags("*")})
print(len(tags), "tags; e.g.", tags[:10])
print(t.getNode(r"\fs04").getFullPath())   # -> \SPECTROSCOPY::TOP.FILTERSCOPE.PMT42:PHOTON_FLUX
```

Tag names do not always encode structure: channel number != PMT number
(`\fs04` -> PMT42, `\FS00` -> PMT24), and a tag may alias a node several levels
deep. Always resolve, never infer.

## Notes

- Signal paths are case-insensitive on lookup but conventionally lower/upper as
  shown; time bases differ between diagnostics; not all shots have all signals.
- Use `compute_serial()` while developing; switch to `compute_multiprocessing()`
  for many shots (see `toksearch-backends`).
