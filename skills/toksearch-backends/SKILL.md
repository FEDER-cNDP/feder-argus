---
name: toksearch-backends
description: Computing backends in TokSearch - Serial, Multiprocessing, Ray, and Spark execution
license: Apache-2.0
compatibility: Designed for deepagents CLI
metadata:
  author: GA-FDP
  version: "1.0"
  url: https://ga-fdp.github.io/toksearch/
---

# TokSearch Backends Skill

## Note on Data Access

In this environment, Pelican is the only working data access method. Scripts must be executed using the fdp wrapper. Before writing any data fetching code, read the `d3d-shot-fetcher` skill first.

## Description
TokSearch supports multiple execution backends for parallel data processing across fusion experimental shots. This skill covers the available backends and when to use each one.

## When to Use
- **Serial**: Development, debugging, small datasets (< 100 shots)
- **Multiprocessing**: Local parallel processing, medium datasets (100-1000 shots)
- **Ray**: Distributed computing, large datasets, need to scale beyond single machine
- **Spark**: Very large datasets, existing Spark infrastructure, cluster computing

## Backend Overview

| Backend | Use Case | Scaling | Setup Required |
|---------|----------|---------|----------------|
| `compute_serial()` | Development, testing | 1 core | None |
| `compute_multiprocessing()` | Local parallel | All CPU cores | None |
| `compute_ray()` | Distributed computing | Cluster/Cloud | Ray installation |
| `compute_spark()` | Big data | Spark cluster | Spark installation |

## Serial Backend (Default)

**Best for:** Development, debugging, small datasets

```python
from toksearch import Pipeline

pipeline = Pipeline([1701, 1702, 1703])

# ... add operations ...

# Execute serially (one shot at a time)
results = pipeline.compute_serial()
```

**Advantages:**
- Easy to debug (stack traces are clear)
- No setup required
- Predictable execution order
- Best for development

**Disadvantages:**
- Slow for large datasets
- Single-core execution only

## Multiprocessing Backend

**Best for:** Local parallel processing, medium datasets

```python
from toksearch import Pipeline
from toksearch.backend.multiprocessing import MultiprocessingConfig

pipeline = Pipeline(list(range(1701, 1800)))

# ... add operations ...

# Configure and execute
config = MultiprocessingConfig(num_workers=4)
results = pipeline.compute_multiprocessing(config=config)
```

**Configuration Options:**
```python
config = MultiprocessingConfig(
    num_workers=4,          # Number of parallel processes (default: CPU count)
    chunk_size=10,          # Shots per chunk (default: auto)
)
```

**Advantages:**
- Uses all CPU cores
- No extra setup needed
- Good for 100-1000 shots
- Simple configuration

**Disadvantages:**
- Single machine only
- Memory per process
- Not suitable for very large datasets

## Ray Backend

**Best for:** Distributed computing, scaling beyond one machine

```python
from toksearch import Pipeline
from toksearch.backend.ray import RayConfig

pipeline = Pipeline(list(range(1701, 10000)))

# ... add operations ...

# Configure and execute
config = RayConfig(
    num_cpus=4,
    num_workers=4,
    object_store_memory=500_000_000,  # 500MB
)
results = pipeline.compute_ray(config=config)
```

**Configuration Options:**
```python
config = RayConfig(
    num_cpus=4,                    # CPUs per worker
    num_workers=4,                 # Number of workers
    object_store_memory=500_000_000,  # Object store memory in bytes
    runtime_env={"PIP": ["some-package"]},  # Python packages for workers
)
```

**Advantages:**
- Scales to clusters
- Fault tolerance
- Efficient task scheduling
- Handles very large datasets

**Disadvantages:**
- Requires Ray installation
- More complex setup
- Overhead for small datasets

## Spark Backend

**Best for:** Very large datasets, existing Spark infrastructure

```python
from toksearch import Pipeline
from toksearch.backend.spark import ToksearchSparkConfig

pipeline = Pipeline(list(range(1701, 50000)))

# ... add operations ...

# Configure and execute
config = ToksearchSparkConfig(
    app_name="TokSearch Analysis",
    master="local[*]",  # or "spark://hostname:7077" for cluster
    executor_memory="2g",
    driver_memory="1g",
)
results = pipeline.compute_spark(config=config)
```

**Configuration Options:**
```python
config = ToksearchSparkConfig(
    app_name="My Analysis",
    master="local[*]",              # Deployment mode
    executor_memory="2g",           # Memory per executor
    driver_memory="1g",             # Driver memory
    executor_cores=2,               # Cores per executor
    log_level="WARN",
    # Spark configuration
    spark_conf={
        "spark.sql.shuffle.partitions": "200",
    },
)
```

**Advantages:**
- Handles massive datasets
- Industry-standard for big data
- Excellent for ETL workflows
- Mature ecosystem

**Disadvantages:**
- Highest overhead
- Requires Java/Spark
- Overkill for small datasets
- Slower startup time

## Choosing the Right Backend

### Decision Tree

```
Start
  |
  v
Is dataset < 100 shots?
  YES -> Use compute_serial()
  NO  ->
     |
     v
  Do you have a Spark cluster?
    YES -> Use compute_spark()
    NO  ->
       |
       v
  Is dataset > 10,000 shots?
    YES -> Use compute_ray()
    NO  ->
       |
       v
  Use compute_multiprocessing()
```

### Quick Reference

| Shot Count | Recommended Backend |
|------------|---------------------|
| < 100 | Serial |
| 100 - 1,000 | Multiprocessing |
| 1,000 - 10,000 | Ray or Multiprocessing |
| > 10,000 | Ray or Spark |

## Performance Tips

### Start serial, then scale
```python
# 1. Develop and debug with serial
results = pipeline.compute_serial()

# 2. Test with multiprocessing
results = pipeline.compute_multiprocessing()

# 3. Scale to Ray for production
results = pipeline.compute_ray()
```

### Monitor resource usage
```python
# For multiprocessing
import os
config = MultiprocessingConfig(
    num_workers=max(1, os.cpu_count() - 2)  # Leave 2 cores free
)
```

### Tune chunk size
```python
# For Ray/Multiprocessing
# Larger chunks = less overhead but less parallelism
config = MultiprocessingConfig(
    num_workers=4,
    chunk_size=20,  # Process 20 shots per task
)
```

### Handle failures
```python
# All backends return results even if some shots fail.
# rec.errors is a dict {field: error}; there is no has_error()/get_errors().
for rec in results:
    if rec.errors:
        print(f"Shot {rec['shot']} failed: {dict(rec.errors)}")
```

## Common Patterns

### Development to Production Workflow

```python
from toksearch import Pipeline

pipeline = Pipeline(shots)

# ... define pipeline ...

# Development: fast feedback
if len(shots) < 100:
    results = pipeline.compute_serial()
else:
    # Production: parallel execution
    results = pipeline.compute_multiprocessing()
```

### Backend-specific Error Handling

```python
# Multiprocessing requires picklable functions
@pipeline.map
def my_transform(rec):  # Top-level function, not nested
    return rec['data'] * 2

# Avoid closures that can't be pickled
```

### Memory Management

```python
# For large datasets, use smaller chunks
config = RayConfig(
    num_workers=8,
    object_store_memory=200_000_000,  # 200MB per worker
)
```

## Complete Examples

### Example 1: Small dataset (Serial)
```python
from toksearch import Pipeline, MdsSignal

shots = [1701, 1702, 1703]
pipeline = Pipeline(shots)

pipeline.fetch('ip', MdsSignal(r'\ipmhd', 'efit01'))

@pipeline.where
def ip_gt_1ma(rec):
    return 'ip' not in rec.errors

results = pipeline.compute_serial()  # Simple, debuggable
```

### Example 2: Medium dataset (Multiprocessing)
```python
from toksearch import Pipeline, MdsSignal
from toksearch.backend.multiprocessing import MultiprocessingConfig

shots = list(range(1701, 2000))
pipeline = Pipeline(shots)

# ... define pipeline ...

config = MultiprocessingConfig(num_workers=8)
results = pipeline.compute_multiprocessing(config=config)
```

### Example 3: Large dataset (Ray)
```python
from toksearch import Pipeline, MdsSignal
from toksearch.backend.ray import RayConfig

shots = list(range(1701, 20000))
pipeline = Pipeline(shots)

# ... define pipeline ...

config = RayConfig(num_workers=16)
results = pipeline.compute_ray(config=config)
```

## Best Practices
- Always test with `compute_serial()` first
- Use the simplest backend that meets your needs
- Consider memory requirements when choosing backend
- Monitor and tune based on actual performance
- Profile your pipeline before scaling

## Notes
- All backends return the same `RecordSet` type of results
- Backend selection doesn't change pipeline definition
- Switching backends is just changing the `compute_*()` call
- Error handling is consistent across all backends
