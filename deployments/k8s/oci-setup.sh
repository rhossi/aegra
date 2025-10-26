#!/bin/bash

# OCI Container Registry Setup Helper
# This script helps you set up authentication with OCI Container Registry

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔐 OCI Container Registry Setup${NC}"
echo ""

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

echo -e "${YELLOW}📋 Prerequisites:${NC}"
echo "1. OCI Console access"
echo "2. Your OCI namespace (found in Object Storage > Namespaces)"
echo "3. An Auth Token (create in Identity > Users > Your User > Auth Tokens)"
echo ""

# Get OCI namespace
read -p "Enter your OCI namespace (e.g., your-tenant-name): " OCI_NAMESPACE
if [ -z "$OCI_NAMESPACE" ]; then
    echo -e "${RED}❌ OCI namespace is required${NC}"
    exit 1
fi

# Get OCI region
read -p "Enter your OCI region (default: us-chicago-1): " OCI_REGION
OCI_REGION=${OCI_REGION:-us-chicago-1}

# Get OCI username (non-federated format)
read -p "Enter your OCI username (e.g., felipe.f.garcia@oracle.com): " OCI_USERNAME
if [ -z "$OCI_USERNAME" ]; then
    echo -e "${RED}❌ OCI username is required${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Using non-federated login format${NC}"

# Get Auth Token
echo -e "${YELLOW}🔑 Enter your OCI Auth Token (it won't be displayed):${NC}"
read -s AUTH_TOKEN
if [ -z "$AUTH_TOKEN" ]; then
    echo -e "${RED}❌ Auth Token is required${NC}"
    exit 1
fi

echo ""

# Set environment variables
export OCI_NAMESPACE="$OCI_NAMESPACE"
export OCI_REGION="$OCI_REGION"

echo -e "${YELLOW}🔧 Setting environment variables...${NC}"
echo "export OCI_NAMESPACE=\"$OCI_NAMESPACE\"" >> ~/.bashrc
echo "export OCI_REGION=\"$OCI_REGION\"" >> ~/.bashrc

# Login to OCI Container Registry
echo -e "${YELLOW}🔐 Logging into OCI Container Registry...${NC}"
$CONTAINER_CMD login "${OCI_REGION}.ocir.io" -u "${OCI_NAMESPACE}/${OCI_USERNAME}" -p "$AUTH_TOKEN"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Successfully logged into OCI Container Registry${NC}"
    echo ""
    echo -e "${BLUE}📝 Environment variables set:${NC}"
    echo "  OCI_NAMESPACE=$OCI_NAMESPACE"
    echo "  OCI_REGION=$OCI_REGION"
    echo ""
    echo -e "${GREEN}🎉 Setup complete! You can now build and push images.${NC}"
    echo ""
    echo -e "${YELLOW}💡 Next steps:${NC}"
    echo "1. Run: ./build-and-push.sh --push"
    echo "2. Update 06-aegra-app.yaml with your image URL"
    echo "3. Run: ./deploy.sh"
else
    echo -e "${RED}❌ Failed to login to OCI Container Registry${NC}"
    echo "Please check your credentials and try again"
    exit 1
fi
