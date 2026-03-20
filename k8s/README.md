# Kubernetes Deployment

## Prerequisites
- kubectl configured for your cluster
- Docker image pushed to registry

## Deploy

```bash
# Create secrets from .env
kubectl create secret generic socialentangler-secrets --from-env-file=backend/.env

# Deploy all components
kubectl apply -f k8s/

# Check status
kubectl get pods -l app=socialentangler
kubectl get hpa

# Scale workers manually
kubectl scale deployment socialentangler-worker --replicas=4

# Run migrations
kubectl exec -it $(kubectl get pod -l component=api -o jsonpath='{.items[0].metadata.name}') \
  -- python -m migrations.runner up
```

## Architecture
- `api-deployment.yaml` — FastAPI API (2 replicas, autoscales to 10)
- `worker-deployment.yaml` — Celery workers (2 replicas, autoscales to 20) + Beat (1 replica)
- `hpa.yaml` — Horizontal Pod Autoscalers (CPU 70%, Memory 80%)

## Notes
- Workers run on spot/preemptible instances (60-80% cheaper; tasks are idempotent)
- Beat MUST be single replica (prevents duplicate task scheduling)
- terminationGracePeriodSeconds=120 lets in-flight tasks complete before pod shutdown
