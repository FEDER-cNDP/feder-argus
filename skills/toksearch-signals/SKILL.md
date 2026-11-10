---
name: toksearch-signals
description: Signal classes in TokSearch - MDSplus and Zarr data sources for fusion experimental data
license: Apache-2.0
compatibility: Designed for deepagents CLI
metadata:
  author: GA-FDP
  version: "1.0"
  url: https://ga-fdp.github.io/toksearch/
---

# TokSearch Signals Skill

## Note on Data Access

In this environment, Pelican is the only working data access method. Scripts must be executed using the fdp wrapper. Before writing any data fetching code, read the `d3d-shot-fetcher` skill first.

## Description
Signals are data sources in TokSearch that provide access to fusion experimental data from various storage systems. This skill covers MDSplus (`MdsSignal`) and Zarr (`ZarrSignal`) signal types.

## When to Use
- When fetching data from MDSplus trees (primary data source for DIII-D)
- When accessing data stored in Zarr format
- When working with time series signals from fusion experiments
- When retrieving electron temperature, density, magnetic field, and other plasma parameters

## CRITICAL WARNINGS - READ BEFORE USING SIGNALS

### WARNING 1: Signal Expressions

**DO NOT use signal names that don't exist in the tree!**

Common mistakes that WILL FAIL:
- `MdsSignal(r'\ipmeas', 'magnetics')` - WRONG! There is NO `\ipmeas` in magnetics tree
- `MdsSignal(r'\efit::ipmhd', ...)` - WRONG! Do NOT use `\tree::signal` syntax

Correct usage:
- `MdsSignal(r'\ip', 'magnetics')` - CORRECT
- `MdsSignal(r'\ipmhd', 'efit01')` - CORRECT

**Always check the signal expression table below for the correct signal names!**

### WARNING 2: Data Access Pattern

**Signals return DICTIONARIES, not raw arrays!**

This WILL FAIL:
```python
value = rec['signal'].max()  # ERROR: dict has no 'max' attribute
```

This is CORRECT:
```python
signal_data = rec['signal']
data = signal_data['data']     # Extract array from dict
value = np.max(data)           # Then use numpy functions
```

### MANDATORY CODE PATTERN - FOLLOW THIS EXACTLY

When processing signals fetched with MdsSignal, you MUST use this pattern:

```python
@pipeline.map
def process_signal(rec):
    # Step 1: Get the signal dictionary
    signal_data = rec['signal_name']

    # Step 2: Extract the data array from the dictionary
    data = signal_data['data']

    # Step 3: NOW you can use numpy functions
    max_value = np.max(data)
    mean_value = np.mean(data)
    std_value = np.std(data)

    # Step 4: Store the result
    rec['max_value'] = max_value
```

**DO NOT skip Step 2!** You CANNOT call numpy functions directly on `rec['signal_name']`.

### WRONG vs CORRECT Examples

WRONG - This will crash:
```python
@pipeline.map
def process(rec):
    data = rec['ipmhd']          # WRONG! This is a dict
    value = np.mean(data)        # CRASHES! TypeError
```

CORRECT - This works:
```python
@pipeline.map
def process(rec):
    signal_data = rec['ipmhd']   # Get the dict
    data = signal_data['data']   # Extract the array
    value = np.mean(data)        # Works!
```

## Signal Classes

### Which package a signal class comes from

Not every signal class lives in `toksearch`. The DIII-D-specific ones are in a
separate package, `toksearch_d3d`, and importing them from `toksearch` raises
`ImportError` (verified 2026-08-02 -- this cost an agent six tool calls to
rediscover live, because it assumed `PtDataSignal` sat next to `MdsSignal`).

```python
# toksearch -- generic, device-neutral
from toksearch import Pipeline, MdsSignal, ZarrSignal, Signal, MdsTreePath

# toksearch_d3d -- DIII-D specific
from toksearch_d3d import PtDataSignal   # PTDATA raw digitizer traces
```

For a complete, verified script that fetches an MDSplus signal and a PTDATA
signal side by side, see the canonical example in the `d3d-shot-fetcher` skill
("Start from this script"). PTDATA additionally requires the `fdp run`
subprocess pattern -- it cannot be fetched in-kernel.

### MdsSignal (MDSplus Data)
MDSplus is the primary data storage system for DIII-D and many tokamaks.

```python
from toksearch import MdsSignal

# CORRECT: MdsSignal takes expression and treename as separate arguments
signal = MdsSignal(r'\signal_name', 'treename')

# Examples
signal = MdsSignal(r'\ip', 'magnetics')      # Plasma current from magnetics tree
signal = MdsSignal(r'\ipmhd', 'efit01')      # Plasma current from EFIT tree
signal = MdsSignal(r'\t_e', 'efit01')        # Electron temperature from EFIT
```

**IMPORTANT API Notes:**
- `MdsSignal(expression, treename)` - expression and treename are SEPARATE arguments
- Do NOT use the `\tree::signal` combined syntax
- Do NOT pass `shot` parameter - Pipeline handles this automatically
- Use raw strings `r'...'` for backslashes

**Common DIII-D Trees:**
- `magnetics` - Magnetic diagnostics
- `efit01` or `efit` - EFIT equilibrium reconstruction
- `pcs` - Plasma Control System
- `ece` - Electron Cyclotron Emission
- `thomson` - Thomson scattering

### ZarrSignal (Zarr Storage)
Zarr is a cloud-optimized storage format for array data.

```python
from toksearch import ZarrSignal

# Zarr signal
signal = ZarrSignal('path/to/zarr/store')
```

## Using Signals with Pipeline

### Method 1: Decorator-style (Recommended)

```python
from toksearch import Pipeline, MdsSignal

pipeline = Pipeline([1701, 1702, 1703])

pipeline.fetch('electron_temp', MdsSignal(r'\t_e', 'efit01'))
```

### Method 2: Direct method call

```python
# Direct call - both work
pipeline.fetch('electron_temp', MdsSignal(r'\t_e', 'efit01'))

# Or with variable
signal = MdsSignal(r'\t_e', 'efit01')
pipeline.fetch('electron_temp', signal)
```

## Common DIII-D MDSplus Signals

| Expression | Tree | Description |
|------------|------|-------------|
| `\t_e` | efit01 | Electron temperature profile |
| `\ne` | efit01 | Electron density profile |
| `\ipmhd` | efit01 | Plasma current |
| `\betap` | efit01 | Poloidal beta |
| `\qmin` | efit01 | Minimum safety factor |
| `\ne` | pcs | Line-averaged electron density |
| `\ts_ip` | pcs | Plasma current from PCS |
| `\ip` | magnetics | Plasma current from magnetics |

**IMPORTANT:** Note the magnetics tree uses `\ip`, NOT `\ipmeas`. This is a common mistake.

## Signal Data Format

**CRITICAL:** Signals return **dictionaries**, NOT raw arrays. Do NOT call methods like `.max()` directly on signal data.

```python
@pipeline.map
def process_signal(rec):
    if 'electron_temp' in rec:
        # WRONG! This will fail:
        # value = rec['electron_temp'].max()  # ERROR: dict has no 'max' method

        # CORRECT: Access the 'data' key first
        signal_data = rec['electron_temp']
        data = signal_data['data']           # The actual data array
        times = signal_data['times']         # The time base array
        units = signal_data['units']         # Dict of units

        # Now you can use numpy functions on the data array
        max_value = np.max(data)
        min_value = np.min(data)
        mean_value = np.mean(data)

        print(f"Data points: {len(data)}")
        print(f"Max value: {max_value} {units['data']}")
```

**Signal data structure:**
```python
{
    'data': numpy_array,      # The actual data values
    'times': numpy_array,     # Time base (or other dimensions)
    'units': {                # Units for data and dimensions
        'data': 'A',           # e.g., "A" for Amps, "eV" for temperature
        'times': 's'           # e.g., "s" for seconds, "ms" for milliseconds
    }
}
```

**IMPORTANT: Check units!** Data may be in different units than expected:
- Plasma current often in "A" (Amps), convert to MA by dividing by 1e6
- Time may be in "ms" (milliseconds) or "s" (seconds)
- Temperature may be in "eV", "keV", or other units

---

## WARNING: Mock Data vs Real Signals

**THIS IS A CRITICAL DISTINCTION THAT WILL CAUSE YOUR CODE TO FAIL IF IGNORED:**

### Mock Data (ONLY for testing without MDSplus)

When you create mock data for testing, you add raw numpy arrays directly:

```python
# MOCK DATA - Raw numpy arrays (for testing only)
@pipeline.map
def add_mock_data(rec):
    rec['ipmhd'] = np.array([1.0, 1.1, 1.2, 1.3])  # RAW ARRAY

# This WORKS with mock data:
value = rec['ipmhd'].max()  # OK for mock (raw numpy array)
```

### Real MDSplus Signals (ACTUAL data from tokamak)

When you fetch REAL signals from MDSplus, they return **DICTIONARIES**:

```python
# REAL SIGNAL - Returns dict, NOT raw array
pipeline.fetch('ipmhd', MdsSignal(r'\ipmhd', 'efit01'))

# This FAILS with real signals:
value = rec['ipmhd'].max()  # ERROR! 'dict' object has no attribute 'max'

# This WORKS with real signals:
signal_data = rec['ipmhd']
data = signal_data['data']    # Extract the numpy array from dict
value = np.max(data)          # CORRECT
```

### NEVER Mix These Patterns!

| Pattern | Mock Data | Real Signals |
|---------|-----------|-------------|
| `rec['signal'].max()` | WORKS | **FAILS** |
| `rec['signal']['data'].max()` | Fails | **WORKS** |
| `np.max(rec['signal']['data'])` | Fails | **WORKS** |

**IF YOUR CODE USES MOCK DATA PATTERNS, IT WILL NOT WORK WITH REAL MDSplus SIGNALS!**

Always write code for REAL signals first. Add mock data separately for testing if needed.

---

## Fetching Multiple Signals

```python
from toksearch import Pipeline, MdsSignal

pipeline = Pipeline([1701, 1702, 1703])

# Fetch multiple signals
pipeline.fetch('ip', MdsSignal(r'\ipmhd', 'efit01'))

pipeline.fetch('te', MdsSignal(r'\t_e', 'efit01'))

pipeline.fetch('ne', MdsSignal(r'\ne', 'efit01'))

results = pipeline.compute_serial()
```

## Signal Options

### MDSSignal with default values
```python
# Provide default if signal not found
signal = MdsSignal(r'\signal', 'treename')
```

### Time-based slicing
```python
# Some signals support time range queries
signal = MdsSignal(r'\signal', 'treename',
                   time_start=1.0, time_end=3.0)
```

## Error Handling

### Check for signal errors
```python
@pipeline.map
def safe_processing(rec):
    # Check if signal was fetched successfully.
    # rec.errors is a dict {field: error}; there is NO rec.has_error() method.
    if 'my_signal' in rec.errors:
        print(f"Shot {rec['shot']}: Error fetching my_signal")
        rec['status'] = 'error'
        return

    # Process signal if no error
    if 'my_signal' in rec and rec['my_signal'] is not None:
        rec['processed'] = rec['my_signal'] * 2
```

### Validate signal data
```python
@pipeline.map
def validate_signal(rec):
    if 'my_signal' in rec:
        data = rec['my_signal']

        # Check for empty data
        if data is None or len(data) == 0:
            rec['signal_status'] = 'empty'
            return

        # Check for NaN values
        import numpy as np
        if np.any(np.isnan(data)):
            rec['signal_status'] = 'has_nan'
        else:
            rec['signal_status'] = 'valid'
```

## Working with Time Series

### Extract time and data separately
```python
@pipeline.map
def extract_time_data(rec):
    if 'electron_temp' in rec:
        signal_data = rec['electron_temp']
        times = signal_data['times']
        temp_data = signal_data['data']
        rec['time_array'] = times
        rec['temp_data'] = temp_data
        rec['temp_at_peak'] = np.max(temp_data)
        rec['time_at_peak'] = times[np.argmax(temp_data)]
```

### Time-based filtering
```python
@pipeline.map
def filter_time_window(rec):
    if 'electron_temp' in rec:
        signal_data = rec['electron_temp']
        times = signal_data['times']
        data = signal_data['data']

        # Get data in time window [1.0, 2.0] seconds
        mask = (times >= 1.0) & (times <= 2.0)
        rec['window_times'] = times[mask]
        rec['window_data'] = data[mask]
```

## Common Mistakes to AVOID

### Mistake 1: Calling numpy functions directly on signal

WRONG:
```python
@pipeline.map
def process(rec):
    rec['max'] = np.max(rec['ipmhd'])    # CRASHES!
```

CORRECT:
```python
@pipeline.map
def process(rec):
    signal_data = rec['ipmhd']
    data = signal_data['data']
    rec['max'] = np.max(data)             # Works!
```

### Mistake 2: Assigning signal to variable and using it directly

WRONG:
```python
@pipeline.map
def process(rec):
    ip_data = rec['ipmhd']              # This is a DICT!
    mean = np.mean(ip_data)             # CRASHES!
    std = np.std(ip_data)               # CRASHES!
```

CORRECT:
```python
@pipeline.map
def process(rec):
    signal_data = rec['ipmhd']           # Get the dict
    data = signal_data['data']           # Extract the array
    mean = np.mean(data)                 # Works!
    std = np.std(data)                   # Works!
```

### Mistake 3: Forgetting to access the 'data' key

WRONG:
```python
data = rec['signal']                    # This is a DICT
value = data.max()                      # CRASHES!
```

CORRECT:
```python
signal_data = rec['signal']             # Get the dict
data = signal_data['data']              # Extract the array
value = np.max(data)                    # Works!
```

---

## REMEMBER: Signal Data Access Pattern

Before using any example below, remember this MANDATORY pattern:

```python
# WRONG - Do NOT do this:
value = np.mean(rec['signal_name'])    # FAILS!

# CORRECT - Always do this:
signal_data = rec['signal_name']       # Get dict
data = signal_data['data']              # Extract array
value = np.mean(data)                   # Then use numpy
```

---

## Complete Example: Multi-Signal Analysis

```python
from toksearch import Pipeline, MdsSignal
import numpy as np

# Define shots of interest
shots = [1701, 1702, 1703, 1704, 1705]
pipeline = Pipeline(shots)

# Fetch plasma current
pipeline.fetch('ip', MdsSignal(r'\ipmhd', 'efit01'))

# Fetch electron temperature
pipeline.fetch('te', MdsSignal(r'\t_e', 'efit01'))

# Fetch electron density
pipeline.fetch('ne', MdsSignal(r'\ne', 'efit01'))

# Calculate derived parameters
@pipeline.map
def calculate_derived(rec):
    if 'ip' in rec and 'ne' in rec:
        rec['greenwald_fraction'] = rec['ne'] / (rec['ip'] / np.pi)

# Filter for valid data (rec.errors is a dict of failed fields)
@pipeline.where
def has_valid_data(rec):
    return not ({'ip', 'te', 'ne'} & set(rec.errors))

# Compute results
results = pipeline.compute_serial()

# Output summary
for rec in results:
    print(f"Shot {rec['shot']}: Ip={rec.get('ip', 'N/A')} MA, "
          f"Te={rec.get('te', 'N/A')} keV, "
          f"ne={rec.get('ne', 'N/A')} 10^20 m^-3")
```

## ZarrSignal Usage

### Basic Zarr access
```python
from toksearch import ZarrSignal

# Local Zarr store
signal = ZarrSignal('/path/to/data.zarr')

# With path within store
signal = ZarrSignal('/path/to/data.zarr/group/array')

# Fetch with pipeline
pipeline.fetch('zarr_data', ZarrSignal('/path/to/data.zarr'))
```

### Zarr with S3/cloud storage
```python
import fsspec

# S3-backed Zarr
signal = ZarrSignal('s3://bucket/path/to/data.zarr',
                   storage_options={'anon': True})
```

## Best Practices
- Call `pipeline.fetch(name, signal)` directly -- it is a method, not a
  decorator, and returns `None`, so `@pipeline.fetch(...)` raises
  `TypeError: 'NoneType' object is not callable`. `map` and `where` DO
  work as decorators.
- Check for errors with `rec.errors` (a dict of failed fields); there is no `has_error()` method
- Validate signal data before processing
- Use descriptive signal names (e.g., 'electron_temp' not 'te')
- Consider time windows when dealing with long-pulse discharges

## Notes
- MDSplus signals require active MDSplus server connection
- Signal paths are case-sensitive
- Not all signals are available for all shots
- Use `test_toksearch.py` to verify your setup before running complex queries
