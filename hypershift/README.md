# Hypershift GitOps Configuration

This directory contains the Hypershift operator YAML manifests for deployment to GCP management clusters via ArgoCD.

## Content Generation

The hypershift YAML manifests in this directory were generated using the hypershift binary:

```bash
hypershift install render --development
```

## Files

- `hypershift-dev.yaml`: Complete hypershift operator deployment manifests for development environment
- `cert.yaml`: Additional certificate configuration

## ArgoCD Deployment

This directory is deployed by ArgoCD from the https://github.com/patjlm/gcp-hcp-apps.git repository to management clusters.