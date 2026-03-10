#!/usr/bin/env python3
"""Entry point for the Job Application Assistant bot."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

from src.bot.app import run_bot

if __name__ == "__main__":
    run_bot()
