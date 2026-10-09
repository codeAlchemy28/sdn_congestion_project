import argparse
import json
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(
    description="Run an SDN UDP performance test."
    )
    parser.add_argument(
    "--mode",
    choices=["static", "adaptive"],
    required=True
    )
    args = parser.parse_args()


    print(f"\nUDP TEST — {args.mode.upper()} ROUTING")

    command = [
        "iperf3",
        "-c", "10.0.0.2",
        "-u",
        "-b", "10M",
        "-t", "20",
        "-J"
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"Could not run iperf3: {exc}")
        sys.exit(1)

    if result.returncode != 0:
        print("iperf3 failed:")
        print(result.stderr or result.stdout)
        sys.exit(1)

    try:
        data = json.loads(result.stdout)
        end = data["end"]
        receiver = end.get("sum_received")

        if not isinstance(receiver, dict):
            raise ValueError(
                "Receiver statistics not found. "
                "Inspect the raw JSON output."
            )

        throughput = receiver["bits_per_second"] / 1_000_000
        jitter = float(receiver["jitter_ms"])
        lost = int(receiver["lost_packets"])
        total = int(receiver["packets"])

        if "lost_percent" in receiver:
            loss = float(receiver["lost_percent"])
        elif total > 0:
            loss = lost / total * 100
        else:
            raise ValueError("Receiver reported no packets.")

    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"Could not read receiver results: {exc}")
        print("Raw iperf3 JSON:")
        print(result.stdout)
        sys.exit(1)

    print("\n===== RECEIVER RESULTS =====")
    print(f"Mode        : {args.mode}")
    print(f"Throughput  : {throughput:.2f} Mbps")
    print(f"Packet loss : {loss:.2f}%")
    print(f"Jitter      : {jitter:.3f} ms")
    print(f"Packets lost: {lost}/{total}")
    print("============================")



if __name__ == "__main__":
    main()
