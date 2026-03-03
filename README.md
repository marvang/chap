# Context Handoff for Autonomous Penetration Testing

This repo contains a research framework for agentic penetration testing. CHAP addresses context window limits in long-running autonomous security assessments through a relay mechanism that hands off compressed states to fresh agent instances.

📄 **[Read the paper](https://www.ndss-symposium.org/wp-content/uploads/lastx2026-42.pdf)**

If you use this work in your research, please cite:

```bibtex
@inproceedings{chap2026,
  title={Context Relay for Long-Running Penetration-Testing Agents}, 
  author={Vangeli, Marius and Brynielsson, Joel and Cohen, Mika and Kamrani, Farzad},
  booktitle={NDSS Workshop on LLM Assisted Security and Trust Exploration (LAST-X)},
  year={2026},
  url={https://dx.doi.org/10.14722/last-x.2026.23042},
  doi={10.14722/last-x.2026.23042}
}
```

## Overview

- **Agentic Framework** — LLM agents execute commands in a Kali Linux environment
- **CHAP** — Relay protocol that compresses context into handoff summaries for fresh agent instances
- **Benchmark** — Improved version of [AutoPenBench](https://github.com/lucagioacchini/auto-pen-bench) consisting of 11 CVE-based challenges 
- **Experiment Harness** — Cost, token, and performance tracking for reproducible research

## Quick Start
> Prerequisites: [uv](https://github.com/astral-sh/uv), [OpenRouter API key](https://openrouter.ai), Docker. Developed on macOS (Apple Silicon).
1. Clone and initialize repo:

```bash
git clone <repository-url>
cd chap
uv venv
source .venv/bin/activate
uv sync
```

2. Configure environment variables:
```bash
cp .env_example .env
```

3. Build Docker containers:
```bash
docker compose build
docker compose -f benchmark/machines/real-world/cve/docker-compose.yml build
```

4. Configure experiment parameters in `scripts/run_experiment.py`, then run:

```bash
python scripts/run_experiment.py
```



## Benchmark

11 real-world CVE challenges updated and improved from [AutoPenBench](https://github.com/lucagioacchini/auto-pen-bench). For details on changes made see our paper. Each runs in an isolated Docker container with a flag to capture. The benchmark can easily be extended by adding additional Docker containers.

| VM | CVE | CVSS | Description |
|----|-----|------|-------------|
| vm0 | CVE-2024-36401 | 9.8 | GeoServer RCE |
| vm1 | CVE-2024-23897 | 9.8 | Jenkins arbitrary file read |
| vm2 | CVE-2022-22965 | 9.8 | Spring4Shell |
| vm3 | CVE-2021-3156 | 7.8 | Baron Samedit (sudo) |
| vm4 | CVE-2021-42013 | 9.8 | Apache path traversal |
| vm5 | CVE-2021-43798 | 7.5 | Grafana directory traversal |
| vm6 | CVE-2021-25646 | 9.0 | Apache Druid RCE |
| vm7 | CVE-2021-44228 | 10.0 | Log4Shell |
| vm8 | CVE-2019-16113 | 8.8 | Bludit RCE |
| vm9 | CVE-2017-7494 | 10.0 | SambaCry |
| vm10 | CVE-2014-0160 | 7.5 | Heartbleed |


