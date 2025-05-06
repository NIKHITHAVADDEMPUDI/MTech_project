#!/bin/bash

echo "Starting port-forwarding..."

kubectl port-forward service/frontend-service 30001:80 &
kubectl port-forward service/backend-service 30002:80 &

echo "Port forwarding is running on:"
echo "Frontend → http://localhost:30001"
echo "Backend  → http://localhost:30002"

trap "echo 'Stopping port forwarding...'; kill 0" SIGINT
wait
