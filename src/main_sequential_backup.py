
import multiprocessing as mp
import argparse
import shutil
import uuid
import time
import os

from online_controller import OnlineLearningController
from controller import RuleBasedController
from checkpoint import save_checkpoint, load_checkpoint


NUMBER_OF_WORKERS = 3
TASK_SIZE = 1_000_000


def worker(
    worker_id,
    result_queue,
    resume,
    checkpoint_interval,
    strategy="fixed",
    run_id=None,
    crash_worker=None,
    crash_after=None
):

    checkpoint = load_checkpoint(worker_id, TASK_SIZE) if resume else None

    if checkpoint:
        completed_until = checkpoint["completed_until"]
        result = checkpoint["result"]

        print(
            f"[Worker {worker_id}] Recovering from iteration "
            f"{completed_until}",
            flush=True
        )
    else:
        completed_until = 0
        result = 0

        print(
            f"[Worker {worker_id}] Starting fresh",
            flush=True
        )

    controller = None

    if strategy == "rule-based":
        controller = RuleBasedController(
            initial_interval=checkpoint_interval
        )

        print(
            f"[Worker {worker_id}] Rule-based controller enabled",
            flush=True
        )

    elif strategy == "online-learning":
        controller = OnlineLearningController(
            initial_interval=checkpoint_interval
        )

        print(
            f"[Worker {worker_id}] Online learning controller enabled",
            flush=True
        )

    start_time = time.perf_counter()

    compute_window_start = time.perf_counter()
    last_checkpoint_iteration = completed_until

    next_checkpoint = (
        (completed_until // checkpoint_interval) + 1
    ) * checkpoint_interval

    for i in range(completed_until + 1, TASK_SIZE + 1):

        result += (i * i) % 97
        completed_until = i

        if i >= next_checkpoint or i == TASK_SIZE:

            compute_duration = (
                time.perf_counter() - compute_window_start
            )

            iterations_since_checkpoint = (
                i - last_checkpoint_iteration
            )

            iterations_per_second = (
                iterations_since_checkpoint / compute_duration
                if compute_duration > 0
                else 0
            )

            # Predict using only earlier observations.
            prediction_callback = None

            if strategy == "online-learning":

                prediction_callback = (
                    lambda file_size, save_time:
                    controller.predict_transfer_time(
                        file_size,
                        save_time
                    )
                )

            # Save locally, predict, then transfer.
            transfer_metrics = save_checkpoint(
                worker_id,
                completed_until,
                result,
                TASK_SIZE,
                run_id,
                strategy,
                checkpoint_interval,
                prediction_callback=prediction_callback
            )

            # Rule-based adaptation.
            if strategy == "rule-based":

                transfer_time = (
                    transfer_metrics["transfer_time_seconds"]
                    if transfer_metrics is not None
                    else None
                )

                old_interval = checkpoint_interval

                checkpoint_interval = controller.update(
                    transfer_time=transfer_time
                )

                if checkpoint_interval != old_interval:
                    print(
                        f"[Worker {worker_id}] Adaptive interval: "
                        f"{old_interval} -> {checkpoint_interval}",
                        flush=True
                    )

            # Online-learning adaptation.
            elif strategy == "online-learning":

                if transfer_metrics is not None:

                    controller.record_observation(
                        file_size_bytes=transfer_metrics[
                            "file_size_bytes"
                        ],
                        local_save_time=transfer_metrics[
                            "local_save_time_seconds"
                        ],
                        transfer_time=transfer_metrics[
                            "transfer_time_seconds"
                        ],
                        throughput=transfer_metrics[
                            "throughput_mbps"
                        ],
                        checkpoint_interval=checkpoint_interval,
                        predicted_transfer_time=transfer_metrics.get(
                            "predicted_transfer_time_seconds"
                        ),
                        run_id=run_id,
                        worker_id=worker_id
                    )

                    old_interval = checkpoint_interval

                    checkpoint_interval = controller.choose_interval(
                        current_file_size=transfer_metrics[
                            "file_size_bytes"
                        ],
                        local_save_time=transfer_metrics[
                            "local_save_time_seconds"
                        ],
                        iterations_per_second=iterations_per_second
                    )

                    if checkpoint_interval != old_interval:
                        print(
                            f"[Worker {worker_id}] "
                            f"Online learning interval: "
                            f"{old_interval} -> {checkpoint_interval}",
                            flush=True
                        )

                else:
                    print(
                        f"[Worker {worker_id}] Online learning "
                        f"skipped: no successful transfer measurement",
                        flush=True
                    )

            last_checkpoint_iteration = i
            compute_window_start = time.perf_counter()

            next_checkpoint = i + checkpoint_interval

        # Deliberately terminate one worker for crash testing.
        if worker_id == crash_worker and crash_after == i:
            print(
                f"[Worker {worker_id}] SIMULATED CRASH "
                f"at iteration {i}!",
                flush=True
            )
            os._exit(1)

    elapsed = time.perf_counter() - start_time

    result_queue.put({
        "worker": worker_id,
        "status": "completed",
        "completed_until": completed_until,
        "result": result,
        "elapsed": elapsed
    })


def run_worker(
    worker_id,
    resume,
    checkpoint_interval,
    strategy="fixed",
    run_id=None,
    crash_worker=None,
    crash_after=None
):

    result_queue = mp.Queue()

    process = mp.Process(
        target=worker,
        args=(
            worker_id,
            result_queue,
            resume,
            checkpoint_interval,
            strategy,
            run_id,
            crash_worker,
            crash_after
        )
    )

    process.start()
    process.join()

    result = None

    if not result_queue.empty():
        result = result_queue.get()

    result_queue.close()
    result_queue.join_thread()

    return process.exitcode, result


def main():

    parser = argparse.ArgumentParser(
        description="Adaptive checkpointing and recovery"
    )

    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=100_000,
        help="Initial number of iterations between checkpoints"
    )

    parser.add_argument(
        "--payload-mb",
        type=float,
        default=0,
        help="Synthetic checkpoint payload size in MB (0 = no extra payload)"
    )

    parser.add_argument(
        "--strategy",
        choices=["fixed", "rule-based", "online-learning"],
        default="fixed",
        help="Checkpointing strategy"
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing checkpoints"
    )

    parser.add_argument(
        "--crash-worker",
        type=int,
        default=None,
        help="Worker number to crash"
    )

    parser.add_argument(
        "--crash-after",
        type=int,
        default=None,
        help="Iteration at which the selected worker crashes"
    )

    args = parser.parse_args()
    run_id = uuid.uuid4().hex

    if args.payload_mb < 0:
        parser.error("--payload-mb cannot be negative")

    payload_bytes = int(args.payload_mb * 1_000_000)
    os.environ["CHECKPOINT_PAYLOAD_BYTES"] = str(payload_bytes)

    if args.checkpoint_interval <= 0:
        parser.error("--checkpoint-interval must be positive")

    if args.reset:
        shutil.rmtree("checkpoints", ignore_errors=True)

    if (args.crash_worker is None) != (args.crash_after is None):
        parser.error(
            "--crash-worker and --crash-after must be used together"
        )

    if args.crash_worker is not None:

        if not 1 <= args.crash_worker <= NUMBER_OF_WORKERS:
            parser.error("Invalid worker number")

        if not 1 <= args.crash_after <= TASK_SIZE:
            parser.error("Invalid crash iteration")

    print("=" * 55)
    print("ADAPTIVE CHECKPOINTING - PHASE 4")
    print("=" * 55)

    print(f"Strategy: {args.strategy}")
    print(f"Initial interval: {args.checkpoint_interval}")
    print(f"Run ID: {run_id}")
    print(f"Payload size: {payload_bytes} bytes")

    total_start = time.perf_counter()
    failed_workers = []

    for worker_id in range(1, NUMBER_OF_WORKERS + 1):

        print(f"\nStarting Worker {worker_id}")

        crash_after = (
            args.crash_after
            if worker_id == args.crash_worker
            else None
        )

        exit_code, result = run_worker(
            worker_id,
            resume=False,
            checkpoint_interval=args.checkpoint_interval,
            strategy=args.strategy,
            run_id=run_id,
            crash_worker=args.crash_worker,
            crash_after=crash_after
        )

        if exit_code != 0:

            print(
                f"[Coordinator] Worker {worker_id} "
                f"failed with exit code {exit_code}"
            )

            failed_workers.append(worker_id)

        elif result:

            print(
                f"[Coordinator] Worker {worker_id} "
                f"completed successfully"
            )

    for worker_id in failed_workers:

        print(
            f"\n[Coordinator] Restarting Worker {worker_id}..."
        )

        exit_code, result = run_worker(
            worker_id,
            resume=True,
            checkpoint_interval=args.checkpoint_interval,
            strategy=args.strategy,
            run_id=run_id
        )

        if exit_code == 0 and result:

            print(
                f"[Coordinator] Worker {worker_id} "
                f"recovered successfully!"
            )

        else:

            print(
                f"[Coordinator] Worker {worker_id} "
                f"failed again."
            )

    total_time = time.perf_counter() - total_start

    print("\n" + "=" * 55)
    print("EXECUTION FINISHED")
    print(f"Strategy: {args.strategy}")
    print(f"Workers restarted: {len(failed_workers)}")
    print(f"Total time: {total_time:.2f}s")
    print("=" * 55)


if __name__ == "__main__":
    mp.freeze_support()
    main()
