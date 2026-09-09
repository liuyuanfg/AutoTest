"""
Application path utilities for PyInstaller compatibility.
"""
import os
import sys


def get_app_dir() -> str:
    """Return the directory containing the application (script or frozen exe)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_config_path(name: str = "config.yaml") -> str:
    """Return the default config file path in the app directory."""
    return os.path.join(get_app_dir(), name)


def get_output_dir(subdir: str = "reports") -> str:
    """Return output directory path (absolute, relative to app dir)."""
    return os.path.join(get_app_dir(), subdir)
