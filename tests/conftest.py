"""
tests/conftest.py – pytest configuration and shared fixtures.
Adds the project root (parent of tests/) to sys.path so imports work.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
