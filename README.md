# GCP HCP Apps

ArgoCD applications for the GCP HCP project.

## Usage

Deploy the ApplicationSet via Terraform to automatically discover and deploy all applications in the `management-clusters/` directory structure.

## Adding New Applications

1. Create a new directory under `management-clusters/`
2. Add an `application.yaml` file with your ArgoCD Application manifest
3. The ApplicationSet will automatically discover and deploy it