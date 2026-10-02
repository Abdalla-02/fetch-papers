"""Run fetch_pdfs.py while asking Windows not to idle-sleep.

Usage: python keep_awake_run.py path\to\fetch_pdfs.py <fetch_pdfs arguments ...>

The request is released automatically when the process exits. It prevents idle
sleep only; closing a laptop lid or choosing Sleep still suspends the PC.
On other operating systems the script simply runs fetch_pdfs.py.
"""
import runpy
import sys

if sys.platform == "win32":
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)

script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name="__main__")
