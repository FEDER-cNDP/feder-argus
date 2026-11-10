---
name: d3d-disruption-compute
description: "RUN disruption-py to compute DIII-D disruption parameters from raw signals, for shots that are not already in the stored disruption index. Fetches over the Fusion Data Platform origin, so it needs no on-site access. Use when asked to compute, recompute or generate disruption parameters, or when a shot is absent from the stored index. To READ parameters for shots already processed, use the d3d-disruption skill instead: it is immediate, carries disruption timing, and is the right answer for most questions."
license: Apache-2.0
compatibility: runs only inside an image carrying the disruption-py environment
metadata:
  node_type: skill
---

# Computing DIII-D disruption parameters

Two skills cover disruption parameters and they are not interchangeable.

`d3d-disruption` **reads** an index of disruption-py output that someone has
already produced. It answers immediately, it carries `time_until_disrupt`, and
it is the right source for nearly every question.

This skill **runs** disruption-py. It is slower, it reaches the network for
every signal, and off-site it cannot know when a shot disrupted. Reach for it
when a shot is not in the index, or when asked in so many words to compute or
recompute.

**Check the index first.** `d3d-disruption`'s `is_indexed(shot)` answers that in
one call, and a shot already there needs nothing from here.

## Running it

```python
import sys; sys.path.insert(0, "/path/to/this/skill/directory")
import d3d_disruption_compute as dpc

rows, meta = dpc.compute([161228, 161229], columns=("ip", "beta_n", "li", "kappa"))
print(meta["rows"], len(meta["columns"]))
```

Verified output for that call -- two shots, 145 samples each:

```
290 21
```

Twenty-one columns for four requested is not a mistake; see below.

and for a single shot with the same four columns:

```
meta: {'rows': 145, 'columns': ['shot', 'time', 'beta_n', 'beta_p', 'chisq',
       'dbetap_dt', 'dip_dt', 'dipprog_dt', 'dli_dt', 'dwmhd_dt', 'ip',
       'ip_error', 'ip_prog', 'kappa', 'li', 'lower_gap', 'q0', 'q95',
       'qstar', 'upper_gap', 'wmhd']}
sample: {'shot': 161228.0, 'time': 0.1, 'beta_n': 0.1126, 'beta_p': 0.1212,
         'chisq': 7.63, 'dbetap_dt': -0.9716}
```

`rows` is one dict per (shot, time) sample.

## Ask for a GROUP of shots, always

`compute()` takes a list because one call is one subprocess and one set of
MDSplus sessions. Calling it per shot inside a loop pays the whole start-up cost
each time and opens a session per shot, which the origin limits.

## What comes back is not what you asked for

**More columns than requested.** disruption-py runs whole methods, and one
method produces several columns: four requested above returned twenty-one.
Read `meta["columns"]` for what actually arrived rather than assuming.

**Sometimes fewer.** A method that fails for a shot leaves its column out
instead of raising, so a column named in the request and missing from
`meta["columns"]` means that method did not produce it for those shots. Say so
when reporting, rather than treating the column as absent from the machine.

## Disruption timing, and which source it came from

disruption-py's own `time_until_disrupt` comes from GA's live SQL server, which
is unreachable away from the site. That is why `use_sql=False` is the default
and why the computed output carries no countdown of its own.

The disruption TIME is available from our lakehouse instead, and this skill
fills the countdown in from there:

```python
rows, meta = dpc.compute([161228], columns=("ip", "q95"),
                         timebase=dpc.timebase_covering([161228]))
dpc.add_time_until_disrupt(rows)
```

Verified output:

```
timebase_covering([161228]) -> (0.1, 5.1935, 0.02)
rows = 255
samples within 50 ms of the quench: 2
closest: time = 5.080   time_until_disrupt = 0.0135
```

**Use `timebase_covering()` whenever the question is about timing.** The
default timebase stops at 3.0 s, which is before most DIII-D disruptions: a
countdown computed over it never approaches zero, so "what happened just before
the disruption" cannot be answered from it however carefully the countdown was
derived. The helper returns a timebase that runs past the latest disruption in
the group.

**Say where a countdown came from.** `disruption_times()` reads
`d3drdb.disruptions.t_disrupt` from the lakehouse. That is a DIFFERENT source
from the `time_until_disrupt` carried by the stored index, and the two are not
interchangeable -- a reader given a bare column name cannot tell which they are
looking at. Name the source in the answer.

A shot absent from `disruption_times()` has no recorded disruption time. That is
not the same as "it did not disrupt", and reporting it as such states something
the data does not say.

## Write every output file through `working_dir()`

```python
out = dpc.working_dir() + "disruption_params.csv"
df.to_csv(out, index=False)
```

**Not a bare filename, and not a hand-built path.** A script is written into the
working folder and run by absolute path, which leaves the process in the
NOTEBOOK's folder one level up -- so a bare `"disruption_params.csv"` lands
outside the working folder and has to be swept back.

**`working_dir()` already ends in a separator**, which is why the concatenation
above is correct. Building the path by hand and joining it without one --
`WORKDIR + "plot.png"` -- produces a SIBLING of the folder rather than a file
inside it, and the resulting name looks almost right, which is what makes it
hard to spot. Both of these have happened in real runs of this skill.

`os.path.join(dpc.working_dir(), name)` is equally correct if you prefer it.

## Alcator C-Mod cannot be computed here

This skill is DIII-D only, and that is a limit of the platform rather than a
policy. disruption-py only ever speaks to an MDSplus server. DIII-D has one on
its origin, which is what `compute()` connects to. The C-Mod origin runs no
equivalent -- the same request there answers `HTTP 403: Opening path
'/mdsip/connect' is disallowed' -- so there is nothing for disruption-py to
connect to, whatever its own C-Mod support can do on a site that has a server.

Computing it is also unnecessary: the C-Mod output was produced at MIT and
staged on the origin, and the stored C-Mod index is that same dataset. Use the
`cmod-disruption` skill for it.

When asked to compute C-Mod parameters, say which of these applies rather than
declining flatly: the data already exists and is served, and separately, this
installation could not produce it even if it did not.

## When the environment is missing

disruption-py lives in a separate environment, because it needs stock MDSplus
and must not see the data-access stack the rest of the image uses. In an image
built without it, `available()` returns False and `compute()` raises
`DisruptionPyUnavailable` rather than failing deep inside a subprocess. That is
a fact about the installation, not about the shot: report it as such, and fall
back to the stored index.
