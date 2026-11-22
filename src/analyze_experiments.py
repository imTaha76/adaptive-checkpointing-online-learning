import csv
import re
import statistics
from pathlib import Path
from collections import defaultdict

RESULTS = Path("results")
LOG_DIR = RESULTS / "experiment_logs"

def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def average(values):
    return statistics.mean(values) if values else 0.0

def safe_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

# Load raw records.
checkpoints = read_csv(RESULTS / "checkpoint_events_v2.csv")
transfers = read_csv(RESULTS / "network_transfers_v2.csv")
predictions = read_csv(RESULTS / "online_predictions_v1.csv")

# Index records by run ID.
checkpoint_index = defaultdict(list)
transfer_index = defaultdict(list)
prediction_index = defaultdict(list)

for row in checkpoints:
    if row.get("payload_size_bytes") == "1000000":
        checkpoint_index[row["run_id"]].append(row)

for row in transfers:
    if row.get("payload_size_bytes") == "1000000":
        transfer_index[row["run_id"]].append(row)

for row in predictions:
    prediction_index[row["run_id"]].append(row)

# Extract only the FINAL concurrent experiment batch.
FINAL_TAG = "20261122_123057_seed20261122"

runs = []

for log in sorted(LOG_DIR.glob(f"{FINAL_TAG}_*.log")):
    match = re.match(r"(.+)_trial(\d+)\.log$", log.name)

    if not match:
        continue

    prefix = match.group(1)
    trial = int(match.group(2))

    prefix = prefix.removeprefix(FINAL_TAG + "_")

    strategy = None
    profile = None

    for candidate in ["online-learning", "rule-based", "fixed"]:
        suffix = "_" + candidate
        if prefix.endswith(suffix):
            profile = prefix[:-len(suffix)]
            strategy = candidate
            break

    if strategy is None or profile not in ["normal", "congested", "unstable"]:
        print("WARNING: Cannot identify experiment:", log.name)
        continue

    content = log.read_text(errors="replace")

    run_match = re.search(r"Run ID:\s*([a-f0-9]+)", content)
    time_match = re.search(r"Total time:\s*([\d.]+)s", content)
    restart_match = re.search(r"Workers restarted:\s*(\d+)", content)

    if not run_match or not time_match:
        print("WARNING: Missing run ID or runtime:", log.name)
        continue

    run_id = run_match.group(1)

    cp = checkpoint_index[run_id]
    tr = transfer_index[run_id]
    pr = prediction_index[run_id]

    transfer_times = [
        safe_float(r["transfer_time_seconds"]) for r in tr
    ]
    transfer_times = [v for v in transfer_times if v is not None]

    save_times = [
        safe_float(r["local_save_time_seconds"]) for r in cp
    ]
    save_times = [v for v in save_times if v is not None]

    throughputs = [
        safe_float(r["throughput_mbps"]) for r in tr
    ]
    throughputs = [v for v in throughputs if v is not None]

    errors = [
        safe_float(r["absolute_error_seconds"]) for r in pr
    ]
    errors = [v for v in errors if v is not None]

    success_count = sum(r["status"] == "success" for r in tr)

    runs.append({
        "profile": profile,
        "strategy": strategy,
        "trial": trial,
        "run_id": run_id,
        "execution_time_seconds": float(time_match.group(1)),
        "workers_restarted": int(restart_match.group(1)) if restart_match else "",
        "checkpoint_count": len(cp),
        "transfer_count": len(tr),
        "successful_transfers": success_count,
        "failed_transfers": len(tr) - success_count,
        "success_rate_percent": 100 * success_count / len(tr) if tr else 0,
        "avg_local_save_time_seconds": average(save_times),
        "avg_transfer_time_seconds": average(transfer_times),
        "avg_throughput_mbps": average(throughputs),
        "evaluated_predictions": len(errors),
        "prediction_mae_seconds": average(errors) if errors else "",
    })

# Validate that exactly 45 trials were extracted.
print("Experiment runs extracted:", len(runs))

if len(runs) != 45:
    raise SystemExit("Expected 45 runs. Stop and investigate before analysis.")

# Save per-run dataset.
fields = list(runs[0].keys())

with open(RESULTS / "experiment_run_summary.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(runs)

# Aggregate by network profile and strategy.
groups = defaultdict(list)

for run in runs:
    groups[(run["profile"], run["strategy"])].append(run)

summary = []

metrics = [
    "execution_time_seconds",
    "checkpoint_count",
    "avg_local_save_time_seconds",
    "avg_transfer_time_seconds",
    "avg_throughput_mbps",
    "success_rate_percent",
    "prediction_mae_seconds",
]

for (profile, strategy), group in sorted(groups.items()):
    row = {
        "profile": profile,
        "strategy": strategy,
        "trials": len(group),
    }

    for metric in metrics:
        values = [
            safe_float(r[metric])
            for r in group
        ]
        values = [v for v in values if v is not None]

        if metric == "prediction_mae_seconds" and strategy != "online-learning":
            row[metric + "_mean"] = "N/A"
            row[metric + "_std"] = "N/A"
        elif not values:
            row[metric + "_mean"] = "N/A"
            row[metric + "_std"] = "N/A"
        else:
            row[metric + "_mean"] = average(values)
            row[metric + "_std"] = (
                statistics.stdev(values) if len(values) > 1 else 0
            )

    summary.append(row)

with open(RESULTS / "experiment_aggregate_summary.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
    writer.writeheader()
    writer.writerows(summary)

print("\n========== AGGREGATE RESULTS ==========")

for row in summary:
    print(
        f"\n{row['profile']} | {row['strategy']} "
        f"| Trials: {row['trials']}"
    )

    for metric in metrics:
        mean_value = row[metric + "_mean"]
        std_value = row[metric + "_std"]

        if isinstance(mean_value, (int, float)):
            print(
                f"{metric}: "
                f"{mean_value:.6f} "
                f"+/- {std_value:.6f}"
            )
        else:
            print(f"{metric}: N/A")

print("\n========== VALIDATION ==========")
print("Total runs:", len(runs))
print("Unique run IDs:", len(set(r["run_id"] for r in runs)))
print("Total checkpoints:", sum(r["checkpoint_count"] for r in runs))
print("Total transfers:", sum(r["transfer_count"] for r in runs))
print("Failed transfers:", sum(r["failed_transfers"] for r in runs))

print("\nCreated:")
print("results/experiment_run_summary.csv")
print("results/experiment_aggregate_summary.csv")
