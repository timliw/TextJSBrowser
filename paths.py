"""
Portable Camoufox binary discovery.

Finds the Camoufox executable on this machine so tbr doesn't hard-code a
path that only works for one developer's box. Resolution order:

  1. CAMOUFOX_BIN env var (explicit override)
  2. ~/.cache/camoufox/browsers/*/*/camoufox-bin   (normal install layout)
  3. Any camoufox-bin found under the user's camoufox cache dir

Returns the path or None; callers raise a clear error telling the user to
run `python -m camoufox fetch` if nothing is found.
"""
import glob
import os
from pathlib import Path


def find_camoufox_bin():
    """Return a path to the camoufox executable, or None if not found."""
    # 1. explicit override
    env = os.environ.get("CAMOUFOX_BIN")
    if env and os.path.exists(env):
        return env

    # 2. standard install layout
    candidates = glob.glob(
        os.path.expanduser("~/.cache/camoufox/browsers/*/*/camoufox-bin")
    )
    if candidates:
        return candidates[0]

    # 3. deeper / different cache location
    for root in (os.path.expanduser("~/.cache/camoufox"),
                 os.path.expanduser("~/.local/share/camoufox")):
        if os.path.isdir(root):
            deeper = glob.glob(os.path.join(root, "**", "camoufox-bin"),
                               recursive=True)
            if deeper:
                return deeper[0]

    return None


def require_camoufox_bin():
    """Return the Camoufox executable, raising a helpful error if missing."""
    p = find_camoufox_bin()
    if not p:
        raise RuntimeError(
            "Camoufox browser not found. Install it with:\n"
            "    python -m pip install camoufox\n"
            "    python -m camoufox fetch\n"
            "or point CAMOUFOX_BIN at your camoufox-bin executable."
        )
    return p
