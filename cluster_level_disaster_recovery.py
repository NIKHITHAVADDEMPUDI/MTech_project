import os
import logging
import time
import subprocess
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
MINIKUBE_PATH = '/opt/homebrew/bin/minikube'
KUBECTL_PATH = '/opt/homebrew/bin/kubectl'
YQ_PATH = '/opt/homebrew/bin/yq'
NEAT_PATH = '/Users/vaddempudinikhitha/.krew/bin/kubectl-neat'

BACKUP_FILE = str(Path(__file__).parent / "combined.yaml")
BACKUP_DIR = str(Path(__file__).parent / "backup")
NODE_COUNT_FILE = str(Path(__file__).parent / "node_count.txt")  # ← NEW

def run_command(command):
    result = subprocess.run(command, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        logger.error(f"Command failed: {command}\nError: {result.stderr}")
    return result.stdout.strip()

def save_node_count(count):
    with open(NODE_COUNT_FILE, 'w') as f:
        f.write(str(count))

def load_node_count():
    if os.path.exists(NODE_COUNT_FILE):
        with open(NODE_COUNT_FILE) as f:
            return int(f.read())
    return 1  # fallback if file missing

def get_non_default_nodes():
    nodes = run_command(f"{KUBECTL_PATH} get nodes -o jsonpath='{{.items[*].metadata.name}}'").split()
    non_default_nodes = []
    for node in nodes:
        labels = run_command(f"{KUBECTL_PATH} get node {node} -o jsonpath='{{.metadata.labels}}'")
        if "control-plane" not in labels:
            non_default_nodes.append(node)
    logger.info(f"Found {len(non_default_nodes)} non-default nodes.")
    return non_default_nodes

def get_pod_mount_paths(namespace, pod_name):
    command = f"{KUBECTL_PATH} get pod {pod_name} -n {namespace} -o jsonpath='{{.spec.containers[*].volumeMounts[*].mountPath}}'"
    return run_command(command).split()

def backup_pod_data(namespace, pod_name, mount_paths):
    backup_path = Path(BACKUP_DIR) / namespace / pod_name
    backup_path.mkdir(parents=True, exist_ok=True)
    for mount_path in mount_paths:
        dest_dir = backup_path / mount_path.lstrip('/')  # preserve folder structure
        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        command = f"{KUBECTL_PATH} cp {namespace}/{pod_name}:{mount_path} {dest_dir}"
        subprocess.run(command, shell=True, check=False)

def backup_all_pod_volumes():
    non_default_nodes = get_non_default_nodes()
    for node in non_default_nodes:
        pods = run_command(f"{KUBECTL_PATH} get pods --field-selector spec.nodeName={node} --all-namespaces -o jsonpath='{{.items[*].metadata.name}}'").split()
        namespaces = run_command(f"{KUBECTL_PATH} get pods --field-selector spec.nodeName={node} --all-namespaces -o jsonpath='{{.items[*].metadata.namespace}}'").split()
        for ns, pod in zip(namespaces, pods):
            if ns not in ['kube-system', 'kube-proxy', 'kubernetes-dashboard']:
                mounts = get_pod_mount_paths(ns, pod)
                backup_pod_data(ns, pod, mounts)

def restore_pod_data(namespace, pod_name, backup_path):
    mount_paths = get_pod_mount_paths(namespace, pod_name)
    skip_paths = ['/var/run/secrets/kubernetes.io/serviceaccount']
    for mount_path in mount_paths:
        if any(mount_path.startswith(skip) for skip in skip_paths):
            logger.info(f"Skipping read-only system path: {mount_path}")
            continue
        local_backup_path = Path(backup_path) / mount_path.lstrip('/')
        if local_backup_path.exists():
            command = f"{KUBECTL_PATH} cp {local_backup_path}/. {namespace}/{pod_name}:{mount_path}"
            subprocess.run(command, shell=True, check=False)

def restore_all_pod_data():
    namespaces = run_command(f"{KUBECTL_PATH} get namespaces -o jsonpath='{{.items[*].metadata.name}}'").split()
    for ns in namespaces:
        pods = run_command(f"{KUBECTL_PATH} get pods -n {ns} -o jsonpath='{{.items[*].metadata.name}}'").split()
        for pod in pods:
            backup_path = Path(BACKUP_DIR) / ns / pod
            if backup_path.exists():
                if wait_for_pod_ready(ns, pod):
                    restore_pod_data(ns, pod, backup_path)
                else:
                    logger.warning(f"Skipping restore for {ns}/{pod} because it is not ready.")

def run_kubectl_get_all_and_neat():
    try:
        command = (
            f"{KUBECTL_PATH} get all,pv,pvc --all-namespaces -o yaml | "
            f"{NEAT_PATH} | "
            f"{YQ_PATH} eval 'del(.items[].metadata.creationTimestamp, .items[].metadata.uid, "
            f".items[].spec.claimRef, .items[].metadata.resourceVersion)' - > {BACKUP_FILE}"
        )
        subprocess.run(command, shell=True, check=True)
        logger.info(f"Cluster resources backed up to {BACKUP_FILE}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error backing up cluster resources: {e}")

def check_minikube_status():
    result = subprocess.run([MINIKUBE_PATH, 'status'], capture_output=True, text=True)
    out = result.stdout
    return all(x in out for x in ["host: Running", "kubelet: Running", "apiserver: Running"])

def get_minikube_node_count():
    try:
        nodes = run_command(f"{KUBECTL_PATH} get nodes -o jsonpath='{{.items[*].metadata.name}}'").split()
        count = len(nodes)
        save_node_count(count)
        return count
    except Exception:
        return load_node_count()

def start_minikube_cluster(nodes):
    try:
        subprocess.run(
            [MINIKUBE_PATH, 'start', '--driver=podman', '--container-runtime=cri-o', f'--nodes={nodes}'],
            check=True
        )
        logger.info("Minikube cluster started.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to start Minikube: {e}")

def restore_cluster_resources():
    if os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE) as f:
            yaml_content = f.read()
        try:
            subprocess.run([KUBECTL_PATH, 'apply', '-f', '-'], input=yaml_content, text=True, check=True)
            logger.info("Cluster resources restored from backup.")
        except subprocess.CalledProcessError as e:
            logger.error(f"kubectl apply failed: {e}")
    else:
        logger.error("No cluster backup file found.")

def wait_for_pod_ready(namespace, pod_name, timeout=300):
    start_time = time.time()
    while time.time() - start_time < timeout:
        status = run_command(f"{KUBECTL_PATH} get pod {pod_name} -n {namespace} -o jsonpath='{{.status.containerStatuses[*].ready}}'")
        if all(s == 'true' for s in status.split()):
            logger.info(f"Pod {namespace}/{pod_name} is ready.")
            return True
        logger.info(f"Waiting for pod {namespace}/{pod_name} to become ready...")
        time.sleep(5)
    logger.warning(f"Timeout waiting for pod {namespace}/{pod_name} to become ready.")
    return False

def wait_for_all_pods_ready(timeout=600):
    namespaces = run_command(f"{KUBECTL_PATH} get namespaces -o jsonpath='{{.items[*].metadata.name}}'").split()
    all_pods_ready = False
    start_time = time.time()
    while time.time() - start_time < timeout:
        all_pods_ready = True
        for ns in namespaces:
            pods = run_command(f"{KUBECTL_PATH} get pods -n {ns} -o jsonpath='{{.items[*].metadata.name}}'").split()
            for pod in pods:
                status = run_command(f"{KUBECTL_PATH} get pod {pod} -n {ns} -o jsonpath='{{.status.containerStatuses[*].ready}}'")
                if not all(s == 'true' for s in status.split()):
                    all_pods_ready = False
                    logger.info(f"Waiting for pod {ns}/{pod} to become ready...")
                    break
            if not all_pods_ready:
                break
        if all_pods_ready:
            logger.info("All pods are ready!")
            return True
        time.sleep(5)
    logger.warning("Timeout waiting for all pods to become ready.")
    return False

def monitor_and_backup_cluster():
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    while True:
        if not check_minikube_status():
            logger.warning("Cluster down! Restarting and restoring...")
            nodes = load_node_count()
            start_minikube_cluster(nodes)
            restore_cluster_resources()
            if wait_for_all_pods_ready():
                restore_all_pod_data()
        else:
            get_minikube_node_count()
            run_kubectl_get_all_and_neat()
            backup_all_pod_volumes()
        time.sleep(60)

if __name__ == "__main__":
    try:
        logger.info("Starting cluster monitor and backup...")
        monitor_and_backup_cluster()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
