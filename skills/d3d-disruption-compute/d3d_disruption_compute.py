"""Compute DIII-D disruption parameters from raw signals, with disruption-py.

This is the COMPUTE side. The stored index (`d3d-disruption`) already holds
disruption-py output for the shots someone has already run; this runs it afresh,
which is what a shot outside that index needs.

It is a wrapper around a subprocess, and that is not an implementation detail.
disruption-py needs stock MDSplus and must not see toksearch, ptdata or XRootD,
so it lives in a separate environment inside the image. Importing it here would
fail; calling it over a pipe is the whole design.

Signals come from the FDP origin rather than an on-site MDSplus server. The
origin runs an mdsip relay speaking the ordinary thin-client protocol, so
disruption-py itself is unmodified -- only its connection string differs.

EVERY CALL TAKES A GROUP OF SHOTS. One subprocess, one set of MDSplus sessions,
one pass. A loop calling this per shot pays the whole start-up cost each time
and opens a new session per shot.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d3d_lakehouse import query as _query   # noqa: E402

DPY_PYTHON = os.environ.get(
    "DPY_PYTHON", "/opt/conda/envs/disruption-py-fdp/bin/python")

# The origin's mdsip relay. Derived from the fdp catalog when available so this
# follows a device-catalog change rather than needing an edit here.
DEFAULT_ORIGIN = "fdp://fdp-d3d-origin.nationalresearchplatform.org:8443/mdsip"


class DisruptionPyUnavailable(RuntimeError):
    """The disruption-py environment is not present or did not start."""


class ComputeFailed(RuntimeError):
    """disruption-py ran and returned an error."""


def available():
    """Whether the disruption-py environment is usable from here."""
    if not os.path.exists(DPY_PYTHON):
        return False
    r = subprocess.run([DPY_PYTHON, "-c", "import disruption_py"],
                       capture_output=True, text=True)
    return r.returncode == 0


def origin_url():
    """The mdsip endpoint disruption-py is pointed at."""
    try:
        from fdp import catalog                                  # noqa: PLC0415
        server = catalog["d3d"].schema.origin_server             # root://host:port
        return "fdp://" + server.split("://", 1)[-1] + "/mdsip"
    except Exception:                                            # noqa: BLE001
        return DEFAULT_ORIGIN


_RUNNER = r'''
import json, sys
import numpy as np
from disruption_py.core.utils.shared_instance import SharedInstance
from disruption_py.inout.mds import ProcessMDSConnection
from disruption_py.inout.sql import DummyDatabase
from disruption_py.machine.tokamak import Tokamak
from disruption_py.settings import RetrievalSettings
from disruption_py.workflow import get_shots_data

cfg = json.loads(sys.argv[1])
ORIGIN = cfg["origin"]

# Module-level: connection_initializer is pickled to workers when
# num_processes > 1. SharedInstance keeps ONE mdsip session per worker; a bare
# ProcessMDSConnection opens one per shot and exhausts the origin's limit.
def fdp_connection():
    return SharedInstance(ProcessMDSConnection).get_instance(ORIGIN)

extra = {}
if cfg["use_sql"]:
    settings = RetrievalSettings(run_columns=cfg["columns"])
else:
    settings = RetrievalSettings(
        run_columns=cfg["columns"],
        efit_nickname_setting="default",
        time_setting=np.arange(*cfg["timebase"]),
    )
    extra["database_initializer"] = DummyDatabase.initializer

df = get_shots_data(
    tokamak=Tokamak.D3D,
    shotlist_setting=cfg["shots"],
    retrieval_settings=settings,
    connection_initializer=fdp_connection,
    output_setting="dataframe",
    num_processes=cfg["num_processes"],
    **extra,
)
df.to_csv(cfg["out"], index=False)
print(json.dumps({"rows": int(len(df)), "columns": list(df.columns)}))
'''


def compute(shots, columns=("ip", "beta_n", "li", "kappa"), use_sql=False,
            timebase=(0.1, 3.0, 0.02), num_processes=1, timeout=1800):
    """Disruption parameters for a GROUP of shots, computed from raw signals.

    `shots` is a list. `columns` names the disruption-py methods to run; the
    full set is large and slow, so ask for what the question needs.

    `use_sql=False` is the default because it is the only thing that works away
    from GA: disruption times and EFIT-tree selection live in GA's d3drdb, which
    is not reachable off-site. Without it disruption-py cannot know when a shot
    disrupted, so **`time_until_disrupt` is empty and the EFIT tree is pinned**.
    A question about how long before a disruption something happened cannot be
    answered from this path -- the stored index (`d3d-disruption`) carries that
    column already, and is where such a question belongs.

    Returns (rows, meta). `rows` is a list of dicts, one per (shot, time)
    sample. `meta` carries the row count and the columns actually produced,
    which is not always what was asked for: a method that fails for a shot
    leaves its column out rather than raising.
    """
    shots = list(shots)
    if not shots:
        raise ValueError("compute() needs at least one shot")
    if not available():
        raise DisruptionPyUnavailable(
            "the disruption-py environment is not usable at %s. This skill runs "
            "disruption-py in a separate environment; in an image without it, "
            "the stored index (d3d-disruption) is the only disruption source."
            % DPY_PYTHON)

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.csv")
        cfg = {"shots": shots, "columns": list(columns), "use_sql": bool(use_sql),
               "timebase": list(timebase), "num_processes": int(num_processes),
               "origin": origin_url(), "out": out}
        runner = os.path.join(tmp, "runner.py")
        with open(runner, "w") as fh:
            fh.write(_RUNNER)
        env = dict(os.environ)
        env.setdefault("USER", "jovyan")     # disruption-py builds a path from it
        try:
            proc = subprocess.run([DPY_PYTHON, runner, json.dumps(cfg)],
                                  capture_output=True, text=True,
                                  timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            raise ComputeFailed(
                "disruption-py did not finish within %ds for %d shot(s). It "
                "fetches every signal over the network; narrow `columns` or "
                "the shot list rather than raising the timeout first."
                % (timeout, len(shots))) from None
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]
            raise ComputeFailed("disruption-py failed:\n  " + "\n  ".join(tail))
        meta = {}
        for line in (proc.stdout or "").strip().splitlines():
            if line.startswith("{"):
                try:
                    meta = json.loads(line)
                except ValueError:
                    pass
        rows = []
        if os.path.exists(out):
            import csv                                           # noqa: PLC0415
            with open(out) as fh:
                for r in csv.DictReader(fh):
                    rows.append({k: (float(v) if _isnum(v) else v)
                                 for k, v in r.items()})
        return rows, meta


def _isnum(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


# There is deliberately no `columns_available()` here. disruption-py's method
# metadata is not exposed by any public attribute I could verify against this
# build, and a discovery helper that silently returns an empty list is worse
# than none. Two verified routes exist instead:
#
#   * `meta["columns"]` from compute() -- what a real run actually produced.
#   * the `d3d-disruption` skill's `parameters()` -- every parameter name, its
#     long name, units and method, from the stored index.


# --------------------------------------------------------------------------
# Disruption times, so a computed shot can carry a countdown
# --------------------------------------------------------------------------
# WHERE THIS NUMBER COMES FROM, because it is not the same source as the
# stored index's `time_until_disrupt`:
#
#   d3drdb.disruptions.t_disrupt, served from our lakehouse copy of d3drdb.
#   One row per shot, 24,219 shots, every one carrying a t_disrupt.
#
# disruption-py's own `time_until_disrupt` comes from GA's live SQL server,
# which is unreachable off-site -- that is why `use_sql=False` is the default
# and why the computed output has no countdown of its own. This fills that in
# from the lakehouse instead.
#
# Say which source a countdown came from when reporting it. A number labelled
# `time_until_disrupt` that came from here and one that came from the stored
# index are not interchangeable, and a reader cannot tell them apart.


def disruption_times(shots):
    """`t_disrupt` in seconds for a GROUP of shots, from the lakehouse d3drdb.

    Returns {shot: t_disrupt} containing only the shots that have one. A shot
    missing from the result did not disrupt, or no disruption time was
    recorded for it -- those two are not distinguished here, so do not report
    an absent shot as "did not disrupt".
    """
    shots = [int(s) for s in shots]
    if not shots:
        return {}
    rows = _query("SELECT shot, t_disrupt FROM d3drdb.disruptions "
                  "WHERE shot IN (?) AND t_disrupt IS NOT NULL", (shots,))
    return {int(r["shot"]): float(r["t_disrupt"]) for r in rows}


def add_time_until_disrupt(rows, times=None):
    """Add a `time_until_disrupt` column to computed rows, in seconds.

    `times` is the mapping from `disruption_times()`; it is looked up for you
    when omitted. Rows for a shot with no disruption time are left without the
    column rather than given a null, so its absence stays visible.

    The value is `t_disrupt - time`, and it is NEGATIVE after the disruption.
    It is not clamped: a negative number means the sample is past the quench,
    which is a fact worth seeing rather than hiding at zero.
    """
    if times is None:
        times = disruption_times({int(r["shot"]) for r in rows if "shot" in r})
    for r in rows:
        shot = int(r.get("shot", -1))
        if shot in times and "time" in r:
            r["time_until_disrupt"] = times[shot] - float(r["time"])
    return rows


def timebase_covering(shots, start=0.1, step=0.02, pad=0.1):
    """A timebase that reaches the LAST disruption among `shots`.

    The default timebase stops at 3.0 s, which is before most DIII-D
    disruptions: a countdown computed over it never approaches zero, so a
    question about the moments before a disruption cannot be answered from it
    however carefully the countdown was derived. This returns a
    `(start, stop, step)` triple that runs past the latest disruption in the
    group, for passing to `compute(timebase=...)`.

    `compute()` applies ONE timebase to every shot, so for a group this runs
    past the earlier disruptions too -- their samples carry a negative
    countdown, which is correct and visible rather than silently trimmed.

    Returns None when no shot in the group has a disruption time, because
    there is then nothing to reach.
    """
    times = disruption_times(shots)
    if not times:
        return None
    return (start, max(times.values()) + pad, step)


# --------------------------------------------------------------------------
# Where output files belong
# --------------------------------------------------------------------------
# Ported verbatim from the d3d-materials skill, which learned it the hard way.
# A script written into the working folder and run by absolute path leaves the
# process in the NOTEBOOK's folder, one level up, so a bare relative filename
# lands outside the working folder and is swept back.
#
# `working_dir()` ends in a separator on purpose: `working_dir() + "name.csv"`
# is the natural way to build a destination, and without the separator it
# produces a SIBLING of the folder rather than a file inside it.

def _resolve_working_dir():
    """The notebook's working folder -- where fetched files belong.

    NOT the current directory. A script may be run from anywhere (`python
    /abs/path/script.py` leaves the process in the notebook's own folder, one
    level up), and a file written there is outside the working folder: it gets
    swept back, re-fetched by the next script, and swept again. Resolving
    against the exported working folder makes the destination the same no
    matter how the script was invoked, which is also what lets the local-copy
    check actually hit.
    """
    here = os.environ.get("SAGE_OUTPUT_DIR")
    if here and os.path.isdir(here):
        return here
    # The variable is normally exported, but a subprocess that does not inherit
    # it falls back to the current directory -- which for a script launched by
    # absolute path is the notebook's own folder, one level up. A file written
    # there is outside the working folder: it gets swept back, and the script
    # that looks for it next by the same relative name no longer finds it and
    # regenerates it. The working folder is identifiable without the variable,
    # so find it rather than write to the wrong place and be corrected.
    cwd = os.getcwd()
    if os.path.basename(cwd).endswith("_sage_"):
        return cwd
    # The running script's OWN directory, checked before the glob below.
    #
    # Scripts are written into the working folder and run by absolute path,
    # which leaves the process in the notebook's folder one level up. argv[0]
    # then identifies the working folder even when the environment variable did
    # not survive into the subprocess -- and it names the right one, which the
    # glob cannot: a directory holding several notebooks holds several `*_sage_`
    # folders, and that ambiguous case fell through to cwd. Every fetched file
    # then landed outside the working folder and was swept back, once per run,
    # so the fault appeared only after a second notebook was run beside the
    # first.
    try:
        argv0 = os.path.dirname(os.path.abspath(sys.argv[0]))
        if os.path.basename(argv0).endswith("_sage_") and os.path.isdir(argv0):
            return argv0
    except Exception:                                            # noqa: BLE001
        pass
    import glob as _glob
    here = [d for d in _glob.glob(os.path.join(cwd, "*_sage_")) if os.path.isdir(d)]
    return here[0] if len(here) == 1 else cwd


def working_dir():
    """The notebook's working folder, ending in a separator.

    The trailing separator is deliberate. `working_dir() + "name.csv"` is the
    natural way to build a destination, and without it that lands a sibling of
    the folder rather than a file inside it -- a stray the sweep then moves
    back, once for every script that repeats the concatenation. With it the
    naive form is correct, `working_dir() + "/name.csv"` still resolves, and
    `os.path.join()` and `os.path.realpath()` are unaffected.
    """
    return os.path.join(_resolve_working_dir(), "")
