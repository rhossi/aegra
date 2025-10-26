#!/bin/bash

# Aegra Docker Build and Push Script
# This script builds the Aegra Docker image and pushes it to a registry

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="aegra"
TAG="${AEGRA_TAG:-latest}"
OCI_REGION="${OCI_REGION:-us-chicago-1}"
OCI_NAMESPACE="${OCI_NAMESPACE:-}"
# Use the correct OCI Container Registry URL format
OCI_REGISTRY="${OCI_REGISTRY:-${OCI_REGION}.ocir.io}"
FULL_IMAGE_NAME="${OCI_NAMESPACE:+$OCI_NAMESPACE/}${IMAGE_NAME}:${TAG}"

echo -e "${BLUE}🐳 Building Aegra Docker image...${NC}"

# Check for container runtime (prefer Podman over Docker)
if command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
    echo -e "${GREEN}✅ Using Podman${NC}"
elif command -v docker &> /dev/null; then
    CONTAINER_CMD="docker"
    echo -e "${YELLOW}⚠️  Using Docker (Podman preferred)${NC}"
else
    echo -e "${RED}❌ Neither Podman nor Docker is installed or in PATH${NC}"
    echo "Please install Podman (preferred) or Docker"
    exit 1
fi

# Use existing local image
LOCAL_IMAGE="localhost/idxzjcdglx2s/aegra"
echo -e "${YELLOW}🔨 Using existing local image: ${LOCAL_IMAGE}${NC}"

# Debug output
echo -e "${BLUE}🔍 Debug Information:${NC}"
echo "  Container command: $CONTAINER_CMD"
echo "  Local image: $LOCAL_IMAGE"
echo "  Full image name: $FULL_IMAGE_NAME"
echo ""

# Build for x86_64 architecture (Linux AMD64) for Kubernetes compatibility
echo -e "${YELLOW}🔨 Building image for linux/amd64 architecture...${NC}"

# Get the project root directory (parent of deployments/k8s)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Change to project root directory
cd "$PROJECT_ROOT"

$CONTAINER_CMD build --platform linux/amd64 -f deployments/docker/Dockerfile -t "${LOCAL_IMAGE}" .

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to build image${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Image built successfully for linux/amd64${NC}"

# Ask if user wants to push
if [ "$1" = "--push" ] || [ "$1" = "-p" ]; then
    echo -e "${YELLOW}📤 Pushing image to OCI Container Registry...${NC}"
    
    if [ -z "$OCI_NAMESPACE" ]; then
        echo -e "${RED}❌ OCI_NAMESPACE environment variable is not set${NC}"
        echo "Set it to your OCI namespace (e.g., export OCI_NAMESPACE=your-namespace)"
        echo "You can find your namespace in the OCI Console under 'Administration' > 'Tenancy Details'"
        echo ""
        echo -e "${YELLOW}📋 Prerequisites:${NC}"
        echo "1. Create a Container Registry repository in OCI Console:"
        echo "   Developer Services → Containers & Artifacts → Container Registry"
        echo "2. Get your Object Storage Namespace from Tenancy Details"
        echo "3. Set OCI_NAMESPACE environment variable"
        exit 1
    fi
    
    # Login to OCI Container Registry if not already logged in
    echo -e "${YELLOW}🔐 Logging into OCI Container Registry...${NC}"
    echo "You may need to run: $CONTAINER_CMD login ${OCI_REGISTRY} -u your-namespace/your-username -p your-auth-token"
    
    # Tag for OCI registry (following Gerald's exact pattern)
    OCI_IMAGE_NAME="${OCI_REGISTRY}/${OCI_NAMESPACE}/${IMAGE_NAME}"
    
    # Debug output for push
    echo -e "${BLUE}🔍 Push Debug Information:${NC}"
    echo "  OCI Registry: $OCI_REGISTRY"
    echo "  OCI Namespace: $OCI_NAMESPACE"
    echo "  Image Name: $IMAGE_NAME"
    echo "  Tag: $TAG"
    echo "  OCI Image Name: $OCI_IMAGE_NAME"
    echo "  Tag command: $CONTAINER_CMD tag \"${FULL_IMAGE_NAME}\" \"${OCI_IMAGE_NAME}\""
    echo "  Push command: $CONTAINER_CMD push \"${OCI_IMAGE_NAME}\""
    echo ""
    
    $CONTAINER_CMD tag "${LOCAL_IMAGE}" "${OCI_IMAGE_NAME}"
    
    $CONTAINER_CMD push "${OCI_IMAGE_NAME}"
    echo -e "${GREEN}✅ Image pushed successfully to OCI Container Registry${NC}"
    echo -e "${BLUE}📝 Update your Kubernetes manifests to use: ${OCI_IMAGE_NAME}${NC}"
else
    echo -e "${YELLOW}💡 To push the image, run: $0 --push${NC}"
    echo -e "${BLUE}📝 Set OCI environment variables:${NC}"
    echo "  export OCI_NAMESPACE=your-namespace"
    echo "  export OCI_REGION=your-region (optional, defaults to us-chicago-1)"
    echo "  $0 --push"
fi

echo -e "${GREEN}🎉 Build completed!${NC}"
