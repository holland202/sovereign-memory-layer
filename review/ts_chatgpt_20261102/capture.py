#!/usr/bin/env python3
"""Save an exact command, separate raw streams, exit status, and elapsed time."""
import json
import subprocess
import sys
import time
from pathlib import Path

label, *command = sys.argv[1:]
out = Path(__file__).resolve().parent / "raw"
out.mkdir(exist_ok=True)
start = time.time()
metadata = {"command": command, "cwd": str(Path.cwd()), "started_unix": start}
with (out / f"{label}.stdout").open("wb") as stdout, (out / f"{label}.stderr").open("wb") as stderr:
    try:
        result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=1200)
        metadata["exit_code"] = result.returncode
    except Exception as exc:
        metadata.update(exit_code=None, runner_error=f"{type(exc).__name__}: {exc}")
metadata["elapsed_seconds"] = time.time() - start
(out / f"{label}.command.json").write_text(json.dumps(metadata, indent=2) + "\n")
print(json.dumps(metadata), flush=True)
print((out / f"{label}.stdout").read_text(errors="backslashreplace"), end="", flush=True)
sys.exit(metadata["exit_code"] if metadata["exit_code"] is not None else 2)
