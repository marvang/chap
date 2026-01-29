#!/usr/bin/env python3
"""
Overnight Experiment Runner
===========================
Reads experiments from YAML config and runs them sequentially.
Each experiment runs ALL challenges defined in run_experiment.py.

Usage:
    python ctf-experiment-runner/run_overnight.py
    
With caffeinate (keeps Mac awake):
    caffeinate -dims python ctf-experiment-runner/run_overnight.py

Or use the shell script:
    ./ctf-experiment-runner/run_overnight.sh
"""

import os
import sys
import subprocess
import time
from datetime import datetime

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(SCRIPT_DIR, "configs", "overnight_experiments.yaml")
RUN_EXPERIMENT_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "run_experiment.py")

# Try to import yaml, install if missing
try:
    import yaml
except ImportError:
    print("📦 Installing PyYAML...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml


def load_config():
    """Load experiments from YAML config."""
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def build_command(experiment: dict, run_number: int) -> tuple:
    """Build command line args for run_experiment.py."""
    # Add run number to name for uniqueness
    base_name = experiment["name"]
    full_name = f"{base_name}_run{run_number}"
    
    cmd = [sys.executable, RUN_EXPERIMENT_SCRIPT, "--name", full_name]
    
    # CHAP toggle
    if experiment.get("chap_enabled", True):
        cmd.append("--chap")
    else:
        cmd.append("--no-chap")
    
    # Optional overrides - names match run_experiment.py constants
    if "chap_token_limit_base" in experiment:
        cmd.extend(["--token-base", str(experiment["chap_token_limit_base"])])
    
    if "model_name" in experiment:
        cmd.extend(["--model", experiment["model_name"]])
    
    if "chap_token_limit_increment" in experiment:
        cmd.extend(["--token-increment", str(experiment["chap_token_limit_increment"])])
    
    # Auto-trigger toggle (only relevant when CHAP enabled)
    if "chap_auto_trigger" in experiment:
        if experiment["chap_auto_trigger"]:
            cmd.append("--auto-trigger")
        else:
            cmd.append("--no-auto-trigger")
    
    return cmd, full_name


def main():
    print("=" * 60)
    print("🌙 OVERNIGHT EXPERIMENT RUNNER")
    print("=" * 60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Config:  {CONFIG_PATH}")
    print("=" * 60)
    
    # Load config
    config = load_config()
    experiments = config.get("experiments", [])
    runs_per_config = config.get("runs_per_config", 1)
    
    if not experiments:
        print("❌ No experiments defined in config!")
        sys.exit(1)
    
    # Calculate total runs
    total_runs = len(experiments) * runs_per_config
    
    # Show what will run
    print(f"\n📋 {len(experiments)} experiment configs × {runs_per_config} runs = {total_runs} total runs\n")
    for exp in experiments:
        chap = "CHAP ON" if exp.get("chap_enabled", True) else "CHAP OFF"
        token = f", {exp.get('chap_token_limit_base', 'default')}tok" if exp.get("chap_enabled", True) else ""
        print(f"  • {exp['name']} ({chap}{token}) × {runs_per_config}")
    
    print("\n" + "-" * 60)
    print("Each run executes ALL challenges from run_experiment.py")
    print("Edit CTF_CHALLENGES in that file to change which VMs run.")
    print("-" * 60)
    
    # Confirm
    print("\n⏳ Starting in 5 seconds... (Press Ctrl+C to cancel)")
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        print("\n❌ Cancelled.")
        sys.exit(0)
    
    # Run experiments
    completed = 0
    failed = 0
    current = 0
    
    for run_num in range(1, runs_per_config + 1):
        for experiment in experiments:
            current += 1
            cmd, full_name = build_command(experiment, run_num)
            
            print("\n" + "=" * 60)
            print(f"🚀 RUN {current}/{total_runs}: {full_name}")
            print("=" * 60)
            print(f"Command: {' '.join(cmd)}\n")
            
            try:
                result = subprocess.run(cmd, cwd=PROJECT_ROOT)
                if result.returncode == 0:
                    completed += 1
                    print(f"\n✅ '{full_name}' completed!")
                else:
                    failed += 1
                    print(f"\n⚠️ '{full_name}' exited with code {result.returncode}")
            except KeyboardInterrupt:
                print(f"\n\n⚠️ Interrupted during '{full_name}'")
                print(f"Completed: {completed}/{total_runs}")
                sys.exit(1)
            except Exception as e:
                failed += 1
                print(f"\n❌ '{full_name}' failed: {e}")
    
    # Final summary
    print("\n" + "=" * 60)
    print("🏁 OVERNIGHT RUN COMPLETE")
    print("=" * 60)
    print(f"Completed: {completed}/{total_runs}")
    print(f"Failed:    {failed}/{total_runs}")
    print(f"Finished:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Results:   ./results/<experiment_name>/")
    print("=" * 60)


if __name__ == "__main__":
    main()
