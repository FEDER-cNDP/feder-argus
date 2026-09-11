# ARGUS-FEDER

An AI agent that answers questions about DIII-D fusion data, asked in plain
English inside a Jupyter notebook.

A question is typed into a `%%ask` cell. The agent decides what to look up,
writes and runs its own code against the data, checks its own answer against a
set of review criteria, and reports back in prose with the numbers and the
caveats attached. Nothing in the notebooks below is hand-written analysis --
every answer was produced by the agent from the question above it.

## What is in this repository

    examples/jupyterhub/   the notebooks, saved with the answers the agent gave
    skills/                the knowledge modules the agent uses to reach each data source
    image/                 how the runtime image is built (see image/README.md)

The notebooks are saved with their real outputs, so they can be read without
running anything.

## Skills

A skill is what teaches the agent one data source: where it lives, how it is
shaped, and what is easy to get wrong about it. The agent chooses which to use
from the question alone.

| Skill | What it covers |
|---|---|
| `d3d-relational-db` | The DIII-D shot catalogue: which discharges exist and what was recorded about them |
| `d3d-shot-fetcher` | Time-series signals for a shot, over the Pelican data federation |
| `d3d-elm-index` | Stored ELM labels from several detectors and from hand-labelling, with their provenance |
| `d3d-elm-phase-analysis` | Sorting other measurements by where they fall in the ELM cycle |
| `d3d-disruption` | Disruption timing and the parameters recorded around it |
| `d3d-filterscopes` | Filterscope diagnostics |
| `d3d-materials` | Exposed material samples: their treatment history, measurements, and the files behind them |
| `d3d-imas-terms` | Translation between IMAS names and DIII-D names |
| `signal-zoom` | Looking closely at a region of a signal |

## Examples

## Data access and terminology

### Pelican data access, metadata, and PTDATA

ARGUS answering plain-English questions about DIII-D through four different
access paths: resolving a physics concept to the right MDSplus signal with no
symbol name given, querying the shot-metadata database, fetching from PTDATA
(a separate raw-digitizer source), and looking up signal meanings, MDSplus
paths and IMAS names.

[Open the notebook](examples/jupyterhub/argus_feder_pelican_database_ptdata_jupyterhub.ipynb)

### IMAS ↔ DIII-D terminology

Translating between IMAS — the device-neutral standard vocabulary used across
fusion machines and by ITER — and DIII-D's own historical signal names, in both
directions. The mapping is extracted from GA's
[`imas_composer`](https://github.com/GA-FDP/imas_composer) (Apache-2.0) and every
entry was checked by actually fetching it across shots spanning more than two
decades of machine operation. The notebook also exercises what a plain name-pair
table gets wrong: sign conventions that differ between the two vocabularies,
availability that changes over the machine's history, fields whose provenance is
incomplete, and mistyped input.

[Open the notebook](examples/jupyterhub/argus_feder_imas_d3d_jupyterhub.ipynb)

## ELM studies

### FEDER ELM competency questions

FEDER's ELM competency questions answered in plain English, from a stored index
of ELM labels: what each detector defines as an ELM and at which parameters
(Q2), which D-alpha filterscope channels a shot has and at what sampling rate
(Q5, Q7, Q9), where two detectors and a domain expert disagree on the same
discharge (Q12), when the plasma was ELMing and when ELM activity was absent
(Q3), and what a candidate ELM training set would contain (Q4, Q11).

The notebook also asks questions the list does not cover, and two whose correct
answer is a refusal — a shot nobody has analysed, and a population statistic the
sample cannot support. A confident number in either case would be a failure, not
a success.

[Open the notebook](examples/jupyterhub/argus_feder_elm_index_jupyterhub.ipynb)

### Sorting measurements by where they fall in the ELM cycle

An analysis rather than a question: ARGUS uses stored ELM event times to sort
Thomson scattering measurements by where they fall in the ELM cycle, then shows
what an average over everything hides. Thomson samples on its own clock — a few
times faster than the ELMs, but unsynchronised with them — so each profile
lands at an arbitrary point in the cycle, and the naive average blends
crash-phase and recovered plasma into a state the discharge never holds. The
notebook picks a suitable discharge from the stored labels, checks the event
times against a domain expert's before trusting them, and reports where in the
plasma the ELM actually reaches.

[Open the notebook](examples/jupyterhub/argus_feder_elm_phase_analysis_jupyterhub.ipynb)

### Building a training cohort for a published ELM-forecasting study

A research task set by someone else.
[Teo et al. (2026)](https://arxiv.org/abs/2604.06508) train a neural network
to forecast the first ELM after the L-H transition, and state their own
principal limitation twice: the dataset is too small to quantify performance, and
identifying which discharges are relevant for training is a necessary next step.
They used 26 discharges. In six plain-English questions and no code, ARGUS
establishes what labels exist and who produced them, characterises the
distribution of first-ELM times, assembles a candidate cohort of 4,869
discharges, interrogates an anomaly in its own data, grounds one case in the raw
D-alpha signal, and states what the cohort cannot support — including that it
cannot reproduce the original study, because nothing in the data locates the
L-H transition.

[Open the notebook](examples/jupyterhub/argus_feder_elm_forecast_cohort_jupyterhub.ipynb)

### Testing a published claim: do turbulence precursors precede an ELM?

A complete study rather than a query. Joung et al. (*Nucl. Fusion* **64**,
066038, 2024) report that pedestal turbulence in the 15–150 kHz band rises
before an ELM crash. That is a measurement, so it can be tested directly. In
seven plain-English questions and no code, ARGUS finds the BES waveforms — the
`bes` MDSplus tree holds none, and the 64 channels live in another source under
a templated name — picks the edge channels, filters to the band, averages over
every labelled ELM, and states what the result cannot support.

The last two questions are the ones worth reading. Asked whether its estimate
might be using data from after the point it reports, the agent measured its own
look-ahead by impulse injection — 0.30 ms on one deployment, 0.32 ms on the
other, arrived at independently — and redid the analysis causally. Both
deployments find no systematic precursor in the ensemble average; one then
bounds what its design could have detected at all, the other finds an
intermittent rise on about a tenth of ELMs against a false-alarm null.

[Open the notebook](examples/jupyterhub/argus_feder_bes_elm_precursor_jupyterhub.ipynb)

## Disruption studies

### Getting started with DIII-D disruption data

A disruption is a sudden, uncontrolled collapse of the plasma current —
tolerable on a research device, damaging on a power plant, and predicting one
early enough to act is an open problem. This notebook introduces a stored index
of twenty DIII-D shots (ten that disrupted, ten that did not) run through
[disruption-py](https://github.com/MIT-PSFC/disruption-py), the MIT-PSFC
disruption-warning code, with every signal fetched over the Fusion Data
Platform. Eight plain-English questions cover what the data contains, what each
of the 63 parameters means and in what units, what a disruption looks like in
the traces, and how disrupted and non-disrupted shots differ.

The last two questions are about limits rather than results. The source files
carry **no units and no descriptions on any variable**, so the meaning of a
column lives in the index rather than the data; and three parameters return
plausible but wrong values, which the skill blocks rather than warns about. A
question asking what fraction of DIII-D shots disrupt is answered by declining:
twenty shots balanced ten and ten is a constructed slice, not a sample.

[Open the notebook](examples/jupyterhub/argus_feder_disruption_basics_jupyterhub.ipynb)

### Answering GA's disruption competency questions

General Atomics' competency-question set splits into an ELM half and a
disruption half; this works through the disruption half (Q14–Q27) against the
same index. Some questions are answerable now — which pipeline produced a label
and at what commit, which quantities are disruption precursors and in what
units, whether the two disruption indicators agree. Some are answerable for one
pipeline only, because GA's questions assume three and we have run one. And two
are answered correctly by refusing: a campaign disruption rate, which this slice
cannot support, and a question about discharge phase, where the column that
should answer it is constant for every row because of an upstream unit bug.

[Open the notebook](examples/jupyterhub/argus_feder_disruption_competency_jupyterhub.ipynb)

### Disruption precursors: what a 20-shot slice can and cannot show

A research pass over the same disruption index, at the level of questions that
decide whether a prediction study is worth building on this data: when precursors
become visible before the current quench, which signals actually discriminate
disrupted from non-disrupted shots, whether the locked mode is a multi-second
warning or a final-100 ms event, and what an alarm threshold would cost in false
alarms.

Several answers are negative, and the notebook reports them as such: no parameter
separates the two classes at p < 0.05 with ten shots per class, and the largest
AUCs belong to parameters that are statistically pure noise. It also separates the
apparent discriminators that are real physics from those that are artifacts of how
the disruption label is defined.

[Open the notebook](examples/jupyterhub/argus_feder_disruption_research_jupyterhub.ipynb)

## Plasma-facing materials

### Tungsten in the divertor: what the plasma did to it

Tungsten armours the DIII-D divertor and is the leading candidate for ITER. Helium
restructures its surface and deuterium implants into it, so whether the first
changes the second is a reactor safety question. Samples pre-exposed to helium in a
linear device, and others not, were mounted on DiMES through real DIII-D discharges
and analysed afterwards. The notebook works across the sample record and the
discharge archive together, joined by the shot numbers each exposure carries.

Several questions rebuild a recorded condition from the raw measurements behind it —
temperature at the sample, heat flux from the infrared exports, the camera's intra-
to inter-ELM brightness ratio from the archive's D-alpha filterscope — and two
reproduce the record only under a restriction that has to be found first. Where the
sample record and the ELM index disagree about a campaign's confinement regime, the
notebook settles it from the traces, and the closing question separates what the
record establishes from what it only suggests.

[Open the notebook](examples/jupyterhub/argus_feder_materials_d3d_jupyterhub.ipynb)

### Where the deuterium sits: a carbon film, or the tungsten?

Retained fuel is the number a reactor designer cares about, and the samples did not
come back as clean tungsten — DIII-D's walls carry carbon, and it deposits on
whatever is exposed. Deuterium held in a carbon film behaves nothing like deuterium
trapped in tungsten, so the same measured inventory means two different things
depending on where it sits. Five questions test whether the delivery can tell.

The answer is partly negative and the notebook says so: the deep band is settled as
tungsten-resident, the other three-quarters is pinned only to "above half a micron",
and the closing question works out the depth resolution a measurement would need to
close the gap — about a hundred times finer than anything in the delivery.

[Open the notebook](examples/jupyterhub/argus_feder_materials_carbon_jupyterhub.ipynb)

### Does a helium bubble layer change how tungsten survives a tokamak?

A burning plasma makes helium, so the tungsten facing one is tungsten with a bubble
layer already in it. Coupons pre-exposed to helium in a linear device were mounted on
DiMES beside coupons that were not, and all of them saw the same DIII-D discharges —
a design built to isolate what that layer does to erosion, morphology and fuel
retention. The notebook assembles the dataset and then tries to carry the comparison
out.

Two of its findings are structural rather than physical. The coupons that entered the
tokamak carry no imaging of their own, so the record of their initial surface runs
through a sibling implanted in the same run — a link in the experiment's design, not
in the sample table. And the helium-free controls do not come back helium-free, which
narrows the contrast the experiment was built around.

[Open the notebook](examples/jupyterhub/argus_feder_materials_helium_jupyterhub.ipynb)

## Running these notebooks

The notebooks assume the agent, TokSearch and the DIII-D skills are already
installed, as they are in the runtime image. Two credentials are supplied at
run time and are never stored in this repository:

- an API key for the LLM provider
- a DIII-D Pelican access token

Each notebook says how to supply both.

## Status

This repository is a periodic snapshot of work developed elsewhere, so it will
lag the development tree.
