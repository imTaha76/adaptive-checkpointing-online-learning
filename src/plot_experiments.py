
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = Path("results")
OUTPUT = RESULTS / "graphs"
OUTPUT.mkdir(parents=True, exist_ok=True)

with open(RESULTS / "experiment_aggregate_summary.csv", newline="") as f:
    rows = list(csv.DictReader(f))

def get_row(profile, strategy):
    for row in rows:
        if row["profile"] == profile and row["strategy"] == strategy:
            return row
    raise ValueError(f"Missing data: {profile}, {strategy}")

profiles = ["normal", "congested", "unstable"]
strategies = ["fixed", "rule-based", "online-learning"]

labels = {
    "fixed": "Fixed",
    "rule-based": "Rule-based",
    "online-learning": "Online learning"
}

# 1. Execution time comparison
fig, ax = plt.subplots(figsize=(10, 6))

x = list(range(len(profiles)))
width = 0.24

for i, strategy in enumerate(strategies):
    means = [
        float(get_row(p, strategy)["execution_time_seconds_mean"])
        for p in profiles
    ]
    errors = [
        float(get_row(p, strategy)["execution_time_seconds_std"])
        for p in profiles
    ]

    positions = [v + (i - 1) * width for v in x]
    ax.bar(
        positions, means, width,
        yerr=errors, capsize=4,
        label=labels[strategy]
    )

ax.set_title("Execution Time Across Network Conditions")
ax.set_xlabel("Network condition")
ax.set_ylabel("Execution time (seconds)")
ax.set_xticks(x)
ax.set_xticklabels(profiles)
ax.legend()
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(OUTPUT / "execution_time_comparison.png", dpi=300)
plt.close(fig)


# 2. Checkpoint count comparison
fig, ax = plt.subplots(figsize=(10, 6))

for i, strategy in enumerate(strategies):
    means = [
        float(get_row(p, strategy)["checkpoint_count_mean"])
        for p in profiles
    ]
    errors = [
        float(get_row(p, strategy)["checkpoint_count_std"])
        for p in profiles
    ]

    positions = [v + (i - 1) * width for v in x]
    ax.bar(
        positions, means, width,
        yerr=errors, capsize=4,
        label=labels[strategy]
    )

ax.set_title("Checkpoint Count Across Network Conditions")
ax.set_xlabel("Network condition")
ax.set_ylabel("Number of checkpoints")
ax.set_xticks(x)
ax.set_xticklabels(profiles)
ax.legend()
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(OUTPUT / "checkpoint_count_comparison.png", dpi=300)
plt.close(fig)


# 3. Online prediction MAE
fig, ax = plt.subplots(figsize=(9, 5))

mae = [
    float(get_row(p, "online-learning")["prediction_mae_seconds_mean"])
    for p in profiles
]
mae_std = [
    float(get_row(p, "online-learning")["prediction_mae_seconds_std"])
    for p in profiles
]

ax.bar(profiles, mae, yerr=mae_std, capsize=5)
ax.set_title("Online Learning Prediction Error")
ax.set_xlabel("Network condition")
ax.set_ylabel("Mean Absolute Error (seconds)")
ax.grid(axis="y", alpha=0.3)

fig.tight_layout()
fig.savefig(OUTPUT / "online_prediction_mae.png", dpi=300)
plt.close(fig)

print("All graphs generated successfully:")
for path in sorted(OUTPUT.glob("*.png")):
    print(path)
