
import csv
import statistics
from pathlib import Path
from collections import defaultdict

CSV_FILE = Path("results/network_transfers.csv")


def analyze_results():
    if not CSV_FILE.exists():
        print("Results CSV not found.")
        return

    profiles = defaultdict(list)
    failures = defaultdict(int)

    with CSV_FILE.open("r", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            profile = row["network_profile"]

            if row["status"] == "success":
                profiles[profile].append(row)
            else:
                failures[profile] += 1

    print("=" * 65)
    print("NETWORK PROFILE COMPARISON")
    print("=" * 65)

    total_success = 0
    total_failure = 0

    for profile in ["normal", "congested", "unstable"]:
        records = profiles[profile]

        if not records:
            print(f"\n{profile.upper()}: No successful transfers")
            continue

        times = [
            float(row["transfer_time_seconds"])
            for row in records
        ]

        throughputs = [
            float(row["throughput_mbps"])
            for row in records
        ]

        sizes = [
            int(row["file_size_bytes"])
            for row in records
        ]

        success = len(records)
        failure = failures[profile]
        total_success += success
        total_failure += failure

        print(f"\n{profile.upper()} NETWORK")
        print("-" * 45)
        print(f"Successful transfers: {success}")
        print(f"Failed transfers: {failure}")
        print(f"Average file size: {statistics.mean(sizes):.2f} bytes")
        print(f"Average transfer time: {statistics.mean(times):.6f} seconds")
        print(f"Median transfer time: {statistics.median(times):.6f} seconds")
        print(f"Average throughput: {statistics.mean(throughputs):.4f} Mbps")

    print("\n" + "=" * 65)
    print("OVERALL RESULTS")
    print("-" * 45)
    print(f"Successful transfers: {total_success}")
    print(f"Failed transfers: {total_failure}")

    total = total_success + total_failure

    if total:
        print(f"Success rate: {total_success / total * 100:.2f}%")

    print("=" * 65)


if __name__ == "__main__":
    analyze_results()
