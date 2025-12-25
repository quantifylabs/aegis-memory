# Kubernetes Deployment

This directory contains Kubernetes manifests for deploying Aegis Memory.

## Quick Start

```bash
# Create namespace
kubectl create namespace aegis

# Apply all manifests
kubectl apply -f k8s/

# Check deployment status
kubectl get pods -n aegis
```

## Manifests

- `namespace.yaml` - Aegis namespace definition
- `configmap.yaml` - Configuration (non-sensitive)
- `secret.yaml` - Secrets template (customize with your values)
- `postgres.yaml` - PostgreSQL with pgvector StatefulSet
- `aegis.yaml` - Aegis API Deployment
- `dashboard.yaml` - Dashboard Deployment (optional)
- `ingress.yaml` - Ingress configuration (customize for your domain)

## Prerequisites

1. A Kubernetes cluster (1.25+)
2. kubectl configured to access your cluster
3. An OpenAI API key
4. A PostgreSQL-compatible storage class

## Configuration

Before deploying, update the following:

1. **secret.yaml**: Add your actual secrets
   ```bash
   # Create secret from command line (recommended)
   kubectl create secret generic aegis-secrets -n aegis \
     --from-literal=openai-api-key=sk-your-key \
     --from-literal=aegis-api-key=your-secure-key \
     --from-literal=postgres-password=your-db-password
   ```

2. **ingress.yaml**: Update with your domain and TLS configuration

## Production Considerations

- Use external PostgreSQL (RDS, Cloud SQL) for production
- Enable TLS for all endpoints
- Configure proper resource limits
- Set up monitoring with Prometheus
- Configure backup with Velero

See [docs/OPERATIONS.md](../docs/OPERATIONS.md) for detailed production guidance.

