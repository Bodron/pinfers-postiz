"""Versioned timing, with transitions included in each scene's interval."""
import json
from pathlib import Path

VERSION='2.2-2.2-4-v1'
DURATIONS=[2.2,2.2,4.0]

def current(folder):
    folder=Path(folder)
    try:
        return (folder/'clip.mp4').exists() and json.loads((folder/'motion-version.json').read_text()).get('version')==VERSION
    except (OSError,ValueError):return False
