# URL Shortener + Image Resizer — Kubernetes Autoscaling Demo

A combined FastAPI + Streamlit application demonstrating Horizontal Pod
Autoscaler (HPA) behavior on a local Kubernetes cluster (minikube).

## What this app does

Two independent features sharing one backend and one Redis instance:

1. **URL Shortener** — submit a long URL, get back a short code (hash-based,
   deliberately CPU-heavy to generate real autoscaling load).
2. **Image Resizer** — upload an image, get back thumbnail/medium/large
   resized + sharpened versions (genuinely CPU-heavy via Pillow).

Both endpoints are CPU-bound by design, so a load test against either (or
both) will trigger the backend's HorizontalPodAutoscaler to add replicas.

## Architecture

```
┌──────────┐      ┌─────────┐      ┌───────┐
│ Frontend │─────▶│ Backend │─────▶│ Redis │
│Streamlit │      │ FastAPI │      │       │
└──────────┘      └─────────┘      └───────┘
                   (scales via HPA)   (1 replica,
                                       shared state)
```

Redis stays at 1 replica — it's shared state all backend pods read/write to,
not what's being scaled. The backend scales because it's where the CPU work
happens.

## Prerequisites

- Docker Desktop (with WSL2 backend or native Windows containers)
- kubectl
- minikube
- Python 3.11+ (for running `load_test.py` locally)

## Local testing (Docker Compose)

```powershell
docker compose up -d --build
```

Open http://localhost:8501 — test both tabs (shorten a URL, upload an image)
to confirm everything works before moving to Kubernetes.

```powershell
docker compose down
```

## Kubernetes deployment

### 1. Start minikube

```powershell
minikube start --driver=docker --cpus=2 --memory=4096
kubectl get nodes          # should show STATUS: Ready
minikube addons enable metrics-server
kubectl top nodes          # wait ~1 min if "metrics not available yet"
```

### 2. Build images

```powershell
docker build -t app-backend:latest ./backend
docker build -t app-frontend:latest ./frontend
docker images | findstr app-
```

### 3. Load images into minikube

```powershell
minikube image load app-backend:latest
minikube image load app-frontend:latest
minikube image ls | findstr app-
```

### 4. Deploy

```powershell
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/backend.yaml
kubectl apply -f k8s/backend-hpa.yaml
kubectl apply -f k8s/frontend.yaml
```

Checkpoint:
```powershell
kubectl get pods       # all should be Running, 1/1
kubectl get hpa        # TARGETS should show a %, not <unknown>
```

### 5. Open the UI

```powershell
kubectl port-forward svc/frontend 8501:8501
```
Open http://localhost:8501, confirm both features work end-to-end through
Kubernetes. Ctrl+C when done testing.

### 6. Get a load-testable backend address

New terminal:
```powershell
minikube service backend --url
```
Copy the printed address (e.g. `http://127.0.0.1:38091`) — NodePort traffic
load-balances across all backend pods, unlike port-forward which always hits
one pod.

### 7. Run the load test

```powershell
pip install requests Pillow
python load_test.py http://127.0.0.1:38091
```

### 8. Watch it scale

Two more terminals, started alongside the load test:
```powershell
kubectl get hpa backend-hpa -w
kubectl get pods -w
```
Expect: CPU % climbs past 50, replica count increases (1→2→4...), new pods
go Pending→Running. After the load test ends and a ~5 min cooldown, it
scales back down.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Pods stuck `ErrImageNeverPull` | Re-run `minikube image load` for that image |
| `CrashLoopBackOff` | `kubectl logs <pod-name>` |
| HPA shows `<unknown>/50%` forever | metrics-server not ready — check `kubectl get pods -n kube-system` |
| `localhost:8501` doesn't load | Confirm `kubectl port-forward` is still running |

## Project structure

```
acc-micro-project/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
├── k8s/
│   ├── redis.yaml
│   ├── backend.yaml
│   ├── backend-hpa.yaml
│   └── frontend.yaml
├── docker-compose.yml
└── load_test.py
```