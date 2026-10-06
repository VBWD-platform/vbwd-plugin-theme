"""Test fixtures for the theme plugin.

Puts vbwd-backend on ``sys.path`` and selects the testing environment, as every
plugin conftest does. The plugin owns no tables (S152 D9), so no database
fixtures are defined until a slice needs one.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

os.environ["FLASK_ENV"] = "testing"
os.environ["TESTING"] = "true"
