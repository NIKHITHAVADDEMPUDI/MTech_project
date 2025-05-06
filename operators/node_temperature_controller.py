import subprocess
import time
import re

THRESHOLD = 80  # percent
CHECK_INTERVAL = 30  # seconds

def get_podman_stats():
    result = subprocess.run(
        ["podman", "stats", "--no-stream"],
        capture_output=True,
        text=True
    )
    return result.stdout

def parse_stats(stats_output):
    node_cpu = {}
    lines = stats_output.strip().split("\n")
    header_skipped = False

    for line in lines:
        if not header_skipped:
            header_skipped = True
            continue

        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 3:
            name = parts[1]  # NAME column
            cpu_str = parts[2]  # CPU % column
            cpu_val = float(cpu_str.strip('%'))
            node_cpu[name] = cpu_val

    return node_cpu

def cordon_node(node):
    subprocess.run(["kubectl", "cordon", node])

def uncordon_node(node):
    subprocess.run(["kubectl", "uncordon", node])

def main():
    while True:
        print("Checking node CPU usage...")
        stats_output = get_podman_stats()
        node_cpu = parse_stats(stats_output)

        for node, cpu in node_cpu.items():
            print(f"Node: {node}, CPU: {cpu}%")

            if cpu > THRESHOLD:
                print(f"> {node} over {THRESHOLD}%, cordoning...")
                cordon_node(node)
            else:
                print(f"> {node} below {THRESHOLD}%, uncordoning...")
                uncordon_node(node)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
