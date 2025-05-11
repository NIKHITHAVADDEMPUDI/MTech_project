from flask import Flask, jsonify, request
import subprocess
import json
import re
from kubernetes import client, config
from flask_cors import CORS

app = Flask(__name__)

# Enable CORS
CORS(app)

# Initialize Kubernetes clients
config.load_kube_config()  # Assumes kubeconfig is set up locally
v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()

def get_minikube_status():
    """Get Minikube status using subprocess"""
    try:
        result = subprocess.run(['minikube', 'status', '--format=json'], capture_output=True, text=True, check=True)
        print(f"Minikube Status Output: {result.stdout}")

        if not result.stdout:
            return {"error": "Minikube status returned empty output"}

        return json.loads(result.stdout)

    except subprocess.CalledProcessError as e:
        return {"error": "Failed to get minikube status", "details": e.stderr}
    except json.JSONDecodeError:
        return {"error": "Failed to parse minikube status: Invalid JSON"}

def get_kubernetes_nodes():
    """Get Kubernetes nodes"""
    try:
        nodes = v1.list_node()
        return [{
            "name": node.metadata.name,
            "status": [condition.type for condition in node.status.conditions if condition.status == "True"]
        } for node in nodes.items]
    except Exception as e:
        return {"error": "Failed to get Kubernetes nodes", "details": str(e)}

def parse_mem_usage(mem_usage_str):
    """Parses '412.8MB / 2.042GB' => (used_MB, total_MB)"""
    used_str, total_str = mem_usage_str.split(' / ')

    def convert_to_mb(mem_str):
        if 'GB' in mem_str:
            return float(mem_str.replace('GB', '').strip()) * 1024
        elif 'MB' in mem_str:
            return float(mem_str.replace('MB', '').strip())
        elif 'kB' in mem_str:
            return float(mem_str.replace('kB', '').strip()) / 1024
        else:
            return 0

    used_mb = convert_to_mb(used_str)
    total_mb = convert_to_mb(total_str)
    return used_mb, total_mb

def get_podman_stats():
    """Parse podman stats plain text output"""
    try:
        result = subprocess.run(['podman', 'stats', '--no-stream'], capture_output=True, text=True, check=True)
        
        lines = result.stdout.strip().split('\n')
        if len(lines) < 2:
            return {"error": "No stats returned from podman"}

        headers = re.split(r'\s{2,}', lines[0])
        parsed_stats = {}

        for line in lines[1:]:
            cols = re.split(r'\s{2,}', line)
            data = dict(zip(headers, cols))
            node_name = data.get('NAME', '')

            cpu_percent = float(data['CPU %'].replace('%', '').strip())
            cpu_time = data.get('CPU TIME', '')

            mem_used_mb, mem_total_mb = parse_mem_usage(data['MEM USAGE / LIMIT'])
            mem_percent = float(data['MEM %'].replace('%', '').strip())

            parsed_stats[node_name] = {
                'cpu': cpu_percent,
                'cpu_time': cpu_time,
                'memory_used_mb': mem_used_mb,
                'memory_total_mb': mem_total_mb,
                'memory_percent': mem_percent
            }

        return parsed_stats

    except subprocess.CalledProcessError as e:
        return {"error": "Failed to get podman stats", "details": e.stderr}
    except Exception as e:
        return {"error": "Unexpected error parsing podman stats", "details": str(e)}

@app.route('/')
def home():
    return "Welcome to the Flask Kubernetes API!"

@app.route('/api/nodes', methods=['GET'])
def get_nodes_info():
    """Get information about nodes in the cluster"""
    minikube_status = get_minikube_status()
    kubernetes_nodes = get_kubernetes_nodes()
    podman_stats = get_podman_stats()

    return jsonify({
        "minikube_status": minikube_status,
        "nodes": kubernetes_nodes,
        "metrics": podman_stats
    })

@app.route('/api/pods', methods=['GET'])
def get_pods_by_node():
    """Get all pods associated with a specific node."""
    node_name = request.args.get('node')  # Get the node name from the query string

    if not node_name:
        return jsonify({"error": "Node name is required"}), 400

    try:
        pods = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}")
        pod_info = []

        for pod in pods.items:
            pod_info.append({
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": pod.status.phase,
                "node_name": pod.spec.node_name
            })

        return jsonify({"pods": pod_info})

    except Exception as e:
        return jsonify({"error": "Failed to get pods for node", "details": str(e)}), 500

@app.route('/api/deployments', methods=['GET'])
def get_deployments():
    """Get deployments and their associated pods (just names)"""
    deployments_info = []
    try:
        deployments = apps_v1.list_namespaced_deployment(namespace='default')

        for deployment in deployments.items:
            deployments_info.append({
                "name": deployment.metadata.name
            })
    except Exception as e:
        return jsonify({"error": "Failed to fetch deployments", "details": str(e)}), 500

    return jsonify(deployments_info)

@app.route('/api/deployments/<deployment_name>/pods', methods=['GET'])
def get_pods_by_deployment(deployment_name):
    """Return pods belonging to a specific deployment"""
    try:
        # Find the deployment
        deployment = apps_v1.read_namespaced_deployment(name=deployment_name, namespace='default')

        # Get ReplicaSets owned by the deployment
        replicasets = apps_v1.list_namespaced_replica_set(
            namespace='default',
            label_selector=",".join([f"{k}={v}" for k, v in deployment.spec.selector.match_labels.items()])
        )

        pod_info = []
        for rs in replicasets.items:
            # Get pods owned by each replicaset
            pods = v1.list_namespaced_pod(
                namespace='default',
                label_selector=",".join([f"{k}={v}" for k, v in rs.spec.selector.match_labels.items()])
            )
            for pod in pods.items:
                for owner in pod.metadata.owner_references or []:
                    if owner.kind == "ReplicaSet" and owner.name == rs.metadata.name:
                        pod_info.append({
                            "name": pod.metadata.name,
                            "namespace": pod.metadata.namespace,
                            "status": pod.status.phase,
                            "node_name": pod.spec.node_name
                        })

        return jsonify({"pods": pod_info})

    except client.exceptions.ApiException as e:
        return jsonify({"error": f"Deployment '{deployment_name}' not found", "details": str(e)}), 404
    except Exception as e:
        return jsonify({"error": "Failed to fetch pods for deployment", "details": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
