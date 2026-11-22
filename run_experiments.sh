#!/bin/bash
set -euo pipefail

cd "/mnt/c/adaptive checkpointing using online learning"

mkdir -p results/experiment_logs

SEED="${1:-20261122}"
RUN_TAG="$(date +%Y%m%d_%H%M%S)_seed${SEED}"

SCHEDULE_FILE="results/experiment_logs/concurrent_final_schedule_${RUN_TAG}.tsv"

sudo -v

apply_profile() {
    local profile="$1"

    echo ""
    echo "Applying network profile: $profile"

    case "$profile" in
        normal)
            sudo ip netns exec worker tc qdisc del dev veth-worker root 2>/dev/null || true
            sudo ip netns exec receiver tc qdisc del dev veth-receiver root 2>/dev/null || true
            ;;
        congested)
            sudo ip netns exec worker tc qdisc replace dev veth-worker root netem delay 75ms rate 10mbit
            sudo ip netns exec receiver tc qdisc replace dev veth-receiver root netem delay 75ms
            ;;
        unstable)
            sudo ip netns exec worker tc qdisc replace dev veth-worker root netem delay 40ms 15ms distribution normal rate 5mbit loss 1%
            sudo ip netns exec receiver tc qdisc replace dev veth-receiver root netem delay 40ms 15ms distribution normal
            ;;
        *)
            echo "Unknown profile: $profile"
            exit 1
            ;;
    esac
}

restore_normal() {
    echo ""
    echo "Restoring normal network conditions..."
    sudo ip netns exec worker tc qdisc del dev veth-worker root 2>/dev/null || true
    sudo ip netns exec receiver tc qdisc del dev veth-receiver root 2>/dev/null || true
}

trap restore_normal EXIT INT TERM

# Generate a reproducible randomized experiment schedule.
python3 - "$SEED" "$SCHEDULE_FILE" <<'PY'
import csv
import random
import sys

seed = int(sys.argv[1])
output = sys.argv[2]
rng = random.Random(seed)

profiles = ["normal", "congested", "unstable"]
strategies = ["fixed", "rule-based", "online-learning"]

with open(output, "w", newline="") as f:
    writer = csv.writer(f, delimiter="\t")
    writer.writerow(["trial", "profile", "strategy"])

    for trial in range(1, 6):
        trial_profiles = profiles.copy()
        rng.shuffle(trial_profiles)

        for profile in trial_profiles:
            trial_strategies = strategies.copy()
            rng.shuffle(trial_strategies)

            for strategy in trial_strategies:
                writer.writerow([trial, profile, strategy])

print(f"Randomized schedule saved: {output}")
PY

echo ""
echo "========================================"
echo "CONCURRENT FINAL EXPERIMENT BATCH"
echo "Seed: $SEED"
echo "Run tag: $RUN_TAG"
echo "Total runs: 45"
echo "========================================"

tail -n +2 "$SCHEDULE_FILE" | tr -d "\r" |
while IFS=$'\t' read -r trial profile strategy; do

    apply_profile "$profile"

    echo ""
    echo "========================================"
    echo "PROFILE: $profile"
    echo "STRATEGY: $strategy"
    echo "TRIAL: $trial"
    echo "========================================"

    log_file="results/experiment_logs/${RUN_TAG}_${profile}_${strategy}_trial${trial}.log"

    CHECKPOINT_NETWORK_PROFILE="$profile" \
        python3 src/main.py \
        --reset \
        --strategy "$strategy" \
        --checkpoint-interval 100000 \
        --payload-mb 1 2>&1 | tee "$log_file"

done

echo ""
echo "========================================"
echo "ALL 45 EXPERIMENTS COMPLETED"
echo "Schedule: $SCHEDULE_FILE"
echo "========================================"
