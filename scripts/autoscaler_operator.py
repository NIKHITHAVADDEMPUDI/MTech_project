import subprocess
import time
import re
from kubernetes import client, config

# Load kube config
config.load_kube_config()

# Initialize the Kubernetes API client
v1 = client.CoreV1Api()

# Function to check top event with "Insufficient memory"
def check_insufficient_memory_in_events(pod_name, namespace='default'):
    try:
        result = subprocess.run(
            ["kubectl", "describe", "pod", pod_name, "-n", namespace],
            capture_output=True,
            text=True,
            check=True
        )

        event_section = re.search(r'Events:\n((?:.|\n)*)', result.stdout)
        if event_section:
            events = event_section.group(1).strip().split("\n")
            event_lines = [line for line in events if not re.match(r'^\s*(Type|----)', line) and line.strip()]
            if event_lines:
                # Read only the topmost event line
                top_event_line = event_lines[0].strip()
                if re.search(r"Insufficient memory", top_event_line, re.IGNORECASE):
                    print(f"Pod {pod_name} has insufficient memory in top event: {top_event_line}")
                    return True
    except subprocess.CalledProcessError as e:
        print(f"Error describing pod {pod_name}: {e}")

    return False

# Function to check pending pods with insufficient memory
def check_pending_pods():
    pods = v1.list_pod_for_all_namespaces(watch=False)
    pending_pods = []

    for pod in pods.items:
        if pod.status.phase == 'Pending':
            if check_insufficient_memory_in_events(pod.metadata.name, pod.metadata.namespace):
                pending_pods.append(pod)

    return pending_pods

# Function to add Minikube node
def add_minikube_node():
    try:
        print("Adding a new node to Minikube...")
        subprocess.run(["minikube", "node", "add"], check=True)
        print("New node added successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error adding node to Minikube: {e}")

# Function to delete pending pods
def delete_pending_pods(pods):
    for pod in pods:
        try:
            print(f"Deleting pending pod: {pod.metadata.name} in namespace {pod.metadata.namespace}")
            v1.delete_namespaced_pod(pod.metadata.name, pod.metadata.namespace)
        except Exception as e:
            print(f"Error deleting pod {pod.metadata.name}: {e}")

# Monitor and scale
def monitor_and_scale():
    while True:
        print("Checking for pending pods...")
        pending_pods = check_pending_pods()

        if pending_pods:
            print(f"Found {len(pending_pods)} pending pods due to insufficient memory.")
            
            # Add a new node if there are pending pods
            add_minikube_node()

            # Delete the pending pods so they can be rescheduled
            delete_pending_pods(pending_pods)
        else:
            print("No pending pods requiring new nodes.")

        time.sleep(90)

if __name__ == "__main__":
    monitor_and_scale()
