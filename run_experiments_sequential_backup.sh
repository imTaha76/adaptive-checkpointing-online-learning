#!/bin/bash

set -euo pipefail

cd "/mnt/c/adaptive checkpointing using online learning"

mkdir -p results/experiment_logs

# Authenticate sudo before starting the experiment batch.
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

for profile in normal congested unstable; do

    apply_profile "$profile"

    for strategy in fixed rule-based online-learning; do

        for trial in 1 2 3 4 5; do

            echo ""
            echo "========================================"
            echo "PROFILE: $profile"
            echo "STRATEGY: $strategy"
            echo "TRIAL: $trial"
            echo "========================================"

            log_file="results/experiment_logs/${profile}_${strategy}_trial${trial}.log"

            CHECKPOINT_NETWORK_PROFILE="$profile" \
                python3 src/main.py \
                --reset \
                --strategy "$strategy" \
                --checkpoint-interval 100000 \
                --payload-mb 1 2>&1 | tee "$log_file"

        done
    done
done

# Restore normal network conditions after the experiments.
apply_profile normal

echo ""
echo "========================================"
echo "ALL EXPERIMENTS COMPLETED"
echo "========================================"
