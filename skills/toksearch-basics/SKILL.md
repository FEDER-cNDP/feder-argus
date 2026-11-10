---
name: toksearch-basics
description: Basic TokSearch API usage - Pipeline, Record, and core data processing concepts for fusion experimental data
license: Apache-2.0
compatibility: Designed for deepagents CLI
metadata:
  author: GA-FDP
  version: "1.0"
  url: https://ga-fdp.github.io/toksearch/
---

# TokSearch Basics Skill

## Note on Data Access

In this environment, Pelican is the only working data access method. Scripts must be executed using the fdp wrapper. Before writing any data fetching code, read the `d3d-shot-fetcher` skill first.

## Description
TokSearch is a Python package for parallel retrieving, processing, and filtering of arbitrary-dimension fusion experimental data from tokamak experiments (primarily DIII-D). This skill covers the core API: Pipeline, Record, and basic data processing operations.

## When to Use
- When the user needs to analyze fusion experimental data from tokamaks
- When working with shot-based data processing workflows
- When fetching, filtering, and transforming experimental signals
- When performing parallel data analysis across multiple shots

## Core Concepts

### Pipeline
The `Pipeline` class is the main interface for data processing workflows. It processes `Record` objects (each representing data from a single experimental "shot").

```python
from toksearch import Pipeline

# Create a pipeline for a list of shot numbers
shots = [1701, 1702, 1703, 1704, 1705]
pipeline = Pipeline(shots)
```

### Record
Records are dict-like objects that hold data for a single shot. Each record has a 'shot' field and can contain multiple signals with their data.

```python
# Access data in a record (within map/where functions)
data = rec['signal_name']

# Get shot number (attribute access)
shot_number = rec.shot

# Check for errors
if 'signal_name' in rec.errors:
    # Handle error
    pass

# Get value with default (IMPORTANT: get() requires BOTH key and default)
value = rec.get('signal_name', None)
```

## Pipeline Methods

### fetch(signal_name, signal)
Fetch data from a signal source and add it to each record.

```python
from toksearch import MdsSignal

pipeline.fetch('electron_temperature', MdsSignal(r'\t_e', 'efit01'))
```

**`fetch` is a plain method call, NOT a decorator.** It returns `None`, so
`@pipeline.fetch(...)` above a stub function raises
`TypeError: 'NoneType' object is not callable`. `map` and `where` below ARE
used as decorators; `fetch` is the exception, because it takes arguments of its
own.

### map(func)
Apply a function to each record, modifying it in place.

```python
@pipeline.map
def add_calculated_field(rec):
    rec['t_e_squared'] = rec['electron_temperature'] ** 2
```

### where(func)
Filter records based on a boolean condition.

```python
@pipeline.where
def has_valid_data(rec):
    return rec.get('electron_temperature', None) is not None and len(rec['electron_temperature']) > 0
```

**An exception inside `where` is not raised -- the record is silently dropped.**
Nothing propagates to the caller and nothing lands in `rec.errors`; `compute_*`
simply returns fewer records, or none. An empty result from a pipeline that
fetched successfully means the filter is throwing, not that the data is missing.

The most common cause is `Record.get`, which -- unlike `dict.get` -- **requires
the default argument**: `rec.get('ip')` raises
`TypeError: missing 1 required positional argument: 'default'`, so a filter
written the dict way discards every record. Any of these work:

```python
rec.get('ip', None) is not None     # explicit default
'ip' in rec                         # membership
not rec.errors                      # nothing failed to fetch
```

When a pipeline returns zero records unexpectedly, drop the `where` and re-run
to see whether the records were there all along.

### keep(fields)
Keep only these fields in each record. IMPORTANT: Takes a LIST of field names.
There is no `discard()` on `Pipeline` -- select what to keep instead.

```python
pipeline.keep(['shot', 'electron_temperature', 'ip'])
```

### compute()
Execute the pipeline and return results.

```python
records = pipeline.compute()
```

## Complete Example

```python
from toksearch import Pipeline, MdsSignal

# Create pipeline with shot numbers
shots = list(range(1701, 1710))
pipeline = Pipeline(shots)

# Add data fetching
pipeline.fetch('ip', MdsSignal(r'\ipmhd', 'efit01'))

# Add a transformation
@pipeline.map
def normalize_ip(rec):
    if 'ip' in rec and rec['ip'] is not None:
        signal_data = rec['ip']
        data = signal_data['data']
        times = signal_data['times']
        rec['ip_ma'] = float(np.max(data)) / 1e6  # raw \ipmhd is in A; /1e6 -> MA

# Add filtering
@pipeline.where
def ip_threshold(rec):
    return rec.get('ip_ma', 0) > 0.5

# Execute
results = pipeline.compute_serial()

# Access results
for rec in results:
    print(f"Shot {rec['shot']}: Ip = {rec.get('ip_ma', 0):.2f} MA")
```

## Computing Backends

TokSearch supports multiple execution backends:

```python
# Serial execution (default, for local testing)
results = pipeline.compute_serial()

# Multiprocessing (local parallel)
results = pipeline.compute_multiprocessing()

# Ray (distributed computing)
results = pipeline.compute_ray()

# Spark (large-scale distributed)
results = pipeline.compute_spark()
```

## Data Access Patterns

### Check if data exists before using
```python
@pipeline.map
def safe_processing(rec):
    if 'signal_name' in rec and rec['signal_name'] is not None:
        # Process the data
        rec['processed'] = rec['signal_name'] * 2
    else:
        rec['error'] = 'Signal not available'
```

### Handle errors gracefully
```python
@pipeline.map
def robust_processing(rec):
    try:
        rec['result'] = complex_calculation(rec['data'])
    except Exception as e:
        rec['calculation_error'] = str(e)
```

### Work with time series data
```python
@pipeline.map
def time_stats(rec):
    if 'timeseries' in rec:
        import numpy as np
        data = rec['timeseries']
        rec['mean'] = np.mean(data)
        rec['std'] = np.std(data)
        rec['max'] = np.max(data)
        rec['min'] = np.min(data)
```

## Shot Number Format
Shot numbers are integers representing specific experimental discharges:
- DIII-D shots: typically 4-5 digit numbers (e.g., 1701, 17453, 183504)
- Used as unique identifiers for each experiment

## Common Workflow Pattern

```python
from toksearch import Pipeline, MdsSignal

# 1. Define shots
shots = [1701, 1702, 1703, ...]

# 2. Create pipeline
pipeline = Pipeline(shots)

# 3. Fetch data (expression + tree are SEPARATE args; do NOT pass shot)
pipeline.fetch('ip', MdsSignal(r'\ipmhd', 'efit01'))

# 4. Transform data
@pipeline.map
def transform(rec):
    rec['new_field'] = process(rec['signal1'])

# 5. Filter results
@pipeline.where
def filter(rec):
    return condition(rec)

# 6. Compute
results = pipeline.compute_serial()
```

## Best Practices
- Always check if data exists before accessing it
- Use descriptive signal names
- Handle errors gracefully with try/except blocks
- Test with small shot ranges first before scaling up
- Use `compute_serial()` for development, switch to parallel backends for production

## Notes
- Shot numbers are specific to each tokamak device (DIII-D shots are 5-6 digits, e.g. 165340)
- `MdsSignal` takes expression and tree as SEPARATE args, e.g. `MdsSignal(r'\ipmhd', 'efit01')` — NOT the `\tree::signal` combined syntax, and never a `shot=` argument
- Records accumulate all operations in the pipeline
- Failed signal fetches are tracked in `rec.errors` (a dict of {field: error})
