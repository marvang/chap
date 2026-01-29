# Results Tables

Generated from 2 baseline runs and 2 CHAP runs.

## Table 1: Success Rate Comparison

| Method |Run 1 | Run 2 | Pass@2 |
|--------|--------|--------|--------|
| Baseline | 3/11 (27.3%) | 3/11 (27.3%) | 5/11 |
| CHAP | 4/11 (36.4%) | 4/11 (36.4%) | 5/11 |

### Challenges Solved (Pass@k union)

- **Pass@1**: Baseline: ['vm1', 'vm8', 'vm9'], CHAP: ['vm1', 'vm2', 'vm5', 'vm9']
- **Pass@2**: Baseline: ['vm1', 'vm2', 'vm5', 'vm8', 'vm9'], CHAP: ['vm1', 'vm2', 'vm5', 'vm6', 'vm9']

## Table 2: Cost Efficiency

| Method | Grand Total | Avg Cost/Challenge | Avg Cost (Success) | Avg Cost (Fail) |
|--------|-------------|-------------------|--------------------|-----------------|
| Baseline | $22.54 | $1.02 | $0.27 | $1.31 |
| CHAP | $15.08 | $0.69 | $0.37 | $0.86 |

## Table 3: Iteration Analysis

| Method | Avg Iter/Challenge | Avg Iter (Success) | Avg Iter (Fail) | Max Iter (Success) |
|--------|-------------------|-------------------|-----------------|--------------------|
| Baseline | 175.9 | 82.2 | 211.1 | 152 |
| CHAP | 177.0 | 101.6 | 220.0 | 182 |

## Table 4: CHAP Relay Analysis

| Metric | Value |
|--------|-------|
| Total Relays | 53 |
| Avg Relays/Challenge | 2.41 |
| Auto-Triggered | 38 (71.7%) |
| Manual-Triggered | 15 (28.3%) |
| Avg Relays (Solved Challenges) | 1.00 |
| Avg Relays (Unsolved Challenges) | 3.21 |

## Per-Run Details

### Baseline Runs

**Run 1** (new_baseline_gpt-5.1-codex-mini-arm_run1):
- Success: 3/11 (27.3%)
- Solved: ['vm1', 'vm8', 'vm9']
- Total Cost: $12.77
- Total Iterations: 2019

**Run 2** (new_baseline_gpt-5.1-codex-mini-arm_run2):
- Success: 3/11 (27.3%)
- Solved: ['vm1', 'vm2', 'vm5']
- Total Cost: $9.77
- Total Iterations: 1851

### CHAP Runs

**Run 1** (new_chap_auto_trigger_gpt-5.1-codex-mini-arm_run1):
- Success: 4/11 (36.4%)
- Solved: ['vm1', 'vm2', 'vm5', 'vm9']
- Total Cost: $8.37
- Total Iterations: 2010

**Run 2** (new_chap_auto_trigger_gpt-5.1-codex-mini-arm_run2):
- Success: 4/11 (36.4%)
- Solved: ['vm1', 'vm2', 'vm5', 'vm6']
- Total Cost: $6.71
- Total Iterations: 1883

