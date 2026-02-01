"""
Kubernetes deployment generator.

Generates Kubernetes manifests for container orchestration.
"""

from __future__ import annotations

from pathlib import Path


def generate_kubernetes(output_dir: Path) -> None:
    """
    Generate Kubernetes deployment files.
    
    Creates:
        - k8s/namespace.yaml
        - k8s/configmap.yaml
        - k8s/secrets.yaml
        - k8s/api-deployment.yaml
        - k8s/api-service.yaml
        - k8s/worker-deployment.yaml
        - k8s/scheduler-deployment.yaml
        - k8s/ingress.yaml
        - k8s/hpa.yaml
    
    Args:
        output_dir: Directory to write files to
    """
    output_dir = Path(output_dir)
    k8s_dir = output_dir / "k8s"
    k8s_dir.mkdir(parents=True, exist_ok=True)
    
    # Namespace
    namespace = '''apiVersion: v1
kind: Namespace
metadata:
  name: core-app
  labels:
    app.kubernetes.io/name: core-app
'''
    
    # ConfigMap
    configmap = '''apiVersion: v1
kind: ConfigMap
metadata:
  name: core-app-config
  namespace: core-app
data:
  ENVIRONMENT: "production"
  DEBUG: "false"
  API_PREFIX: "/api/v1"
  KAFKA_BOOTSTRAP_SERVERS: "kafka.kafka.svc.cluster.local:9092"
  REDIS_URL: "redis://redis.redis.svc.cluster.local:6379/0"
  TASK_WORKER_CONCURRENCY: "4"
  TASK_DEFAULT_QUEUE: "default"
'''
    
    # Secrets (template)
    secrets = '''apiVersion: v1
kind: Secret
metadata:
  name: core-app-secrets
  namespace: core-app
type: Opaque
stringData:
  # IMPORTANT: Replace these with actual secrets
  # Use: kubectl create secret generic core-app-secrets --from-literal=SECRET_KEY=xxx
  SECRET_KEY: "change-me-in-production"
  DATABASE_URL: "postgresql+asyncpg://user:password@postgres.database.svc.cluster.local:5432/app"
'''
    
    # API Deployment
    api_deployment = '''apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: core-app
  labels:
    app: api
    component: web
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
        component: web
    spec:
      containers:
        - name: api
          image: your-registry/core-app:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 8000
              name: http
          envFrom:
            - configMapRef:
                name: core-app-config
            - secretRef:
                name: core-app-secrets
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 10"]
      terminationGracePeriodSeconds: 30
'''
    
    # API Service
    api_service = '''apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: core-app
  labels:
    app: api
spec:
  type: ClusterIP
  ports:
    - port: 80
      targetPort: 8000
      protocol: TCP
      name: http
  selector:
    app: api
'''
    
    # Worker Deployment
    worker_deployment = '''apiVersion: apps/v1
kind: Deployment
metadata:
  name: worker
  namespace: core-app
  labels:
    app: worker
    component: background
spec:
  replicas: 2
  selector:
    matchLabels:
      app: worker
  template:
    metadata:
      labels:
        app: worker
        component: background
    spec:
      containers:
        - name: worker
          image: your-registry/core-app:latest
          imagePullPolicy: Always
          command: ["core", "worker", "--queue", "default", "--concurrency", "4"]
          envFrom:
            - configMapRef:
                name: core-app-config
            - secretRef:
                name: core-app-secrets
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
      terminationGracePeriodSeconds: 60
'''
    
    # Scheduler Deployment
    scheduler_deployment = '''apiVersion: apps/v1
kind: Deployment
metadata:
  name: scheduler
  namespace: core-app
  labels:
    app: scheduler
    component: background
spec:
  replicas: 1  # Only one scheduler instance
  selector:
    matchLabels:
      app: scheduler
  template:
    metadata:
      labels:
        app: scheduler
        component: background
    spec:
      containers:
        - name: scheduler
          image: your-registry/core-app:latest
          imagePullPolicy: Always
          command: ["core", "scheduler"]
          envFrom:
            - configMapRef:
                name: core-app-config
            - secretRef:
                name: core-app-secrets
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "200m"
      terminationGracePeriodSeconds: 30
'''
    
    # Ingress
    ingress = '''apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  namespace: core-app
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "60"
spec:
  tls:
    - hosts:
        - api.example.com
      secretName: api-tls
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 80
'''
    
    # Horizontal Pod Autoscaler
    hpa = '''apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
  namespace: core-app
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
        - type: Pods
          value: 4
          periodSeconds: 15
      selectPolicy: Max
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: worker-hpa
  namespace: core-app
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: worker
  minReplicas: 2
  maxReplicas: 8
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
'''
    
    # Kustomization
    kustomization = '''apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: core-app

resources:
  - namespace.yaml
  - configmap.yaml
  - secrets.yaml
  - api-deployment.yaml
  - api-service.yaml
  - worker-deployment.yaml
  - scheduler-deployment.yaml
  - ingress.yaml
  - hpa.yaml

commonLabels:
  app.kubernetes.io/name: core-app
  app.kubernetes.io/managed-by: kustomize
'''
    
    # Write files
    (k8s_dir / "namespace.yaml").write_text(namespace)
    (k8s_dir / "configmap.yaml").write_text(configmap)
    (k8s_dir / "secrets.yaml").write_text(secrets)
    (k8s_dir / "api-deployment.yaml").write_text(api_deployment)
    (k8s_dir / "api-service.yaml").write_text(api_service)
    (k8s_dir / "worker-deployment.yaml").write_text(worker_deployment)
    (k8s_dir / "scheduler-deployment.yaml").write_text(scheduler_deployment)
    (k8s_dir / "ingress.yaml").write_text(ingress)
    (k8s_dir / "hpa.yaml").write_text(hpa)
    (k8s_dir / "kustomization.yaml").write_text(kustomization)
