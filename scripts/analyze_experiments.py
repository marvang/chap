#!/usr/bin/env python3
"""
CTF Benchmark Analysis Script
Compares Baseline vs CHAP experiments, generates metrics, tables, and figures.

Usage:
    python scripts/analyze_experiments.py [--runs N] [--output-dir DIR]

Options:
    --runs N        Number of runs to include per method (default: all)
    --output-dir    Output directory (default: analysis_results)

Output:
    analysis_results/analysis_output.json   - Complete structured data
    analysis_results/paper_tables.md        - Markdown tables
    analysis_results/paper_tables.tex       - LaTeX tables (IEEE format)
    analysis_results/figures/               - PNG/PDF figures
"""

import json
import os
import glob
import argparse
from pathlib import Path
from collections import defaultdict
from statistics import mean as stats_mean

# Try to import numpy, fall back to pure python if not available
try:
    import numpy as np
    def safe_mean(lst):
        return float(np.mean(lst)) if lst else 0
    def safe_std(lst):
        return float(np.std(lst, ddof=1)) if len(lst) > 1 else 0.0
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    from statistics import stdev as stats_stdev
    def safe_mean(lst):
        return stats_mean(lst) if lst else 0
    def safe_std(lst):
        return stats_stdev(lst) if len(lst) > 1 else 0.0

# Try to import matplotlib, gracefully handle if not available
try:
    import matplotlib.pyplot as plt
    if NUMPY_AVAILABLE:
        MATPLOTLIB_AVAILABLE = True
    else:
        # matplotlib often needs numpy
        MATPLOTLIB_AVAILABLE = False
        print("Warning: numpy not available, skipping figure generation")
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available, skipping figure generation")


# ============== DATA LOADING ==============

def discover_experiments(results_dir="results"):
    """
    Auto-discover experiments by folder name.
    Returns {'baseline': [paths...], 'chap': [paths...]}
    """
    experiments = {'baseline': [], 'chap': []}

    if not os.path.exists(results_dir):
        print(f"Error: Results directory '{results_dir}' not found")
        return experiments

    for folder in sorted(os.listdir(results_dir)):
        folder_path = os.path.join(results_dir, folder)
        if not os.path.isdir(folder_path):
            continue

        # Find experiment_* subfolder
        exp_dirs = sorted(glob.glob(os.path.join(folder_path, "experiment_*")))
        if not exp_dirs:
            continue

        exp_path = exp_dirs[0]  # Take first (should be only one per run folder)

        # Check if experiment_summary.json exists
        if not os.path.exists(os.path.join(exp_path, "experiment_summary.json")):
            print(f"Warning: No experiment_summary.json in {exp_path}, skipping")
            continue

        if "baseline" in folder.lower():
            experiments['baseline'].append(exp_path)
        elif "chap" in folder.lower():
            experiments['chap'].append(exp_path)

    return experiments


def load_experiment(exp_path):
    """Load all data for one experiment."""
    data = {
        'path': exp_path,
        'name': os.path.basename(os.path.dirname(exp_path)),
        'metadata': {},
        'challenges': {}
    }

    # Load experiment_summary.json
    summary_path = os.path.join(exp_path, "experiment_summary.json")
    try:
        with open(summary_path) as f:
            data['metadata'] = json.load(f).get('metadata', {})
    except Exception as e:
        print(f"Error loading {summary_path}: {e}")
        return data

    # Load each challenge
    challenges = data['metadata'].get('ctf_challenges', [])
    for vm in challenges:
        vm_path = os.path.join(exp_path, vm)
        challenge_data = {'name': vm}

        # summary.json
        summary_file = os.path.join(vm_path, "summary.json")
        if os.path.exists(summary_file):
            try:
                with open(summary_file) as f:
                    challenge_data['summary'] = json.load(f)
            except Exception as e:
                print(f"Error loading {summary_file}: {e}")

        # session.json (for tokens and relay_triggers)
        session_file = os.path.join(vm_path, "session.json")
        if os.path.exists(session_file):
            try:
                with open(session_file) as f:
                    session = json.load(f)
                    challenge_data['tokens'] = session.get('metrics', {})
                    challenge_data['relay_triggers'] = session.get('relay_triggers', [])
            except Exception as e:
                print(f"Error loading {session_file}: {e}")

        data['challenges'][vm] = challenge_data

    return data


# ============== METRICS CALCULATION ==============

def calculate_success_metrics(experiment):
    """Calculate success rate for one experiment."""
    solved = []
    for vm, data in experiment['challenges'].items():
        if data.get('summary', {}).get('flag_valid', False):
            solved.append(vm)

    total = len(experiment['challenges'])
    return {
        'solved_vms': sorted(solved),
        'count': len(solved),
        'total': total,
        'rate': len(solved) / total if total else 0
    }


def calculate_pass_at_k(experiments, k):
    """Calculate pass@k - challenges solved at least once across k runs."""
    if not experiments:
        return {'k': k, 'challenges': [], 'count': 0, 'total': 11, 'rate': 0}

    actual_k = min(k, len(experiments))

    solved_union = set()
    for exp in experiments[:actual_k]:
        metrics = calculate_success_metrics(exp)
        solved_union.update(metrics['solved_vms'])

    total = len(experiments[0]['challenges']) if experiments else 11
    return {
        'k': actual_k,
        'challenges': sorted(list(solved_union)),
        'count': len(solved_union),
        'total': total,
        'rate': len(solved_union) / total if total else 0
    }


def calculate_cost_metrics(experiment):
    """Calculate cost metrics for one experiment."""
    total_cost = 0
    successful_cost = 0
    unsuccessful_cost = 0
    successful_count = 0
    unsuccessful_count = 0
    costs_by_vm = {}

    for vm, data in experiment['challenges'].items():
        cost = data.get('summary', {}).get('total_cost', 0) or 0
        total_cost += cost
        costs_by_vm[vm] = cost

        if data.get('summary', {}).get('flag_valid', False):
            successful_cost += cost
            successful_count += 1
        else:
            unsuccessful_cost += cost
            unsuccessful_count += 1

    num_challenges = len(experiment['challenges'])
    return {
        'total_cost': total_cost,
        'avg_per_challenge': total_cost / num_challenges if num_challenges else 0,
        'avg_per_successful': successful_cost / successful_count if successful_count else None,
        'avg_per_unsuccessful': unsuccessful_cost / unsuccessful_count if unsuccessful_count else None,
        'cost_per_flag': successful_cost / successful_count if successful_count else None,
        'successful_count': successful_count,
        'unsuccessful_count': unsuccessful_count,
        'successful_cost': successful_cost,
        'unsuccessful_cost': unsuccessful_cost,
        'costs_by_vm': costs_by_vm
    }


def calculate_token_metrics(experiment):
    """Calculate token metrics for one experiment."""
    totals = {'input': 0, 'output': 0, 'reasoning': 0, 'cached': 0, 'total': 0}
    successful_tokens = 0
    successful_count = 0
    tokens_by_vm = {}

    for vm, data in experiment['challenges'].items():
        tokens = data.get('tokens', {})
        input_tok = tokens.get('total_input_tokens', 0) or 0
        output_tok = tokens.get('total_output_tokens', 0) or 0
        reasoning_tok = tokens.get('total_reasoning_tokens', 0) or 0
        cached_tok = tokens.get('total_cached_tokens', 0) or 0

        totals['input'] += input_tok
        totals['output'] += output_tok
        totals['reasoning'] += reasoning_tok
        totals['cached'] += cached_tok

        vm_total = input_tok + output_tok
        totals['total'] += vm_total
        tokens_by_vm[vm] = vm_total

        if data.get('summary', {}).get('flag_valid', False):
            successful_tokens += vm_total
            successful_count += 1

    num_challenges = len(experiment['challenges'])
    return {
        'breakdown': totals,
        'avg_per_challenge': totals['total'] / num_challenges if num_challenges else 0,
        'tokens_per_flag': successful_tokens / successful_count if successful_count else None,
        'successful_tokens': successful_tokens,
        'tokens_by_vm': tokens_by_vm
    }


def calculate_iteration_metrics(experiment):
    """Calculate iteration metrics for one experiment."""
    total_iterations = 0
    successful_iterations = 0
    unsuccessful_iterations = 0
    successful_count = 0
    unsuccessful_count = 0
    max_successful_iteration = 0
    iterations_by_vm = {}

    for vm, data in experiment['challenges'].items():
        iterations = data.get('summary', {}).get('iterations', 0) or 0
        total_iterations += iterations
        iterations_by_vm[vm] = iterations

        if data.get('summary', {}).get('flag_valid', False):
            successful_iterations += iterations
            successful_count += 1
            # Track highest iteration where a flag was captured
            if iterations > max_successful_iteration:
                max_successful_iteration = iterations
        else:
            unsuccessful_iterations += iterations
            unsuccessful_count += 1

    num_challenges = len(experiment['challenges'])
    return {
        'total_iterations': total_iterations,
        'avg_per_challenge': total_iterations / num_challenges if num_challenges else 0,
        'avg_per_successful': successful_iterations / successful_count if successful_count else None,
        'avg_per_unsuccessful': unsuccessful_iterations / unsuccessful_count if unsuccessful_count else None,
        'iterations_per_flag': successful_iterations / successful_count if successful_count else None,
        'max_successful_iteration': max_successful_iteration if successful_count else None,
        'successful_count': successful_count,
        'unsuccessful_count': unsuccessful_count,
        'iterations_by_vm': iterations_by_vm
    }


def calculate_relay_metrics(experiments):
    """Calculate CHAP relay metrics across experiments."""
    if not experiments:
        return {
            'total_relays': 0,
            'avg_per_challenge': 0,
            'auto_triggers': 0,
            'manual_triggers': 0,
            'auto_percent': 0,
            'manual_percent': 0,
            'avg_relays_solved': 0,
            'avg_relays_unsolved': 0
        }

    total_relays = 0
    auto_triggers = 0
    manual_triggers = 0
    relays_solved = []
    relays_unsolved = []

    for exp in experiments:
        for vm, data in exp['challenges'].items():
            relay_count = data.get('summary', {}).get('relay_count', 0) or 0
            total_relays += relay_count

            # Count trigger types from relay_triggers list
            for trigger in data.get('relay_triggers', []):
                trigger_type = trigger.get('trigger_type', '')
                if trigger_type == 'auto':
                    auto_triggers += 1
                elif trigger_type == 'manual':
                    manual_triggers += 1

            # Track relays by success status
            if data.get('summary', {}).get('flag_valid', False):
                relays_solved.append(relay_count)
            else:
                relays_unsolved.append(relay_count)

    total_triggers = auto_triggers + manual_triggers
    total_challenges = sum(len(exp['challenges']) for exp in experiments)

    return {
        'total_relays': total_relays,
        'avg_per_challenge': total_relays / total_challenges if total_challenges else 0,
        'auto_triggers': auto_triggers,
        'manual_triggers': manual_triggers,
        'auto_percent': (auto_triggers / total_triggers * 100) if total_triggers else 0,
        'manual_percent': (manual_triggers / total_triggers * 100) if total_triggers else 0,
        'avg_relays_solved': safe_mean(relays_solved),
        'avg_relays_unsolved': safe_mean(relays_unsolved),
        'solved_count': len(relays_solved),
        'unsolved_count': len(relays_unsolved)
    }


# ============== TABLE GENERATION ==============

def generate_markdown_tables(baseline_analysis, chap_analysis):
    """Generate Markdown tables for paper."""
    md = "# Results Tables\n\n"
    md += f"Generated from {len(baseline_analysis['per_run'])} baseline runs and {len(chap_analysis['per_run'])} CHAP runs.\n\n"

    # Table 1: Success Rate
    md += "## Table 1: Success Rate Comparison\n\n"

    max_runs = max(len(baseline_analysis['per_run']), len(chap_analysis['per_run']), 1)
    
    # Build dynamic header with Pass@k columns only up to max_runs
    header = "| Method |" + " | ".join([f"Run {i+1}" for i in range(max_runs)])
    separator = "|--------|" + "|".join(["--------"] * max_runs)
    for k in range(2, max_runs + 1):
        header += f" | Pass@{k}"
        separator += "|--------"
    header += " |\n"
    separator += "|\n"
    md += header + separator

    # Baseline row
    baseline_runs = []
    for r in baseline_analysis['per_run']:
        baseline_runs.append(f"{r['success']['count']}/11 ({r['success']['rate']*100:.1f}%)")
    baseline_runs += ["-"] * (max_runs - len(baseline_runs))

    baseline_pass_cols = ""
    for k in range(2, max_runs + 1):
        pass_k = baseline_analysis['pass_at_k'].get(k, {})
        baseline_pass_cols += f" | {pass_k.get('count', '-')}/11"
    md += f"| Baseline | {' | '.join(baseline_runs)}{baseline_pass_cols} |\n"

    # CHAP row
    chap_runs = []
    for r in chap_analysis['per_run']:
        chap_runs.append(f"{r['success']['count']}/11 ({r['success']['rate']*100:.1f}%)")
    chap_runs += ["-"] * (max_runs - len(chap_runs))

    chap_pass_cols = ""
    for k in range(2, max_runs + 1):
        pass_k = chap_analysis['pass_at_k'].get(k, {})
        chap_pass_cols += f" | {pass_k.get('count', '-')}/11"
    md += f"| CHAP | {' | '.join(chap_runs)}{chap_pass_cols} |\n"

    md += "\n"

    # Solved challenges detail
    md += "### Challenges Solved (Pass@k union)\n\n"
    for k in range(1, max(len(baseline_analysis['per_run']), len(chap_analysis['per_run'])) + 1):
        b_pass = baseline_analysis['pass_at_k'].get(k, {})
        c_pass = chap_analysis['pass_at_k'].get(k, {})
        md += f"- **Pass@{k}**: Baseline: {b_pass.get('challenges', [])}, CHAP: {c_pass.get('challenges', [])}\n"
    md += "\n"

    # Table 2: Cost Efficiency (pooled across all challenges)
    md += "## Table 2: Cost Efficiency\n\n"
    md += "| Method | Grand Total | Avg Cost/Challenge | Avg Cost (Success) | Avg Cost (Fail) |\n"
    md += "|--------|-------------|-------------------|--------------------|-----------------|\n"

    b_cost = baseline_analysis['averages']['cost']
    c_cost = chap_analysis['averages']['cost']

    b_gt = f"${b_cost['grand_total']:.2f}" if b_cost.get('grand_total') else "N/A"
    c_gt = f"${c_cost['grand_total']:.2f}" if c_cost.get('grand_total') else "N/A"
    b_cpc = f"${b_cost['avg_per_challenge']:.2f}" if b_cost.get('avg_per_challenge') else "N/A"
    c_cpc = f"${c_cost['avg_per_challenge']:.2f}" if c_cost.get('avg_per_challenge') else "N/A"
    b_cps = f"${b_cost['avg_per_successful']:.2f}" if b_cost.get('avg_per_successful') else "N/A"
    c_cps = f"${c_cost['avg_per_successful']:.2f}" if c_cost.get('avg_per_successful') else "N/A"
    b_cpu = f"${b_cost['avg_per_unsuccessful']:.2f}" if b_cost.get('avg_per_unsuccessful') else "N/A"
    c_cpu = f"${c_cost['avg_per_unsuccessful']:.2f}" if c_cost.get('avg_per_unsuccessful') else "N/A"

    md += f"| Baseline | {b_gt} | {b_cpc} | {b_cps} | {b_cpu} |\n"
    md += f"| CHAP | {c_gt} | {c_cpc} | {c_cps} | {c_cpu} |\n"

    md += "\n"

    # Table 3: Iteration Analysis (pooled across all challenges)
    md += "## Table 3: Iteration Analysis\n\n"
    md += "| Method | Avg Iter/Challenge | Avg Iter (Success) | Avg Iter (Fail) | Max Iter (Success) |\n"
    md += "|--------|-------------------|-------------------|-----------------|--------------------|\n"

    b_iter = baseline_analysis['averages']['iterations']
    c_iter = chap_analysis['averages']['iterations']

    b_ipc = f"{b_iter['avg_per_challenge']:.1f}" if b_iter.get('avg_per_challenge') else "N/A"
    c_ipc = f"{c_iter['avg_per_challenge']:.1f}" if c_iter.get('avg_per_challenge') else "N/A"
    b_ips = f"{b_iter['avg_per_successful']:.1f}" if b_iter.get('avg_per_successful') else "N/A"
    c_ips = f"{c_iter['avg_per_successful']:.1f}" if c_iter.get('avg_per_successful') else "N/A"
    b_ipu = f"{b_iter['avg_per_unsuccessful']:.1f}" if b_iter.get('avg_per_unsuccessful') else "N/A"
    c_ipu = f"{c_iter['avg_per_unsuccessful']:.1f}" if c_iter.get('avg_per_unsuccessful') else "N/A"
    b_max = f"{b_iter['max_successful_iteration']}" if b_iter.get('max_successful_iteration') else "N/A"
    c_max = f"{c_iter['max_successful_iteration']}" if c_iter.get('max_successful_iteration') else "N/A"

    md += f"| Baseline | {b_ipc} | {b_ips} | {b_ipu} | {b_max} |\n"
    md += f"| CHAP | {c_ipc} | {c_ips} | {c_ipu} | {c_max} |\n"

    md += "\n"

    # Table 4: CHAP Relay Analysis
    md += "## Table 4: CHAP Relay Analysis\n\n"
    md += "| Metric | Value |\n"
    md += "|--------|-------|\n"

    relay = chap_analysis.get('relay_metrics', {})
    md += f"| Total Relays | {relay.get('total_relays', 0)} |\n"
    md += f"| Avg Relays/Challenge | {relay.get('avg_per_challenge', 0):.2f} |\n"
    md += f"| Auto-Triggered | {relay.get('auto_triggers', 0)} ({relay.get('auto_percent', 0):.1f}%) |\n"
    md += f"| Manual-Triggered | {relay.get('manual_triggers', 0)} ({relay.get('manual_percent', 0):.1f}%) |\n"
    md += f"| Avg Relays (Solved Challenges) | {relay.get('avg_relays_solved', 0):.2f} |\n"
    md += f"| Avg Relays (Unsolved Challenges) | {relay.get('avg_relays_unsolved', 0):.2f} |\n"

    md += "\n"

    # Per-run details
    md += "## Per-Run Details\n\n"

    md += "### Baseline Runs\n\n"
    for i, run in enumerate(baseline_analysis['per_run']):
        md += f"**Run {i+1}** ({run['name']}):\n"
        md += f"- Success: {run['success']['count']}/11 ({run['success']['rate']*100:.1f}%)\n"
        md += f"- Solved: {run['success']['solved_vms']}\n"
        md += f"- Total Cost: ${run['cost']['total_cost']:.2f}\n"
        md += f"- Total Iterations: {run['iterations']['total_iterations']}\n\n"

    md += "### CHAP Runs\n\n"
    for i, run in enumerate(chap_analysis['per_run']):
        md += f"**Run {i+1}** ({run['name']}):\n"
        md += f"- Success: {run['success']['count']}/11 ({run['success']['rate']*100:.1f}%)\n"
        md += f"- Solved: {run['success']['solved_vms']}\n"
        md += f"- Total Cost: ${run['cost']['total_cost']:.2f}\n"
        md += f"- Total Iterations: {run['iterations']['total_iterations']}\n\n"

    return md


def generate_latex_tables(baseline_analysis, chap_analysis):
    """Generate LaTeX tables for IEEE paper."""
    latex = "% LaTeX Tables for IEEE Paper\n"
    latex += "% Generated by analyze_experiments.py\n\n"

    # Table 1: Success Rate
    latex += "% Table 1: Success Rate Comparison\n"
    latex += "\\begin{table}[htbp]\n"
    latex += "\\caption{Success Rate Comparison}\n"
    latex += "\\label{tab:success_rate}\n"
    latex += "\\centering\n"
    
    # Dynamic column count based on actual runs
    max_runs = max(len(baseline_analysis['per_run']), len(chap_analysis['per_run']), 1)
    num_pass_cols = max(0, max_runs - 1)  # Pass@2 through Pass@max_runs
    total_cols = 1 + max_runs + num_pass_cols  # Method + runs + pass@k columns
    col_spec = "|l|" + "c|" * (max_runs + num_pass_cols)
    latex += f"\\begin{{tabular}}{{{col_spec}}}\n"
    latex += "\\hline\n"
    
    # Build header dynamically
    header = "Method"
    for i in range(max_runs):
        header += f" & Run {i+1}"
    for k in range(2, max_runs + 1):
        header += f" & Pass@{k}"
    latex += f"{header} \\\\\n"
    latex += "\\hline\n"

    # Baseline row
    b_runs = baseline_analysis['per_run']
    b_row = "Baseline"
    for i in range(max_runs):
        if i < len(b_runs):
            b_row += f" & {b_runs[i]['success']['count']}/11"
        else:
            b_row += " & -"
    for k in range(2, max_runs + 1):
        pass_k = baseline_analysis['pass_at_k'].get(k, {})
        b_row += f" & {pass_k.get('count', '-')}/11"
    latex += f"{b_row} \\\\\n"

    # CHAP row
    c_runs = chap_analysis['per_run']
    c_row = "CHAP"
    for i in range(max_runs):
        if i < len(c_runs):
            c_row += f" & {c_runs[i]['success']['count']}/11"
        else:
            c_row += " & -"
    for k in range(2, max_runs + 1):
        pass_k = chap_analysis['pass_at_k'].get(k, {})
        c_row += f" & {pass_k.get('count', '-')}/11"
    latex += f"{c_row} \\\\\n"

    latex += "\\hline\n"
    latex += "\\end{tabular}\n"
    latex += "\\end{table}\n\n"

    # Table 2: Cost Efficiency (pooled across all challenges)
    latex += "% Table 2: Cost Efficiency\n"
    latex += "\\begin{table}[htbp]\n"
    latex += "\\caption{Cost Efficiency Comparison}\n"
    latex += "\\label{tab:cost}\n"
    latex += "\\centering\n"
    latex += "\\begin{tabular}{|l|c|c|c|c|}\n"
    latex += "\\hline\n"
    latex += "Method & Grand Total & Avg Cost/Chall & Avg Cost (Succ) & Avg Cost (Fail) \\\\\n"
    latex += "\\hline\n"

    b_cost = baseline_analysis['averages']['cost']
    c_cost = chap_analysis['averages']['cost']

    b_gt = f"\\${b_cost['grand_total']:.2f}" if b_cost.get('grand_total') else "-"
    c_gt = f"\\${c_cost['grand_total']:.2f}" if c_cost.get('grand_total') else "-"
    b_cpc = f"\\${b_cost['avg_per_challenge']:.2f}" if b_cost.get('avg_per_challenge') else "-"
    c_cpc = f"\\${c_cost['avg_per_challenge']:.2f}" if c_cost.get('avg_per_challenge') else "-"
    b_cps = f"\\${b_cost['avg_per_successful']:.2f}" if b_cost.get('avg_per_successful') else "-"
    c_cps = f"\\${c_cost['avg_per_successful']:.2f}" if c_cost.get('avg_per_successful') else "-"
    b_cpu = f"\\${b_cost['avg_per_unsuccessful']:.2f}" if b_cost.get('avg_per_unsuccessful') else "-"
    c_cpu = f"\\${c_cost['avg_per_unsuccessful']:.2f}" if c_cost.get('avg_per_unsuccessful') else "-"

    latex += f"Baseline & {b_gt} & {b_cpc} & {b_cps} & {b_cpu} \\\\\n"
    latex += f"CHAP & {c_gt} & {c_cpc} & {c_cps} & {c_cpu} \\\\\n"

    latex += "\\hline\n"
    latex += "\\end{tabular}\n"
    latex += "\\end{table}\n\n"

    # Table 3: Iteration Analysis (pooled across all challenges)
    latex += "% Table 3: Iteration Analysis\n"
    latex += "\\begin{table}[htbp]\n"
    latex += "\\caption{Iteration Analysis}\n"
    latex += "\\label{tab:iterations}\n"
    latex += "\\centering\n"
    latex += "\\begin{tabular}{|l|c|c|c|c|}\n"
    latex += "\\hline\n"
    latex += "Method & Avg Iter/Chall & Avg Iter (Succ) & Avg Iter (Fail) & Max Iter (Succ) \\\\\n"
    latex += "\\hline\n"

    b_iter = baseline_analysis['averages']['iterations']
    c_iter = chap_analysis['averages']['iterations']

    b_ipc = f"{b_iter['avg_per_challenge']:.1f}" if b_iter.get('avg_per_challenge') else "-"
    c_ipc = f"{c_iter['avg_per_challenge']:.1f}" if c_iter.get('avg_per_challenge') else "-"
    b_ips = f"{b_iter['avg_per_successful']:.1f}" if b_iter.get('avg_per_successful') else "-"
    c_ips = f"{c_iter['avg_per_successful']:.1f}" if c_iter.get('avg_per_successful') else "-"
    b_ipu = f"{b_iter['avg_per_unsuccessful']:.1f}" if b_iter.get('avg_per_unsuccessful') else "-"
    c_ipu = f"{c_iter['avg_per_unsuccessful']:.1f}" if c_iter.get('avg_per_unsuccessful') else "-"
    b_max = f"{b_iter['max_successful_iteration']}" if b_iter.get('max_successful_iteration') else "-"
    c_max = f"{c_iter['max_successful_iteration']}" if c_iter.get('max_successful_iteration') else "-"

    latex += f"Baseline & {b_ipc} & {b_ips} & {b_ipu} & {b_max} \\\\\n"
    latex += f"CHAP & {c_ipc} & {c_ips} & {c_ipu} & {c_max} \\\\\n"

    latex += "\\hline\n"
    latex += "\\end{tabular}\n"
    latex += "\\end{table}\n\n"

    # Table 4: CHAP Relay
    latex += "% Table 4: CHAP Relay Analysis\n"
    latex += "\\begin{table}[htbp]\n"
    latex += "\\caption{CHAP Context Relay Analysis}\n"
    latex += "\\label{tab:relay}\n"
    latex += "\\centering\n"
    latex += "\\begin{tabular}{|l|c|}\n"
    latex += "\\hline\n"
    latex += "Metric & Value \\\\\n"
    latex += "\\hline\n"

    relay = chap_analysis.get('relay_metrics', {})
    latex += f"Total Relays & {relay.get('total_relays', 0)} \\\\\n"
    latex += f"Avg Relays/Challenge & {relay.get('avg_per_challenge', 0):.2f} \\\\\n"
    latex += f"Auto-Triggered & {relay.get('auto_triggers', 0)} ({relay.get('auto_percent', 0):.1f}\\%) \\\\\n"
    latex += f"Manual-Triggered & {relay.get('manual_triggers', 0)} ({relay.get('manual_percent', 0):.1f}\\%) \\\\\n"
    latex += f"Avg Relays (Solved) & {relay.get('avg_relays_solved', 0):.2f} \\\\\n"
    latex += f"Avg Relays (Unsolved) & {relay.get('avg_relays_unsolved', 0):.2f} \\\\\n"

    latex += "\\hline\n"
    latex += "\\end{tabular}\n"
    latex += "\\end{table}\n"

    return latex


# ============== FIGURE GENERATION ==============

def generate_figures(baseline_analysis, chap_analysis, output_dir="results/figures"):
    """Generate all figures for paper."""
    if not MATPLOTLIB_AVAILABLE or not NUMPY_AVAILABLE:
        print("Skipping figure generation (matplotlib/numpy not available)")
        return

    os.makedirs(output_dir, exist_ok=True)

    # Try to use a nice style
    try:
        plt.style.use('seaborn-v0_8-whitegrid')
    except:
        try:
            plt.style.use('seaborn-whitegrid')
        except:
            pass  # Use default style

    # Figure 1: Success Rate by Run (Bar Chart)
    fig, ax = plt.subplots(figsize=(8, 5))

    b_rates = [r['success']['rate'] * 100 for r in baseline_analysis['per_run']]
    c_rates = [r['success']['rate'] * 100 for r in chap_analysis['per_run']]

    max_runs = max(len(b_rates), len(c_rates), 1)
    x = np.arange(max_runs)
    width = 0.35

    # Pad shorter list with 0
    b_rates_padded = b_rates + [0] * (max_runs - len(b_rates))
    c_rates_padded = c_rates + [0] * (max_runs - len(c_rates))

    bars1 = ax.bar(x - width/2, b_rates_padded, width, label='Baseline', color='steelblue')
    bars2 = ax.bar(x + width/2, c_rates_padded, width, label='CHAP', color='forestgreen')

    ax.set_ylabel('Success Rate (%)')
    ax.set_xlabel('Run')
    ax.set_title('Success Rate by Experiment Run')
    ax.set_xticks(x)
    ax.set_xticklabels([f'Run {i+1}' for i in range(max_runs)])
    ax.legend()
    ax.set_ylim(0, 100)

    # Add value labels on bars
    for bar in bars1:
        if bar.get_height() > 0:
            ax.annotate(f'{bar.get_height():.1f}%',
                       xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                       ha='center', va='bottom', fontsize=9)
    for bar in bars2:
        if bar.get_height() > 0:
            ax.annotate(f'{bar.get_height():.1f}%',
                       xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                       ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'success_rate_by_run.png'), dpi=300)
    plt.savefig(os.path.join(output_dir, 'success_rate_by_run.pdf'))
    plt.close()

    # Figure 2: Pass@k Comparison
    fig, ax = plt.subplots(figsize=(8, 5))

    max_k = max(len(baseline_analysis['per_run']), len(chap_analysis['per_run']), 1)
    ks = list(range(1, max_k + 1))

    b_pass = [baseline_analysis['pass_at_k'].get(k, {}).get('rate', 0) * 100 for k in ks]
    c_pass = [chap_analysis['pass_at_k'].get(k, {}).get('rate', 0) * 100 for k in ks]

    x = np.arange(len(ks))
    bars1 = ax.bar(x - width/2, b_pass, width, label='Baseline', color='steelblue')
    bars2 = ax.bar(x + width/2, c_pass, width, label='CHAP', color='forestgreen')

    ax.set_ylabel('Pass Rate (%)')
    ax.set_xlabel('k')
    ax.set_title('Pass@k Comparison')
    ax.set_xticks(x)
    ax.set_xticklabels([f'Pass@{k}' for k in ks])
    ax.legend()
    ax.set_ylim(0, 100)

    # Add value labels
    for bar in bars1:
        if bar.get_height() > 0:
            ax.annotate(f'{bar.get_height():.1f}%',
                       xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                       ha='center', va='bottom', fontsize=9)
    for bar in bars2:
        if bar.get_height() > 0:
            ax.annotate(f'{bar.get_height():.1f}%',
                       xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                       ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'pass_at_k.png'), dpi=300)
    plt.savefig(os.path.join(output_dir, 'pass_at_k.pdf'))
    plt.close()

    # Figure 3: Cost Comparison (grouped bar chart)
    fig, ax = plt.subplots(figsize=(10, 6))

    b_cost = baseline_analysis['averages']['cost']
    c_cost = chap_analysis['averages']['cost']

    # Get values, replacing None with 0
    b_vals = [
        b_cost.get('avg_per_challenge', 0) or 0,
        b_cost.get('avg_per_successful', 0) or 0,
        b_cost.get('avg_per_unsuccessful', 0) or 0
    ]
    c_vals = [
        c_cost.get('avg_per_challenge', 0) or 0,
        c_cost.get('avg_per_successful', 0) or 0,
        c_cost.get('avg_per_unsuccessful', 0) or 0
    ]

    x = np.arange(3)
    width = 0.35
    labels = ['Avg/Challenge', 'Avg (Success)', 'Avg (Fail)']

    bars1 = ax.bar(x - width/2, b_vals, width, label='Baseline', color='steelblue')
    bars2 = ax.bar(x + width/2, c_vals, width, label='CHAP', color='forestgreen')

    ax.set_ylabel('Cost ($)')
    ax.set_title('Cost Comparison: Baseline vs CHAP')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()

    # Add value labels
    for bar in bars1:
        if bar.get_height() > 0:
            ax.annotate(f'${bar.get_height():.2f}',
                       xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                       ha='center', va='bottom', fontsize=9)
    for bar in bars2:
        if bar.get_height() > 0:
            ax.annotate(f'${bar.get_height():.2f}',
                       xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                       ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'cost_comparison.png'), dpi=300)
    plt.savefig(os.path.join(output_dir, 'cost_comparison.pdf'))
    plt.close()

    # Figure 4: CHAP Relay Trigger Distribution
    relay = chap_analysis.get('relay_metrics', {})
    auto = relay.get('auto_triggers', 0)
    manual = relay.get('manual_triggers', 0)

    if auto + manual > 0:
        fig, ax = plt.subplots(figsize=(6, 5))

        triggers = [auto, manual]
        labels = [f'Auto-Triggered\n({auto})', f'Manual-Triggered\n({manual})']
        colors = ['coral', 'lightseagreen']

        wedges, texts, autotexts = ax.pie(triggers, labels=labels, autopct='%1.1f%%',
                                          colors=colors, startangle=90)
        ax.set_title('CHAP Relay Trigger Distribution')

        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'relay_triggers.png'), dpi=300)
        plt.savefig(os.path.join(output_dir, 'relay_triggers.pdf'))
        plt.close()

    # Figure 5: Iterations Comparison (grouped bar chart)
    fig, ax = plt.subplots(figsize=(10, 6))

    b_iter = baseline_analysis['averages']['iterations']
    c_iter = chap_analysis['averages']['iterations']

    # Get values, replacing None with 0
    b_vals = [
        b_iter.get('avg_per_challenge', 0) or 0,
        b_iter.get('avg_per_successful', 0) or 0,
        b_iter.get('avg_per_unsuccessful', 0) or 0
    ]
    c_vals = [
        c_iter.get('avg_per_challenge', 0) or 0,
        c_iter.get('avg_per_successful', 0) or 0,
        c_iter.get('avg_per_unsuccessful', 0) or 0
    ]

    x = np.arange(3)
    width = 0.35
    labels = ['Avg/Challenge', 'Avg (Success)', 'Avg (Fail)']

    bars1 = ax.bar(x - width/2, b_vals, width, label='Baseline', color='steelblue')
    bars2 = ax.bar(x + width/2, c_vals, width, label='CHAP', color='forestgreen')

    ax.set_ylabel('Iterations')
    ax.set_title('Iteration Comparison: Baseline vs CHAP')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()

    # Add value labels
    for bar in bars1:
        if bar.get_height() > 0:
            ax.annotate(f'{bar.get_height():.1f}',
                       xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                       ha='center', va='bottom', fontsize=9)
    for bar in bars2:
        if bar.get_height() > 0:
            ax.annotate(f'{bar.get_height():.1f}',
                       xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                       ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'iterations_comparison.png'), dpi=300)
    plt.savefig(os.path.join(output_dir, 'iterations_comparison.pdf'))
    plt.close()

    # Figure 6: Max Successful Iteration (bar chart)
    fig, ax = plt.subplots(figsize=(6, 5))

    b_max = baseline_analysis['averages']['iterations'].get('max_successful_iteration', 0) or 0
    c_max = chap_analysis['averages']['iterations'].get('max_successful_iteration', 0) or 0

    max_iters = [b_max, c_max]
    bars = ax.bar(['Baseline', 'CHAP'], max_iters, color=['steelblue', 'forestgreen'])
    ax.set_ylabel('Iteration Count')
    ax.set_title('Max Iteration Where Flag Was Captured')

    # Add value labels
    for bar in bars:
        if bar.get_height() > 0:
            ax.annotate(f'{int(bar.get_height())}',
                       xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                       ha='center', va='bottom', fontsize=10)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'max_iteration_success.png'), dpi=300)
    plt.savefig(os.path.join(output_dir, 'max_iteration_success.pdf'))
    plt.close()

    # Figure 7: Iterations Comparison with Max (grouped bar chart)
    fig, ax = plt.subplots(figsize=(10, 6))

    b_iter = baseline_analysis['averages']['iterations']
    c_iter = chap_analysis['averages']['iterations']

    # Get values, replacing None with 0
    b_vals = [
        b_iter.get('avg_per_challenge', 0) or 0,
        b_iter.get('avg_per_successful', 0) or 0,
        b_iter.get('avg_per_unsuccessful', 0) or 0,
        b_iter.get('max_successful_iteration', 0) or 0
    ]
    c_vals = [
        c_iter.get('avg_per_challenge', 0) or 0,
        c_iter.get('avg_per_successful', 0) or 0,
        c_iter.get('avg_per_unsuccessful', 0) or 0,
        c_iter.get('max_successful_iteration', 0) or 0
    ]

    x = np.arange(4)
    width = 0.35
    labels = ['Avg/Challenge', 'Avg (Success)', 'Avg (Fail)', 'Max (Success)']

    bars1 = ax.bar(x - width/2, b_vals, width, label='Baseline', color='steelblue')
    bars2 = ax.bar(x + width/2, c_vals, width, label='CHAP', color='forestgreen')

    ax.set_ylabel('Iterations')
    ax.set_title('Iteration Comparison: Baseline vs CHAP (with Max)')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()

    # Add value labels
    for bar in bars1:
        if bar.get_height() > 0:
            ax.annotate(f'{bar.get_height():.0f}',
                       xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                       ha='center', va='bottom', fontsize=9)
    for bar in bars2:
        if bar.get_height() > 0:
            ax.annotate(f'{bar.get_height():.0f}',
                       xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                       ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'iterations_comparison_with_max.png'), dpi=300)
    plt.savefig(os.path.join(output_dir, 'iterations_comparison_with_max.pdf'))
    plt.close()

    # Figure 8: Cost Comparison with Max (grouped bar chart)
    fig, ax = plt.subplots(figsize=(10, 6))

    b_cost = baseline_analysis['averages']['cost']
    c_cost = chap_analysis['averages']['cost']

    # Calculate max cost per challenge across runs
    b_max_cost = max([r['cost']['total_cost'] / len(r['cost'].get('costs_by_vm', {})) 
                      for r in baseline_analysis['per_run'] 
                      if r['cost'].get('costs_by_vm')], default=0)
    c_max_cost = max([r['cost']['total_cost'] / len(r['cost'].get('costs_by_vm', {})) 
                      for r in chap_analysis['per_run'] 
                      if r['cost'].get('costs_by_vm')], default=0)

    # Get values, replacing None with 0
    b_vals = [
        b_cost.get('avg_per_challenge', 0) or 0,
        b_cost.get('avg_per_successful', 0) or 0,
        b_cost.get('avg_per_unsuccessful', 0) or 0,
        b_max_cost
    ]
    c_vals = [
        c_cost.get('avg_per_challenge', 0) or 0,
        c_cost.get('avg_per_successful', 0) or 0,
        c_cost.get('avg_per_unsuccessful', 0) or 0,
        c_max_cost
    ]

    x = np.arange(4)
    width = 0.35
    labels = ['Avg/Challenge', 'Avg (Success)', 'Avg (Fail)', 'Max/Challenge']

    bars1 = ax.bar(x - width/2, b_vals, width, label='Baseline', color='steelblue')
    bars2 = ax.bar(x + width/2, c_vals, width, label='CHAP', color='forestgreen')

    ax.set_ylabel('Cost ($)')
    ax.set_title('Cost Comparison: Baseline vs CHAP (with Max)')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()

    # Add value labels
    for bar in bars1:
        if bar.get_height() > 0:
            ax.annotate(f'${bar.get_height():.2f}',
                       xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                       ha='center', va='bottom', fontsize=9)
    for bar in bars2:
        if bar.get_height() > 0:
            ax.annotate(f'${bar.get_height():.2f}',
                       xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                       ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'cost_comparison_with_max.png'), dpi=300)
    plt.savefig(os.path.join(output_dir, 'cost_comparison_with_max.pdf'))
    plt.close()

    print(f"Figures saved to {output_dir}/")


# ============== MAIN ANALYSIS ==============

def analyze_method(experiments):
    """Run full analysis for one method (baseline or chap).

    Uses pooled statistics: collects all individual challenge data points
    across runs, then computes mean and std over the pooled data.
    """
    per_run = []

    # Collect pooled data across all runs for scientifically correct averaging
    all_costs_successful = []
    all_costs_unsuccessful = []
    all_costs_all = []
    all_iters_successful = []
    all_iters_unsuccessful = []
    all_iters_all = []
    all_tokens_successful = []
    grand_total_cost = 0

    for exp in experiments:
        run_data = {
            'path': exp['path'],
            'name': exp['name'],
            'success': calculate_success_metrics(exp),
            'cost': calculate_cost_metrics(exp),
            'tokens': calculate_token_metrics(exp),
            'iterations': calculate_iteration_metrics(exp)
        }
        per_run.append(run_data)
        grand_total_cost += run_data['cost']['total_cost']

        # Collect individual challenge data for pooling
        for vm, data in exp['challenges'].items():
            cost = data.get('summary', {}).get('total_cost', 0) or 0
            iters = data.get('summary', {}).get('iterations', 0) or 0
            tokens = data.get('tokens', {})
            token_total = (tokens.get('total_input_tokens', 0) or 0) + (tokens.get('total_output_tokens', 0) or 0)

            all_costs_all.append(cost)
            all_iters_all.append(iters)

            if data.get('summary', {}).get('flag_valid', False):
                all_costs_successful.append(cost)
                all_iters_successful.append(iters)
                all_tokens_successful.append(token_total)
            else:
                all_costs_unsuccessful.append(cost)
                all_iters_unsuccessful.append(iters)

    # Calculate pass@k for all available k values
    pass_at_k = {}
    for k in range(1, len(experiments) + 1):
        pass_at_k[k] = calculate_pass_at_k(experiments, k)

    # Calculate pooled averages
    return {
        'per_run': per_run,
        'pass_at_k': pass_at_k,
        'averages': {
            'cost': {
                'grand_total': grand_total_cost,
                'avg_per_challenge': safe_mean(all_costs_all),
                'avg_per_successful': safe_mean(all_costs_successful) if all_costs_successful else None,
                'avg_per_unsuccessful': safe_mean(all_costs_unsuccessful) if all_costs_unsuccessful else None,
            },
            'tokens': {
                'avg_per_successful': safe_mean(all_tokens_successful) if all_tokens_successful else None
            },
            'iterations': {
                'avg_per_challenge': safe_mean(all_iters_all),
                'avg_per_successful': safe_mean(all_iters_successful) if all_iters_successful else None,
                'avg_per_unsuccessful': safe_mean(all_iters_unsuccessful) if all_iters_unsuccessful else None,
                'max_successful_iteration': max(all_iters_successful) if all_iters_successful else None,
            }
        }
    }


def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description='Analyze CTF benchmark experiments')
    parser.add_argument('--runs', type=int, default=None,
                       help='Number of runs to include per method (default: all)')
    parser.add_argument('--output-dir', type=str, default='analysis_results',
                       help='Output directory (default: analysis_results)')
    args = parser.parse_args()

    output_dir = args.output_dir
    max_runs = args.runs

    print("=" * 60)
    print("CTF Benchmark Analysis")
    print("=" * 60)

    # Discover experiments
    print("\nDiscovering experiments...")
    experiments = discover_experiments("results")

    # Limit runs if specified
    if max_runs is not None:
        experiments['baseline'] = experiments['baseline'][:max_runs]
        experiments['chap'] = experiments['chap'][:max_runs]
        print(f"Limiting to first {max_runs} runs per method")

    print(f"Found {len(experiments['baseline'])} baseline runs:")
    for p in experiments['baseline']:
        print(f"  - {p}")
    print(f"Found {len(experiments['chap'])} CHAP runs:")
    for p in experiments['chap']:
        print(f"  - {p}")

    if not experiments['baseline'] and not experiments['chap']:
        print("\nNo experiments found! Make sure results folder contains experiment data.")
        return

    # Load all experiments
    print("\nLoading experiment data...")
    baseline_data = [load_experiment(p) for p in experiments['baseline']]
    chap_data = [load_experiment(p) for p in experiments['chap']]

    # Analyze each method
    print("\nAnalyzing baseline...")
    baseline_analysis = analyze_method(baseline_data) if baseline_data else {
        'per_run': [], 'pass_at_k': {},
        'averages': {'cost': {'avg_total': 0, 'avg_per_flag': None},
                    'tokens': {'avg_per_flag': None},
                    'iterations': {'avg_per_flag': None}}
    }

    print("Analyzing CHAP...")
    chap_analysis = analyze_method(chap_data) if chap_data else {
        'per_run': [], 'pass_at_k': {},
        'averages': {'cost': {'avg_total': 0, 'avg_per_flag': None},
                    'tokens': {'avg_per_flag': None},
                    'iterations': {'avg_per_flag': None}}
    }

    if chap_data:
        chap_analysis['relay_metrics'] = calculate_relay_metrics(chap_data)
    else:
        chap_analysis['relay_metrics'] = {}

    # Generate outputs
    print("\nGenerating outputs...")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # JSON output
    output = {
        'baseline': baseline_analysis,
        'chap': chap_analysis,
        'comparison': {}
    }

    # Calculate comparison metrics
    if baseline_analysis['pass_at_k'] and chap_analysis['pass_at_k']:
        min_k = min(len(baseline_analysis['per_run']), len(chap_analysis['per_run']))
        if min_k >= 2:
            b_rate = baseline_analysis['pass_at_k'].get(2, {}).get('rate', 0)
            c_rate = chap_analysis['pass_at_k'].get(2, {}).get('rate', 0)
            output['comparison']['pass_at_2_improvement'] = (c_rate - b_rate) * 100

    json_path = os.path.join(output_dir, 'analysis_output.json')
    with open(json_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Saved: {json_path}")

    # Markdown tables
    md_tables = generate_markdown_tables(baseline_analysis, chap_analysis)
    md_path = os.path.join(output_dir, 'paper_tables.md')
    with open(md_path, 'w') as f:
        f.write(md_tables)
    print(f"Saved: {md_path}")

    # LaTeX tables
    latex_tables = generate_latex_tables(baseline_analysis, chap_analysis)
    tex_path = os.path.join(output_dir, 'paper_tables.tex')
    with open(tex_path, 'w') as f:
        f.write(latex_tables)
    print(f"Saved: {tex_path}")

    # Figures
    figures_dir = os.path.join(output_dir, 'figures')
    generate_figures(baseline_analysis, chap_analysis, output_dir=figures_dir)

    # Console summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if baseline_data:
        print(f"\nBaseline (n={len(baseline_data)} runs):")
        for k, v in sorted(baseline_analysis['pass_at_k'].items()):
            print(f"  Pass@{k}: {v['count']}/11 ({v['rate']*100:.1f}%) - {v['challenges']}")
        if baseline_analysis['averages']['cost']['avg_per_flag']:
            print(f"  Avg cost/flag: ${baseline_analysis['averages']['cost']['avg_per_flag']:.2f}")
        if baseline_analysis['averages']['iterations']['avg_per_flag']:
            print(f"  Avg iterations/flag: {baseline_analysis['averages']['iterations']['avg_per_flag']:.1f}")

    if chap_data:
        print(f"\nCHAP (n={len(chap_data)} runs):")
        for k, v in sorted(chap_analysis['pass_at_k'].items()):
            print(f"  Pass@{k}: {v['count']}/11 ({v['rate']*100:.1f}%) - {v['challenges']}")
        if chap_analysis['averages']['cost']['avg_per_flag']:
            print(f"  Avg cost/flag: ${chap_analysis['averages']['cost']['avg_per_flag']:.2f}")
        if chap_analysis['averages']['iterations']['avg_per_flag']:
            print(f"  Avg iterations/flag: {chap_analysis['averages']['iterations']['avg_per_flag']:.1f}")

        relay = chap_analysis.get('relay_metrics', {})
        if relay:
            print(f"\n  Relay Analysis:")
            print(f"    Total relays: {relay.get('total_relays', 0)}")
            print(f"    Avg per challenge: {relay.get('avg_per_challenge', 0):.2f}")
            print(f"    Auto: {relay.get('auto_triggers', 0)} ({relay.get('auto_percent', 0):.1f}%)")
            print(f"    Manual: {relay.get('manual_triggers', 0)} ({relay.get('manual_percent', 0):.1f}%)")
            print(f"    Avg relays (solved): {relay.get('avg_relays_solved', 0):.2f}")
            print(f"    Avg relays (unsolved): {relay.get('avg_relays_unsolved', 0):.2f}")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
