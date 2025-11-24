#!/usr/bin/env python3
"""
Aegra Kubernetes Deployment Script
This script deploys Aegra to your Kubernetes cluster
"""

import os
import shutil
import sys
import subprocess

# Colors for output
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
NC = "\033[0m"  # No Color


def print_colored(message: str, color: str = NC) -> None:
    """Print a colored message."""
    print(f"{color}{message}{NC}")


def check_command(cmd: str) -> bool:
    """Check if a command is available."""
    return shutil.which(cmd) is not None


def run_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    result = subprocess.run(cmd, check=check)
    return result


def main() -> None:
    """Main function."""
    # Configuration
    namespace = "aegra"
    image_tag = os.environ.get("AEGRA_IMAGE_TAG", "latest")
    docker_registry = os.environ.get("DOCKER_REGISTRY", "")

    print_colored("🚀 Deploying Aegra to Kubernetes...", BLUE)

    # Check if kubectl is available
    if not check_command("kubectl"):
        print_colored("❌ kubectl is not installed or not in PATH", RED)
        sys.exit(1)

    # Check if we can connect to the cluster
    try:
        subprocess.run(["kubectl", "cluster-info"], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        print_colored("❌ Cannot connect to Kubernetes cluster", RED)
        print("Please ensure your kubeconfig is properly configured")
        sys.exit(1)

    print_colored("✅ Connected to Kubernetes cluster", GREEN)

    # Create namespace first
    print_colored("📦 Creating namespace...", YELLOW)
    run_command(["kubectl", "apply", "-f", "01-namespace.yaml"])

    # Apply configurations in order
    print_colored("🔧 Applying configurations...", YELLOW)
    run_command(["kubectl", "apply", "-f", "02-configmap.yaml"])
    run_command(["kubectl", "apply", "-f", "02-configmap-files.yaml"])
    run_command(["kubectl", "apply", "-f", "03-secrets.yaml"])

    print_colored("💾 Creating persistent volumes...", YELLOW)
    run_command(["kubectl", "apply", "-f", "04-pvc.yaml"])

    print_colored("🐘 Deploying PostgreSQL...", YELLOW)
    run_command(["kubectl", "apply", "-f", "05-postgres.yaml"])

    # Optional: Deploy Redis
    if "--with-redis" in sys.argv:
        print_colored("🔴 Deploying Redis...", YELLOW)
        run_command(["kubectl", "apply", "-f", "05-redis.yaml"])

    print_colored("🤖 Deploying Aegra application...", YELLOW)
    run_command(["kubectl", "apply", "-f", "06-aegra-app.yaml"])

    print_colored("🌐 Creating services...", YELLOW)
    run_command(["kubectl", "apply", "-f", "07-services.yaml"])

    # No ingress - removed as requested
    # No waiting - deployment runs in background

    print_colored("✅ Deployment completed successfully!", GREEN)

    # Show deployment status
    print_colored("📊 Deployment Status:", BLUE)
    run_command(["kubectl", "get", "pods", "-n", namespace], check=False)
    run_command(["kubectl", "get", "services", "-n", namespace], check=False)

    # Show access information
    print_colored("🔗 Access Information:", BLUE)
    print(f"ClusterIP Service: kubectl port-forward -n {namespace} svc/aegra-service 8000:80")
    print(f"LoadBalancer Service: Check external IP with 'kubectl get svc aegra-loadbalancer -n {namespace}'")

    print_colored("🎉 Aegra is now running in your Kubernetes cluster!", GREEN)


if __name__ == "__main__":
    main()

