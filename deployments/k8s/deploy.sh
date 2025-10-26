#!/bin/bash

# Aegra Kubernetes Deployment Script
# This script deploys Aegra to your Kubernetes cluster

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="aegra"
IMAGE_TAG="${AEGRA_IMAGE_TAG:-latest}"
DOCKER_REGISTRY="${DOCKER_REGISTRY:-}"

echo -e "${BLUE}🚀 Deploying Aegra to Kubernetes...${NC}"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}❌ kubectl is not installed or not in PATH${NC}"
    exit 1
fi

# Check if we can connect to the cluster
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}❌ Cannot connect to Kubernetes cluster${NC}"
    echo "Please ensure your kubeconfig is properly configured"
    exit 1
fi

echo -e "${GREEN}✅ Connected to Kubernetes cluster${NC}"

# Create namespace first
echo -e "${YELLOW}📦 Creating namespace...${NC}"
kubectl apply -f 01-namespace.yaml

# Apply configurations in order
echo -e "${YELLOW}🔧 Applying configurations...${NC}"
kubectl apply -f 02-configmap.yaml
kubectl apply -f 02-configmap-files.yaml
kubectl apply -f 03-secrets.yaml

echo -e "${YELLOW}💾 Creating persistent volumes...${NC}"
kubectl apply -f 04-pvc.yaml

echo -e "${YELLOW}🐘 Deploying PostgreSQL...${NC}"
kubectl apply -f 05-postgres.yaml

# Optional: Deploy Redis
if [ "$1" = "--with-redis" ] || [ "$2" = "--with-redis" ]; then
    echo -e "${YELLOW}🔴 Deploying Redis...${NC}"
    kubectl apply -f 05-redis.yaml
fi

echo -e "${YELLOW}🤖 Deploying Aegra application...${NC}"
kubectl apply -f 06-aegra-app.yaml

echo -e "${YELLOW}🌐 Creating services...${NC}"
kubectl apply -f 07-services.yaml

# No ingress - removed as requested
# No waiting - deployment runs in background

echo -e "${GREEN}✅ Deployment completed successfully!${NC}"

# Show deployment status
echo -e "${BLUE}📊 Deployment Status:${NC}"
kubectl get pods -n $NAMESPACE
kubectl get services -n $NAMESPACE

# Show access information
echo -e "${BLUE}🔗 Access Information:${NC}"
echo "ClusterIP Service: kubectl port-forward -n $NAMESPACE svc/aegra-service 8000:80"
echo "LoadBalancer Service: Check external IP with 'kubectl get svc aegra-loadbalancer -n $NAMESPACE'"

echo -e "${GREEN}🎉 Aegra is now running in your Kubernetes cluster!${NC}"
