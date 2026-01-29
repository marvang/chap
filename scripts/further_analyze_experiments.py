#!/usr/bin/env python3
"""
CTF Benchmark Analysis Script - Publication Quality Figures
Generates multiple style variations of figures for scientific papers.

Usage:
    python scripts/further_analyze_experiments.py [--runs N] [--output-dir DIR]

Options:
    --runs N        Number of runs to include per method (default: all)
    --output-dir    Output directory (default: analysis_results/publication_figures)
"""

import json
import os
import glob
import re
import argparse
from pathlib import Path
from collections import defaultdict
from statistics import mean as stats_mean

# Try to import numpy
try:
    import numpy as np
    def safe_mean(lst):
        return float(np.mean(lst)) if lst else 0
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    def safe_mean(lst):
        return stats_mean(lst) if lst else 0

# Try to import matplotlib
try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    if NUMPY_AVAILABLE:
        MATPLOTLIB_AVAILABLE = True
    else:
        MATPLOTLIB_AVAILABLE = False
        print("Warning: numpy not available, skipping figure generation")
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available, skipping figure generation")


# ============== STYLE CONFIGURATIONS ==============

STYLE_CONFIGS = {
    'style_a': {
        'name': 'Navy & Coral',
        'colors': ['#1f4e79', '#d35400'],  # Navy blue, Coral orange
        'edgecolor': '#333333',
        'hatch': [None, None],
        'description': 'High contrast navy/coral for color prints'
    },
    'style_c': {
        'name': 'Teal & Rust',
        'colors': ['#2a9d8f', '#e76f51'],  # Teal, Rust/terracotta
        'edgecolor': '#333333',
        'hatch': [None, None],
        'description': 'Colorblind-friendly teal/rust palette'
    },
    'style_d': {
        'name': 'Navy & Coral + Hatch',
        'colors': ['#1f4e79', '#d35400'],  # Navy blue, Coral orange
        'edgecolor': '#222222',
        'hatch': ['///', '...'],  # Diagonal lines vs dots
        'description': 'Color + hatching for print compatibility'
    },
    'style_e': {
        'name': 'Teal & Rust + Hatch',
        'colors': ['#2a9d8f', '#e76f51'],  # Teal, Rust
        'edgecolor': '#222222',
        'hatch': ['\\\\\\', 'xxx'],  # Backslash vs crosshatch
        'description': 'Colorblind-friendly + hatching for print'
    },
    'style_f': {
        'name': 'Sapphire & Amber',
        'colors': ['#1a5f7a', '#ffb347'],  # Deep blue, Warm amber
        'edgecolor': '#1f2d3d',
        'hatch': [None, None],
        'description': 'High-contrast blue/amber for crisp separation'
    },
    'style_g': {
        'name': 'Forest & Sand + Hatch',
        'colors': ['#2f5233', '#c2a878'],  # Forest green, Sand
        'edgecolor': '#1f1f1f',
        'hatch': ['xx', '--'],  # Cross vs dashed
        'description': 'Earthy palette with bold hatching for clarity'
    },
}

# Typography settings for scientific publications
FONT_CONFIG = {
    'title_size': 14,
    'title_weight': 'bold',
    'axis_label_size': 13,
    'tick_label_size': 12,
    'legend_size': 13,
    'annotation_size': 13,
    'font_family': 'sans-serif',
}

# Figure dimensions
FIG_CONFIG = {
    'bar_chart_size': (9, 6),
    'pie_chart_size': (7, 6),
    'simple_bar_size': (7, 5),
    'dpi': 300,
    'bar_width': 0.28,  # Narrower bars
}


# ============== DATA LOADING (from analyze_experiments.py) ==============

EXPERIMENT_PATTERNS = {
    'baseline': re.compile(r'^new_baseline_gpt-5\.1-codex-mini-arm_run[1-3]$'),
    'chap': re.compile(r'^new_chap_auto_trigger_gpt-5\.1-codex-mini-arm_run[1-3]$'),
}


def discover_experiments(results_dir="results"):
    """Auto-discover experiments by folder name."""
    experiments = {'baseline': [], 'chap': []}

    if not os.path.exists(results_dir):
        print(f"Error: Results directory '{results_dir}' not found")
        return experiments

    for folder in sorted(os.listdir(results_dir)):
        folder_path = os.path.join(results_dir, folder)
        if not os.path.isdir(folder_path):
            continue

        matched_method = None
        for method, pattern in EXPERIMENT_PATTERNS.items():
            if pattern.match(folder):
                matched_method = method
                break

        if matched_method is None:
            continue

        exp_dirs = sorted(glob.glob(os.path.join(folder_path, "experiment_*")))
        if not exp_dirs:
            continue

        exp_path = exp_dirs[0]

        if not os.path.exists(os.path.join(exp_path, "experiment_summary.json")):
            print(f"Warning: No experiment_summary.json in {exp_path}, skipping")
            continue

        experiments[matched_method].append(exp_path)

    return experiments


def load_experiment(exp_path):
    """Load all data for one experiment."""
    data = {
        'path': exp_path,
        'name': os.path.basename(os.path.dirname(exp_path)),
        'metadata': {},
        'challenges': {}
    }

    summary_path = os.path.join(exp_path, "experiment_summary.json")
    try:
        with open(summary_path) as f:
            data['metadata'] = json.load(f).get('metadata', {})
    except Exception as e:
        print(f"Error loading {summary_path}: {e}")
        return data

    challenges = data['metadata'].get('ctf_challenges', [])
    for vm in challenges:
        vm_path = os.path.join(exp_path, vm)
        challenge_data = {'name': vm}

        summary_file = os.path.join(vm_path, "summary.json")
        if os.path.exists(summary_file):
            try:
                with open(summary_file) as f:
                    challenge_data['summary'] = json.load(f)
            except Exception as e:
                print(f"Error loading {summary_file}: {e}")

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


# ============== METRICS CALCULATION (from analyze_experiments.py) ==============

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

            for trigger in data.get('relay_triggers', []):
                trigger_type = trigger.get('trigger_type', '')
                if trigger_type == 'auto':
                    auto_triggers += 1
                elif trigger_type == 'manual':
                    manual_triggers += 1

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


def analyze_method(experiments):
    """Run full analysis for one method (baseline or chap)."""
    per_run = []
    for exp in experiments:
        run_data = {
            'path': exp['path'],
            'name': exp['name'],
            'success': calculate_success_metrics(exp),
            'cost': calculate_cost_metrics(exp),
            'iterations': calculate_iteration_metrics(exp)
        }
        per_run.append(run_data)

    pass_at_k = {}
    for k in range(1, len(experiments) + 1):
        pass_at_k[k] = calculate_pass_at_k(experiments, k)

    costs_per_flag = [r['cost']['cost_per_flag'] for r in per_run if r['cost']['cost_per_flag'] is not None]
    costs_per_successful = [r['cost']['avg_per_successful'] for r in per_run if r['cost']['avg_per_successful'] is not None]
    costs_per_unsuccessful = [r['cost']['avg_per_unsuccessful'] for r in per_run if r['cost']['avg_per_unsuccessful'] is not None]

    iters_per_flag = [r['iterations']['iterations_per_flag'] for r in per_run if r['iterations']['iterations_per_flag'] is not None]
    iters_per_successful = [r['iterations']['avg_per_successful'] for r in per_run if r['iterations']['avg_per_successful'] is not None]
    iters_per_unsuccessful = [r['iterations']['avg_per_unsuccessful'] for r in per_run if r['iterations']['avg_per_unsuccessful'] is not None]
    max_successful_iters = [r['iterations']['max_successful_iteration'] for r in per_run if r['iterations']['max_successful_iteration'] is not None]

    return {
        'per_run': per_run,
        'pass_at_k': pass_at_k,
        'averages': {
            'cost': {
                'avg_total': safe_mean([r['cost']['total_cost'] for r in per_run]),
                'avg_per_challenge': safe_mean([r['cost']['avg_per_challenge'] for r in per_run]),
                'avg_per_flag': safe_mean(costs_per_flag) if costs_per_flag else None,
                'avg_per_successful': safe_mean(costs_per_successful) if costs_per_successful else None,
                'avg_per_unsuccessful': safe_mean(costs_per_unsuccessful) if costs_per_unsuccessful else None
            },
            'iterations': {
                'avg_per_challenge': safe_mean([r['iterations']['avg_per_challenge'] for r in per_run]),
                'avg_per_flag': safe_mean(iters_per_flag) if iters_per_flag else None,
                'avg_per_successful': safe_mean(iters_per_successful) if iters_per_successful else None,
                'avg_per_unsuccessful': safe_mean(iters_per_unsuccessful) if iters_per_unsuccessful else None,
                'max_successful_iteration': max(max_successful_iters) if max_successful_iters else None
            }
        }
    }


# ============== PUBLICATION QUALITY FIGURE GENERATION ==============

def setup_figure_style():
    """Configure matplotlib for publication-quality figures."""
    plt.rcParams.update({
        'font.family': FONT_CONFIG['font_family'],
        'font.size': FONT_CONFIG['tick_label_size'],
        'axes.titlesize': FONT_CONFIG['title_size'],
        'axes.titleweight': FONT_CONFIG['title_weight'],
        'axes.labelsize': FONT_CONFIG['axis_label_size'],
        'xtick.labelsize': FONT_CONFIG['tick_label_size'],
        'ytick.labelsize': FONT_CONFIG['tick_label_size'],
        'legend.fontsize': FONT_CONFIG['legend_size'],
        'figure.dpi': FIG_CONFIG['dpi'],
        'savefig.dpi': FIG_CONFIG['dpi'],
        'savefig.bbox': 'tight',
        'axes.spines.top': False,
        'axes.spines.right': False,
        'axes.grid': True,
        'grid.alpha': 0.3,
        'grid.linestyle': ':',
    })


def create_grouped_bar_chart(ax, x_labels, baseline_vals, chap_vals, ylabel, title,
                             style_config, value_format='{}', show_values=True):
    """Create a grouped bar chart with the specified style."""
    x = np.arange(len(x_labels))
    width = FIG_CONFIG['bar_width']

    colors = style_config['colors']
    edgecolor = style_config['edgecolor']
    hatches = style_config['hatch']

    bars1 = ax.bar(x - width/2 - 0.02, baseline_vals, width,
                   label='Baseline', color=colors[0], edgecolor=edgecolor,
                   linewidth=1.2, hatch=hatches[0])
    bars2 = ax.bar(x + width/2 + 0.02, chap_vals, width,
                   label='CHAP', color=colors[1], edgecolor=edgecolor,
                   linewidth=1.2, hatch=hatches[1])

    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels)
    ax.legend(loc='upper right', framealpha=0.9, edgecolor='gray')

    # Add value labels
    if show_values:
        for bar in bars1:
            height = bar.get_height()
            if height > 0:
                ax.annotate(value_format.format(height),
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           ha='center', va='bottom',
                           fontsize=FONT_CONFIG['annotation_size'],
                           fontweight='bold')
        for bar in bars2:
            height = bar.get_height()
            if height > 0:
                ax.annotate(value_format.format(height),
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           ha='center', va='bottom',
                           fontsize=FONT_CONFIG['annotation_size'],
                           fontweight='bold')

    return bars1, bars2


def generate_success_rate_figure(baseline_analysis, chap_analysis, output_dir, style_key, style_config):
    """Generate success rate by run figure."""
    fig, ax = plt.subplots(figsize=FIG_CONFIG['bar_chart_size'])

    b_rates = [r['success']['rate'] * 100 for r in baseline_analysis['per_run']]
    c_rates = [r['success']['rate'] * 100 for r in chap_analysis['per_run']]

    max_runs = max(len(b_rates), len(c_rates), 1)
    b_rates_padded = b_rates + [0] * (max_runs - len(b_rates))
    c_rates_padded = c_rates + [0] * (max_runs - len(c_rates))

    x_labels = [f'Run {i+1}' for i in range(max_runs)]

    create_grouped_bar_chart(ax, x_labels, b_rates_padded, c_rates_padded,
                            'Success Rate (%)', 'Success Rate by Experiment Run',
                            style_config, value_format='{:.1f}%')

    ax.set_ylim(0, 100)
    ax.set_xlabel('Experiment Run')

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'fig1_success_rate_{style_key}.pdf'))
    plt.close()


def generate_pass_at_k_figure(baseline_analysis, chap_analysis, output_dir, style_key, style_config):
    """Generate pass@k comparison figure."""
    fig, ax = plt.subplots(figsize=FIG_CONFIG['bar_chart_size'])

    max_k = max(len(baseline_analysis['per_run']), len(chap_analysis['per_run']), 1)
    ks = list(range(1, max_k + 1))

    b_pass = [baseline_analysis['pass_at_k'].get(k, {}).get('rate', 0) * 100 for k in ks]
    c_pass = [chap_analysis['pass_at_k'].get(k, {}).get('rate', 0) * 100 for k in ks]

    x_labels = [f'Pass@{k}' for k in ks]

    create_grouped_bar_chart(ax, x_labels, b_pass, c_pass,
                            'Pass Rate (%)', 'Pass@k Comparison',
                            style_config, value_format='{:.1f}%')

    ax.set_ylim(0, 100)
    ax.set_xlabel('k (number of runs)')

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'fig2_pass_at_k_{style_key}.pdf'))
    plt.close()


def generate_cost_comparison_figure(baseline_analysis, chap_analysis, output_dir, style_key, style_config):
    """Generate cost comparison figure."""
    fig, ax = plt.subplots(figsize=FIG_CONFIG['bar_chart_size'])

    b_cost = baseline_analysis['averages']['cost']
    c_cost = chap_analysis['averages']['cost']

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

    x_labels = ['All Challenges', 'Successful', 'Unsuccessful']

    create_grouped_bar_chart(ax, x_labels, b_vals, c_vals,
                            'Average Cost ($)', 'Cost Comparison by Challenge Outcome',
                            style_config, value_format='${:.2f}')
    ax.legend(loc='upper left', framealpha=0.9, edgecolor='gray')

    ax.set_xlabel('Challenge Category')

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'fig3_cost_comparison_{style_key}.pdf'))
    plt.close()


def generate_iterations_comparison_figure(baseline_analysis, chap_analysis, output_dir, style_key, style_config):
    """Generate iterations comparison figure."""
    fig, ax = plt.subplots(figsize=FIG_CONFIG['bar_chart_size'])

    b_iter = baseline_analysis['averages']['iterations']
    c_iter = chap_analysis['averages']['iterations']

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

    x_labels = ['All Challenges', 'Successful', 'Unsuccessful']

    create_grouped_bar_chart(ax, x_labels, b_vals, c_vals,
                            'Average Iterations', 'Iteration Comparison by Challenge Outcome',
                            style_config, value_format='{:.1f}')

    ax.set_xlabel('Challenge Category')

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'fig4_iterations_comparison_{style_key}.pdf'))
    plt.close()


def generate_max_iteration_figure(baseline_analysis, chap_analysis, output_dir, style_key, style_config):
    """Generate max successful iteration figure."""
    fig, ax = plt.subplots(figsize=FIG_CONFIG['simple_bar_size'])

    b_max = baseline_analysis['averages']['iterations'].get('max_successful_iteration', 0) or 0
    c_max = chap_analysis['averages']['iterations'].get('max_successful_iteration', 0) or 0

    colors = style_config['colors']
    edgecolor = style_config['edgecolor']
    hatches = style_config['hatch']

    x = np.arange(2)
    width = 0.5

    bars = ax.bar(x, [b_max, c_max], width,
                  color=colors, edgecolor=edgecolor, linewidth=1.5,
                  hatch=[hatches[0], hatches[1]])

    ax.set_ylabel('Iteration Count')
    ax.set_title('Maximum Iteration Where Flag Was Captured')
    ax.set_xticks(x)
    ax.set_xticklabels(['Baseline', 'CHAP'])

    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.annotate(f'{int(height)}',
                       xy=(bar.get_x() + bar.get_width() / 2, height),
                       ha='center', va='bottom',
                       fontsize=FONT_CONFIG['annotation_size'] + 1,
                       fontweight='bold')

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'fig5_max_iteration_{style_key}.pdf'))
    plt.close()


def generate_relay_triggers_figure(chap_analysis, output_dir, style_key, style_config):
    """Generate relay trigger distribution figure."""
    relay = chap_analysis.get('relay_metrics', {})
    auto = relay.get('auto_triggers', 0)
    manual = relay.get('manual_triggers', 0)

    if auto + manual == 0:
        return

    fig, ax = plt.subplots(figsize=FIG_CONFIG['pie_chart_size'])

    colors = style_config['colors']

    # Pie chart with improved styling
    wedges, texts, autotexts = ax.pie(
        [auto, manual],
        labels=[f'Auto-Triggered\n(n={auto})', f'Manual-Triggered\n(n={manual})'],
        autopct='%1.1f%%',
        colors=colors,
        startangle=90,
        explode=(0.02, 0.02),
        wedgeprops={'edgecolor': 'white', 'linewidth': 2},
        textprops={'fontsize': FONT_CONFIG['legend_size']},
    )

    # Style the percentage text
    for autotext in autotexts:
        autotext.set_fontsize(FONT_CONFIG['annotation_size'] + 1)
        autotext.set_fontweight('bold')

    ax.set_title('CHAP Relay Trigger Distribution', fontsize=FONT_CONFIG['title_size'],
                 fontweight=FONT_CONFIG['title_weight'])

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'fig6_relay_triggers_{style_key}.pdf'))
    plt.close()


def generate_combined_overview_figure(baseline_analysis, chap_analysis, output_dir, style_key, style_config):
    """Generate a combined 2x2 overview figure."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 11))

    colors = style_config['colors']
    edgecolor = style_config['edgecolor']
    hatches = style_config['hatch']
    width = FIG_CONFIG['bar_width']

    # Panel A: Success Rate
    ax = axes[0, 0]
    b_rates = [r['success']['rate'] * 100 for r in baseline_analysis['per_run']]
    c_rates = [r['success']['rate'] * 100 for r in chap_analysis['per_run']]
    max_runs = max(len(b_rates), len(c_rates), 1)
    b_rates_padded = b_rates + [0] * (max_runs - len(b_rates))
    c_rates_padded = c_rates + [0] * (max_runs - len(c_rates))

    x = np.arange(max_runs)
    ax.bar(x - width/2 - 0.02, b_rates_padded, width, label='Baseline',
           color=colors[0], edgecolor=edgecolor, linewidth=1.2, hatch=hatches[0])
    ax.bar(x + width/2 + 0.02, c_rates_padded, width, label='CHAP',
           color=colors[1], edgecolor=edgecolor, linewidth=1.2, hatch=hatches[1])
    ax.set_ylabel('Success Rate (%)')
    ax.set_xlabel('Run')
    ax.set_title('(A) Success Rate by Run')
    ax.set_xticks(x)
    ax.set_xticklabels([f'Run {i+1}' for i in range(max_runs)])
    ax.set_ylim(0, 100)
    ax.legend(loc='upper right', framealpha=0.9)

    # Panel B: Pass@k
    ax = axes[0, 1]
    max_k = max(len(baseline_analysis['per_run']), len(chap_analysis['per_run']), 1)
    ks = list(range(1, max_k + 1))
    b_pass = [baseline_analysis['pass_at_k'].get(k, {}).get('rate', 0) * 100 for k in ks]
    c_pass = [chap_analysis['pass_at_k'].get(k, {}).get('rate', 0) * 100 for k in ks]

    x = np.arange(len(ks))
    ax.bar(x - width/2 - 0.02, b_pass, width, label='Baseline',
           color=colors[0], edgecolor=edgecolor, linewidth=1.2, hatch=hatches[0])
    ax.bar(x + width/2 + 0.02, c_pass, width, label='CHAP',
           color=colors[1], edgecolor=edgecolor, linewidth=1.2, hatch=hatches[1])
    ax.set_ylabel('Pass Rate (%)')
    ax.set_xlabel('k')
    ax.set_title('(B) Pass@k Comparison')
    ax.set_xticks(x)
    ax.set_xticklabels([f'@{k}' for k in ks])
    ax.set_ylim(0, 100)
    ax.legend(loc='upper left', framealpha=0.9)

    # Panel C: Cost Comparison
    ax = axes[1, 0]
    b_cost = baseline_analysis['averages']['cost']
    c_cost = chap_analysis['averages']['cost']
    b_vals = [b_cost.get('avg_per_challenge', 0) or 0, b_cost.get('avg_per_successful', 0) or 0,
              b_cost.get('avg_per_unsuccessful', 0) or 0]
    c_vals = [c_cost.get('avg_per_challenge', 0) or 0, c_cost.get('avg_per_successful', 0) or 0,
              c_cost.get('avg_per_unsuccessful', 0) or 0]

    x = np.arange(3)
    ax.bar(x - width/2 - 0.02, b_vals, width, label='Baseline',
           color=colors[0], edgecolor=edgecolor, linewidth=1.2, hatch=hatches[0])
    ax.bar(x + width/2 + 0.02, c_vals, width, label='CHAP',
           color=colors[1], edgecolor=edgecolor, linewidth=1.2, hatch=hatches[1])
    ax.set_ylabel('Average Cost ($)')
    ax.set_xlabel('Category')
    ax.set_title('(C) Cost by Outcome')
    ax.set_xticks(x)
    ax.set_xticklabels(['All', 'Success', 'Fail'])
    ax.legend(loc='upper right', framealpha=0.9)

    # Panel D: Iterations Comparison
    ax = axes[1, 1]
    b_iter = baseline_analysis['averages']['iterations']
    c_iter = chap_analysis['averages']['iterations']
    b_vals = [b_iter.get('avg_per_challenge', 0) or 0, b_iter.get('avg_per_successful', 0) or 0,
              b_iter.get('avg_per_unsuccessful', 0) or 0]
    c_vals = [c_iter.get('avg_per_challenge', 0) or 0, c_iter.get('avg_per_successful', 0) or 0,
              c_iter.get('avg_per_unsuccessful', 0) or 0]

    x = np.arange(3)
    ax.bar(x - width/2 - 0.02, b_vals, width, label='Baseline',
           color=colors[0], edgecolor=edgecolor, linewidth=1.2, hatch=hatches[0])
    ax.bar(x + width/2 + 0.02, c_vals, width, label='CHAP',
           color=colors[1], edgecolor=edgecolor, linewidth=1.2, hatch=hatches[1])
    ax.set_ylabel('Average Iterations')
    ax.set_xlabel('Category')
    ax.set_title('(D) Iterations by Outcome')
    ax.set_xticks(x)
    ax.set_xticklabels(['All', 'Success', 'Fail'])
    ax.legend(loc='upper right', framealpha=0.9)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'fig_combined_overview_{style_key}.pdf'))
    plt.close()


def generate_all_figures(baseline_analysis, chap_analysis, output_dir):
    """Generate all figures in all style variations."""
    if not MATPLOTLIB_AVAILABLE or not NUMPY_AVAILABLE:
        print("Skipping figure generation (matplotlib/numpy not available)")
        return

    os.makedirs(output_dir, exist_ok=True)
    setup_figure_style()

    print(f"\nGenerating figures in {len(STYLE_CONFIGS)} style variations...")

    for style_key, style_config in STYLE_CONFIGS.items():
        print(f"  Generating {style_config['name']} ({style_key})...")

        # Individual figures
        generate_success_rate_figure(baseline_analysis, chap_analysis, output_dir, style_key, style_config)
        generate_pass_at_k_figure(baseline_analysis, chap_analysis, output_dir, style_key, style_config)
        generate_cost_comparison_figure(baseline_analysis, chap_analysis, output_dir, style_key, style_config)
        generate_max_iteration_figure(baseline_analysis, chap_analysis, output_dir, style_key, style_config)
        generate_relay_triggers_figure(chap_analysis, output_dir, style_key, style_config)

    print(f"\nAll figures saved to {output_dir}/")
    print("\nStyle variations generated:")
    for style_key, style_config in STYLE_CONFIGS.items():
        print(f"  - {style_key}: {style_config['description']}")


# ============== MAIN ==============

def main():
    parser = argparse.ArgumentParser(description='Generate publication-quality figures for CTF benchmark analysis')
    parser.add_argument('--runs', type=int, default=None,
                       help='Number of runs to include per method (default: all)')
    parser.add_argument('--output-dir', type=str, default='analysis_results/publication_figures',
                       help='Output directory (default: analysis_results/publication_figures)')
    args = parser.parse_args()

    output_dir = args.output_dir
    max_runs = args.runs

    print("=" * 60)
    print("Publication Quality Figure Generator")
    print("=" * 60)

    # Discover experiments
    print("\nDiscovering experiments...")
    experiments = discover_experiments("results")

    if max_runs is not None:
        experiments['baseline'] = experiments['baseline'][:max_runs]
        experiments['chap'] = experiments['chap'][:max_runs]
        print(f"Limiting to first {max_runs} runs per method")

    print(f"Found {len(experiments['baseline'])} baseline runs")
    print(f"Found {len(experiments['chap'])} CHAP runs")

    if not experiments['baseline'] and not experiments['chap']:
        print("\nNo experiments found!")
        return

    # Load experiments
    print("\nLoading experiment data...")
    baseline_data = [load_experiment(p) for p in experiments['baseline']]
    chap_data = [load_experiment(p) for p in experiments['chap']]

    # Analyze
    print("\nAnalyzing data...")
    baseline_analysis = analyze_method(baseline_data) if baseline_data else {
        'per_run': [], 'pass_at_k': {},
        'averages': {'cost': {}, 'iterations': {}}
    }

    chap_analysis = analyze_method(chap_data) if chap_data else {
        'per_run': [], 'pass_at_k': {},
        'averages': {'cost': {}, 'iterations': {}}
    }

    if chap_data:
        chap_analysis['relay_metrics'] = calculate_relay_metrics(chap_data)
    else:
        chap_analysis['relay_metrics'] = {}

    # Generate figures
    os.makedirs(output_dir, exist_ok=True)
    generate_all_figures(baseline_analysis, chap_analysis, output_dir)

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
