#!/usr/bin/env python3
"""Start the Docker network for CTF experiments."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.experiment_utils.start_network import start_network

if __name__ == "__main__":
    print("🌐 Starting Docker network...")
    start_network()
    print("✅ Network ready!")
