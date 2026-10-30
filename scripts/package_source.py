"""Package only the audited committed source; exclude all private runtime files."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent.parent
output = root.parent / "OrderFlow-Sentinel-Source.zip"
subprocess.run(
    ["git", "archive", "--format=zip", "--prefix=orderflow-sentinel/", f"--output={output}", "HEAD"],
    cwd=root,
    check=True,
)
print(output)
print(f"{output.stat().st_size:,} bytes")
