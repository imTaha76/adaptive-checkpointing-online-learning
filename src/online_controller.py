
import csv
from pathlib import Path
from datetime import datetime, timezone

try:
    from .csv_utils import append_csv_row
except ImportError:
    from csv_utils import append_csv_row

try:
    from .online_model import OnlineTransferPredictor
except ImportError:
    from online_model import OnlineTransferPredictor


RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
PREDICTIONS_FILE = RESULTS_DIR / "online_predictions_v1.csv"

PREDICTION_FIELDS = [
    "timestamp",
    "run_id",
    "worker_id",
    "checkpoint_interval",
    "file_size_bytes",
    "local_save_time_seconds",
    "previous_transfer_time_seconds",
    "previous_throughput_mbps",
    "observations_before_update",
    "predicted_transfer_time_seconds",
    "actual_transfer_time_seconds",
    "absolute_error_seconds",
    "squared_error_seconds"
]


class OnlineLearningController:

    def __init__(
        self,
        initial_interval=100_000,
        min_interval=50_000,
        max_interval=400_000,
        failure_rate_per_second=1 / 3600
    ):

        if min_interval <= 0 or max_interval < min_interval:
            raise ValueError("Invalid checkpoint interval limits")

        self.min_interval = min_interval
        self.max_interval = max_interval

        self.interval = min(
            max(initial_interval, min_interval),
            max_interval
        )

        # Assumption: one failure per hour by default.
        # This is configurable, not a measured failure rate.
        if failure_rate_per_second < 0:
            raise ValueError("Failure rate cannot be negative")

        self.failure_rate = failure_rate_per_second

        self.predictor = OnlineTransferPredictor()

        self.previous_transfer_time = 0.0
        self.previous_throughput = 0.0

        self.observations = 0

    def predict_transfer_time(
        self,
        file_size_bytes,
        local_save_time
    ):
        return self.predictor.predict(
            file_size_bytes=file_size_bytes,
            local_save_time=local_save_time,
            previous_transfer_time=self.previous_transfer_time,
            previous_throughput=self.previous_throughput
        )

    def log_prediction(
        self,
        run_id,
        worker_id,
        checkpoint_interval,
        file_size_bytes,
        local_save_time,
        predicted_transfer_time,
        actual_transfer_time
    ):

        observations_before_update = self.observations

        if predicted_transfer_time is not None:
            absolute_error = abs(
                predicted_transfer_time - actual_transfer_time
            )
            squared_error = absolute_error ** 2
        else:
            absolute_error = ""
            squared_error = ""

        append_csv_row(PREDICTIONS_FILE, PREDICTION_FIELDS, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "worker_id": worker_id,
            "checkpoint_interval": checkpoint_interval,
            "file_size_bytes": file_size_bytes,
            "local_save_time_seconds": local_save_time,
            "previous_transfer_time_seconds": self.previous_transfer_time,
            "previous_throughput_mbps": self.previous_throughput,
            "observations_before_update": observations_before_update,
            "predicted_transfer_time_seconds": (
                predicted_transfer_time
                if predicted_transfer_time is not None
                else ""
            ),
            "actual_transfer_time_seconds": actual_transfer_time,
            "absolute_error_seconds": absolute_error,
            "squared_error_seconds": squared_error
        })

        if predicted_transfer_time is not None:
            print(
                f"[ONLINE ML] Predicted: {predicted_transfer_time:.6f}s "
                f"| Actual: {actual_transfer_time:.6f}s "
                f"| Absolute error: {absolute_error:.6f}s",
                flush=True
            )
        else:
            print(
                "[ONLINE ML] Prediction unavailable; "
                "collecting initial observations",
                flush=True
            )

    def record_observation(
        self,
        file_size_bytes,
        local_save_time,
        transfer_time,
        throughput,
        checkpoint_interval,
        predicted_transfer_time=None,
        run_id=None,
        worker_id=None
    ):

        if transfer_time is None or transfer_time < 0:
            return

        # Log prediction before training on this observation.
        self.log_prediction(
            run_id=run_id,
            worker_id=worker_id,
            checkpoint_interval=checkpoint_interval,
            file_size_bytes=file_size_bytes,
            local_save_time=local_save_time,
            predicted_transfer_time=predicted_transfer_time,
            actual_transfer_time=transfer_time
        )

        # Update model using the newly observed transfer.
        self.predictor.update(
            file_size_bytes=file_size_bytes,
            local_save_time=local_save_time,
            previous_transfer_time=self.previous_transfer_time,
            previous_throughput=self.previous_throughput,
            actual_transfer_time=transfer_time
        )

        self.previous_transfer_time = transfer_time
        self.previous_throughput = throughput or 0.0

        self.observations += 1

    def choose_interval(
        self,
        current_file_size,
        local_save_time,
        iterations_per_second
    ):

        if self.observations < 5:
            return self.interval

        if iterations_per_second <= 0:
            return self.interval

        # Candidate intervals are bounded and unique.
        candidates = sorted(set([
            self.min_interval,
            min(max(100_000, self.min_interval), self.max_interval),
            min(max(200_000, self.min_interval), self.max_interval),
            self.max_interval
        ]))

        best_interval = self.interval
        best_cost = float("inf")

        predicted_transfer = self.predictor.predict(
            file_size_bytes=current_file_size,
            local_save_time=local_save_time,
            previous_transfer_time=self.previous_transfer_time,
            previous_throughput=self.previous_throughput
        )

        if predicted_transfer is None:
            return self.interval

        checkpoint_cost = local_save_time + predicted_transfer

        for candidate in candidates:

            interval_seconds = (
                candidate / iterations_per_second
            )

            # Young-style approximate checkpoint overhead.
            overhead = (
                checkpoint_cost / interval_seconds
                + self.failure_rate * interval_seconds / 2
            )

            if overhead < best_cost:
                best_cost = overhead
                best_interval = candidate
                print(
            f"[ONLINE ML DEBUG] Predicted transfer: "
            f"{predicted_transfer:.6f}s | "
            f"Save: {local_save_time:.6f}s | "
            f"Compute rate: {iterations_per_second:.2f} iter/s",
            flush=True
        )

        for candidate in candidates:
            interval_seconds = candidate / iterations_per_second
            overhead = (
                checkpoint_cost / interval_seconds
                + self.failure_rate * interval_seconds / 2
            )
            print(
                f"[ONLINE ML DEBUG] Candidate: {candidate} | "
                f"Interval time: {interval_seconds:.4f}s | "
                f"Estimated overhead: {overhead:.8f}",
                flush=True
            )

        print(
            f"[ONLINE ML DEBUG] Selected interval: {best_interval}",
            flush=True
        )
        old_interval = self.interval
        self.interval = best_interval

        if old_interval != best_interval:
            print(
                f"[ONLINE ML] Interval adapted: "
                f"{old_interval} -> {best_interval}",
                flush=True
            )

        return self.interval
