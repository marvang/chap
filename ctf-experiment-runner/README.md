# CTF Overnight Experiment Runner

Run multiple CTF experiments overnight. Your Mac stays awake automatically.

## Usage

```bash
./ctf-experiment-runner/run_overnight.sh
```

Or without caffeinate: `python ctf-experiment-runner/run_overnight.py`

## Configuration

Edit `configs/overnight_experiments.yaml`:

```yaml
experiments:
  - name: "chap_enabled_50k_run1"
    chap_enabled: true
    token_base: 50000
```

| Option | Description |
|--------|-------------|
| `name` | Experiment name (results folder) |
| `chap_enabled` | Enable/disable CHAP |
| `token_base` | CHAP token threshold (when enabled) |

## Single Experiment

```bash
python scripts/run_experiment.py --chap --name "test" --token-base 50000
```

Run `python scripts/run_experiment.py --help` for all options.
