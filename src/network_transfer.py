
import os
import subprocess
import csv
import json
try:
    from .csv_utils import append_csv_row
except ImportError:
    from csv_utils import append_csv_row
from pathlib import Path
from datetime import datetime, timezone


SENDER = Path("/home/tahan/network-test/sender.py")

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_DIR / "results"

CSV_FILE = RESULTS_DIR / "network_transfers_v2.csv"

FIELDS = [
    "timestamp",
    "run_id",
    "strategy",
    "network_profile",
    "worker_id",
    "completed_until",
    "checkpoint_interval",
    "payload_size_bytes",
    "file_size_bytes",
    "local_save_time_seconds",
    "transfer_time_seconds",
    "throughput_mbps",
    "sha256",
    "status",
    "error"
]


def log_transfer(record):
    append_csv_row(CSV_FILE, FIELDS, record)


def transfer_checkpoint(
    checkpoint_path,
    run_id,
    strategy,
    checkpoint_interval,
    local_save_time
):
    checkpoint_path = Path(checkpoint_path)

    if not checkpoint_path.is_file():
        raise FileNotFoundError(checkpoint_path)

    with checkpoint_path.open("r") as file:
        checkpoint_data = json.load(file)

    worker_id = checkpoint_data["worker_id"]
    completed_until = checkpoint_data["completed_until"]

    payload_size_bytes = checkpoint_data.get(
        "synthetic_payload_bytes", 0
    )

    file_size = checkpoint_path.stat().st_size

    command = [
        "sudo", "-n",
        "ip", "netns", "exec", "worker",
        "python3", str(SENDER),
        str(checkpoint_path.resolve())
    ]

    print(
        f"[NETWORK] Transferring {checkpoint_path.name}...",
        flush=True
    )

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    print(completed.stdout, end="", flush=True)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "strategy": strategy,
        "network_profile": os.getenv(
            "CHECKPOINT_NETWORK_PROFILE",
            "unspecified"
        ),
        "worker_id": worker_id,
        "completed_until": completed_until,
        "checkpoint_interval": checkpoint_interval,
        "payload_size_bytes": payload_size_bytes,
        "file_size_bytes": file_size,
        "local_save_time_seconds": f"{local_save_time:.9f}",
        "transfer_time_seconds": "",
        "throughput_mbps": "",
        "sha256": "",
        "status": "failed",
        "error": ""
    }

    if completed.returncode != 0:
        record["error"] = completed.stderr.strip()
        log_transfer(record)

        raise RuntimeError(
            f"Transfer command failed:\n{completed.stderr}"
        )

    for line in completed.stdout.splitlines():

        if line.startswith("Time:"):
            record["transfer_time_seconds"] = (
                line.split(":", 1)[1].strip().split()[0]
            )

        elif line.startswith("Throughput:"):
            record["throughput_mbps"] = (
                line.split(":", 1)[1].strip().split()[0]
            )

        elif line.startswith("SHA-256:"):
            record["sha256"] = (
                line.split(":", 1)[1].strip()
            )

    if (
        not record["transfer_time_seconds"]
        or not record["sha256"]
    ):
        record["error"] = "Could not parse sender measurements"
        log_transfer(record)

        raise RuntimeError(record["error"])

    record["status"] = "success"
    log_transfer(record)

    return {
        "transfer_time_seconds": float(
            record["transfer_time_seconds"]
        ),
        "throughput_mbps": float(record["throughput_mbps"]),
        "file_size_bytes": file_size,
        "sha256": record["sha256"]
    }
