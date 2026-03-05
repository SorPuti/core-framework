"""
Stride - Deployment Generators.

Generates deployment configuration files for Docker, PM2, and Kubernetes.

Usage:
    # CLI
    core deploy docker    # Generate docker-compose.yml
    core deploy pm2       # Generate ecosystem.config.js
    core deploy k8s       # Generate k8s/ manifests
    core deploy all       # Generate all
    
    # Programmatic
    from stride.deployment import generate_docker, generate_pm2, generate_kubernetes
    
    generate_docker(Path("."))
    generate_pm2(Path("."))
    generate_kubernetes(Path("."))
"""

from stride.deployment.docker import generate_docker
from stride.deployment.pm2 import generate_pm2
from stride.deployment.kubernetes import generate_kubernetes

__all__ = [
    "generate_docker",
    "generate_pm2",
    "generate_kubernetes",
]
