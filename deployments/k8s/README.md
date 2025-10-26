# Aegra Kubernetes Deployment

This directory contains Kubernetes manifests to deploy Aegra in a Kubernetes cluster.

## Prerequisites

- Kubernetes cluster (v1.19+)
- `kubectl` configured to access your cluster
- Docker image of Aegra built and available in your cluster's registry
- Persistent storage support in your cluster (for PostgreSQL and Aegra data)
- OCI Container Registry access
- Podman (preferred) or Docker configured to authenticate with OCI Container Registry

## OCI Container Registry Setup

Before deploying, you need to set up authentication with OCI Container Registry:

1. **Create a Container Registry Repository:**
   - Log into OCI Console
   - Go to **Developer Services** → **Containers & Artifacts** → **Container Registry**
   - Click **"Create repository"**
   - Choose **Access** (Private/Public) and **Repository name** (e.g., `aegra`)
   - Click **"Create"**

2. **Get your OCI namespace:**
   - Go to **Administration** → **Tenancy Details**
   - Copy the **Object Storage Namespace** (e.g., `idxzjcdglx2s`)

3. **Create an Auth Token:**
   - Go to **Profile** → **My profile**
   - Click **"Auth Tokens"** under Resources
   - Click **"Generate Token"**
   - Give it a description (e.g., "Container Registry")
   - Copy the generated token (you won't see it again!)

4. **Login to OCI Container Registry:**
   ```bash
   # Using Podman (preferred)
   # For federated users (Oracle Identity Cloud Service):
   podman login us-chicago-1.ocir.io -u "your-object-storage-namespace/oracleidentitycloudservice/your-email@domain.com" -p "your-auth-token"
   
   # For non-federated users:
   podman login us-chicago-1.ocir.io -u "your-object-storage-namespace/your-username" -p "your-auth-token"
   
   # Or using Docker (same format)
   docker login us-chicago-1.ocir.io -u "your-object-storage-namespace/oracleidentitycloudservice/your-email@domain.com" -p "your-auth-token"
   ```

4. **Set environment variables:**
   ```bash
   export OCI_NAMESPACE=your-object-storage-namespace
   export OCI_REGION=us-chicago-1  # or your preferred region
   ```

   **Or use the automated setup script:**
   ```bash
   ./oci-setup.sh
   ```

## Manual Container Commands

If you prefer to run commands manually instead of using the scripts:

### Build Image
```bash
# Using Podman
podman build -f deployments/docker/Dockerfile -t aegra:latest .

# Using Docker
docker build -f deployments/docker/Dockerfile -t aegra:latest .
```

### Tag for OCI Registry
```bash
# Using Podman
podman tag aegra:latest us-chicago-1.ocir.io/your-namespace/aegra:latest

# Using Docker
docker tag aegra:latest us-chicago-1.ocir.io/your-namespace/aegra:latest
```

### Push to Registry
```bash
# Using Podman
podman push us-chicago-1.ocir.io/your-namespace/aegra:latest

# Using Docker
docker push us-chicago-1.ocir.io/your-namespace/aegra:latest
```

## Quick Start

1. **Set up secrets:**
   ```bash
   cd deployments/k8s
   cp 03-secrets.example.yaml 03-secrets.yaml
   # Edit 03-secrets.yaml with your actual secrets
   ```

2. **Build and push the Docker image to OCI Container Registry:**
   ```bash
   # Set your OCI namespace (find it in OCI Console > Object Storage > Namespaces)
   export OCI_NAMESPACE=your-namespace
   
   # Optional: Set your OCI region (defaults to us-chicago-1)
   export OCI_REGION=your-region
   
   # Build and push the image
   ./build-and-push.sh --push
   ```

2. **Update the image reference:**
   Edit `06-aegra-app.yaml` and change:
   ```yaml
   image: aegra:latest  # Change this to your Docker image
   ```
   to:
   ```yaml
   image: us-chicago-1.ocir.io/your-namespace/aegra:latest
   ```

3. **Deploy Aegra:**
   ```bash
   # Basic deployment
   ./deploy.sh
   
   # With Redis (optional, matches docker-compose.yml)
   ./deploy.sh --with-redis
   ```

## Configuration

### Secrets

**IMPORTANT:** Before deploying, update the secrets in `03-secrets.yaml`:

1. **Change the PostgreSQL password:**
   ```bash
   echo -n "your-secure-password" | base64
   ```
   Replace the `POSTGRES_PASSWORD` value in `03-secrets.yaml`

2. **Add API keys (optional):**
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `LANGFUSE_PUBLIC_KEY`: Your Langfuse public key
   - `LANGFUSE_SECRET_KEY`: Your Langfuse secret key

### ConfigMap

Edit `02-configmap.yaml` to customize:
- Database URL
- Authentication type
- Debug mode
- Port configuration

### Storage

The deployment uses PersistentVolumeClaims for:
- PostgreSQL data (`postgres-pvc`): 10Gi
- Aegra application data (`aegra-data-pvc`): 5Gi

Adjust the storage sizes in `04-pvc.yaml` based on your needs.

## Access Methods

### 1. Port Forward (Development)
```bash
kubectl port-forward -n aegra svc/aegra-service 8000:80
```
Access: http://localhost:8000

### 2. LoadBalancer Service
```bash
# Get external IP
kubectl get svc aegra-loadbalancer -n aegra
```
Access: http://EXTERNAL-IP

### 3. Ingress (Production)
Access via LoadBalancer service or port-forward (ingress removed).

## Monitoring and Troubleshooting

### Check Pod Status
```bash
kubectl get pods -n aegra
```

### View Logs
```bash
# Aegra application logs
kubectl logs -n aegra -l app.kubernetes.io/name=aegra

# PostgreSQL logs
kubectl logs -n aegra -l app.kubernetes.io/name=postgres
```

### Database Migration
The deployment automatically runs database migrations on startup. If you need to run them manually:
```bash
kubectl exec -n aegra deployment/aegra-app -- alembic upgrade head
```

### Scale the Application
```bash
kubectl scale deployment aegra-app -n aegra --replicas=3
```

## Production Considerations

### Security
1. **Change default passwords** in `03-secrets.yaml`
2. **Use proper TLS certificates** for ingress
3. **Configure network policies** for additional security
4. **Use secrets management** (e.g., External Secrets Operator)

### Performance
1. **Adjust resource limits** in `06-aegra-app.yaml`
2. **Configure horizontal pod autoscaling**:
   ```bash
   kubectl autoscale deployment aegra-app -n aegra --cpu-percent=70 --min=2 --max=10
   ```
3. **Use a managed PostgreSQL service** for production

### Backup
1. **Backup PostgreSQL data** regularly
2. **Backup Aegra application data** (graphs, etc.)
3. **Consider using Velero** for cluster-level backups

## Troubleshooting

### Common Issues

1. **Image Pull Errors**: Ensure your image is available in the registry and authentication is configured
2. **Database Connection Issues**: Check PostgreSQL pod status and database credentials
3. **Persistent Volume Issues**: Verify your cluster supports the storage class used
4. **Resource Constraints**: Adjust CPU/memory limits in the deployment manifests if needed
5. **Alembic Migration Failures**: Ensure all alembic files are properly included in the ConfigMap
6. **Health Check Failures**: Check application logs for database connectivity issues

### Fixed Issues

The following issues have been resolved in the current deployment:

- **✅ OCI Registry Authentication**: Fixed username format and auth token encoding
- **✅ Database URL Configuration**: Fixed password substitution in ConfigMap
- **✅ Alembic Files**: All necessary alembic files are now included in ConfigMaps
- **✅ Architecture Compatibility**: Images built for linux/amd64 to match cluster architecture
- **✅ Health Check Endpoints**: Properly configured liveness and readiness probes

## Cleanup

To remove the deployment:
```bash
kubectl delete namespace aegra
```

## File Structure

```
deployments/k8s/
├── 01-namespace.yaml      # Namespace definition
├── 02-configmap.yaml     # Application configuration
├── 02-configmap-files.yaml # Configuration files (aegra.json, auth.py, .env, alembic)
├── 03-secrets.example.yaml # Template for secrets (copy to 03-secrets.yaml)
├── 03-secrets.yaml       # Secrets (passwords, API keys) - NOT in git
├── 04-pvc.yaml          # Persistent volume claims (PostgreSQL, Aegra data, Redis)
├── 05-postgres.yaml     # PostgreSQL deployment
├── 05-redis.yaml        # Redis deployment (optional)
├── 06-aegra-app.yaml    # Aegra application deployment
├── 07-services.yaml     # Kubernetes services
├── 08-ingress.yaml      # Ingress configuration (removed - not used)
├── deploy.sh            # Deployment script
├── build-and-push.sh    # Docker build and push script (OCI optimized)
├── oci-setup.sh         # OCI Container Registry setup helper
└── README.md            # This file
```

## Support

For issues and questions:
- Check the logs: `kubectl logs -n aegra -l app.kubernetes.io/name=aegra`
- Verify pod status: `kubectl describe pod -n aegra -l app.kubernetes.io/name=aegra`
- Check service endpoints: `kubectl get endpoints -n aegra`
