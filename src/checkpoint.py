
import csv
import time
import json
import os

from datetime import datetime, timezone
from pathlib import Path
try:
    from .csv_utils import append_csv_row
except ImportError:
    from csv_utils import append_csv_row

try:
    from .network_transfer import transfer_checkpoint
except ImportError:
    from network_transfer import transfer_checkpoint


CHECKPOINT_DIR = Path("checkpoints")
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
EVENTS_FILE = RESULTS_DIR / "checkpoint_events_v2.csv"


def log_checkpoint_event(
    run_id,
    strategy,
    worker_id,
    completed_until,
    checkpoint_interval,
    payload_size_bytes,
    file_size,
    save_time
):
    fields = [
        "timestamp",
        "run_id",
        "strategy",
        "worker_id",
        "completed_until",
        "checkpoint_interval",
        "payload_size_bytes",
        "file_size_bytes",
        "local_save_time_seconds"
    ]

    append_csv_row(EVENTS_FILE, fields, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "strategy": strategy,
        "worker_id": worker_id,
        "completed_until": completed_until,
        "checkpoint_interval": checkpoint_interval,
        "payload_size_bytes": payload_size_bytes,
        "file_size_bytes": file_size,
        "local_save_time_seconds": f"{save_time:.9f}"
    })

def save_checkpoint(
    worker_id,
    completed_until,
    result,
    task_size,
    run_id,
    strategy,
    checkpoint_interval,
    prediction_callback=None
):
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    payload_size_bytes = int(
        os.environ.get("CHECKPOINT_PAYLOAD_BYTES", "0")
    )

    if payload_size_bytes < 0:
        raise ValueError("Checkpoint payload size cannot be negative")

    checkpoint_data = {
        "worker_id": worker_id,
        "completed_until": completed_until,
        "result": result,
        "task_size": task_size,
        "synthetic_payload": "A" * payload_size_bytes,
        "synthetic_payload_bytes": payload_size_bytes
    }

    checkpoint_path = CHECKPOINT_DIR / f"worker_{worker_id}.json"
    temporary_path = checkpoint_path.with_suffix(".tmp")

    save_start = time.perf_counter()

    with open(temporary_path, "w") as file:
        json.dump(checkpoint_data, file, indent=4)
        file.flush()
        os.fsync(file.fileno())

    os.replace(temporary_path, checkpoint_path)

    save_time = time.perf_counter() - save_start
    file_size = checkpoint_path.stat().st_size

    log_checkpoint_event(
        run_id,
        strategy,
        worker_id,
        completed_until,
        checkpoint_interval,
        payload_size_bytes,
        file_size,
        save_time
    )

    print(
        f"[Worker {worker_id}] Local save time: {save_time:.6f}s",
        flush=True
    )

    print(
        f"[Worker {worker_id}] Local checkpoint saved "
        f"at iteration {completed_until}",
        flush=True
    )

    predicted_transfer_time = None

    # Predict before the network transfer takes place.
    if prediction_callback is not None:
        try:
            predicted_transfer_time = prediction_callback(
                file_size,
                save_time
            )

        except Exception as error:
            print(
                f"[Worker {worker_id}] Prediction failed: {error}",
                flush=True
            )

    transfer_metrics = None

    try:
        transfer_metrics = transfer_checkpoint(
            checkpoint_path,
            run_id,
            strategy,
            checkpoint_interval,
            save_time
        )

        print(
            f"[Worker {worker_id}] Network transfer successful",
            flush=True
        )

    except Exception as error:
        print(
            f"[Worker {worker_id}] Network transfer failed: {error}",
            flush=True
        )

    if transfer_metrics is not None:
        transfer_metrics["local_save_time_seconds"] = save_time
        transfer_metrics["predicted_transfer_time_seconds"] = (
            predicted_transfer_time
        )

    return transfer_metrics


def load_checkpoint(worker_id, task_size):

    checkpoint_path = CHECKPOINT_DIR / f"worker_{worker_id}.json"

    if not checkpoint_path.exists():
        return None

    with open(checkpoint_path, "r") as file:
        data = json.load(file)

    if data["worker_id"] != worker_id:
        raise ValueError("Checkpoint worker ID mismatch")

    if data["task_size"] != task_size:
        raise ValueError("Checkpoint task size mismatch")

    completed_until = data["completed_until"]

    if not isinstance(completed_until, int) or not (
        0 <= completed_until <= task_size
    ):
        raise ValueError("Invalid checkpoint progress")

    return data
