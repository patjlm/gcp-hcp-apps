# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **gcp-hcp-apps** repository - ArgoCD applications for the GCP HCP (Google Cloud Platform Hypershift Container Platform) project using the Traditional App of Apps pattern. It manages deployment of applications to management clusters including ArgoCD itself, Prometheus, cert-manager, and the Hypershift operator.

## Repository Architecture

### Core Structure
- **management-clusters/**: Root Helm chart implementing App of Apps pattern
  - `Chart.yaml`: Root Helm chart definition
  - `values.yaml`: Default application configurations
  - `values-dev.yaml`: Development environment overrides
  - `values-prod.yaml`: Production environment overrides
  - `templates/`: ArgoCD Application templates for each managed application
- **hypershift/**: Raw Kubernetes manifests for Hypershift operator
  - `hypershift-dev.yaml`: Generated from `hypershift install render --development`
  - `cert.yaml`: Certificate configuration

### Bootstrap Flow
1. **Terraform creates**: GKE cluster + ArgoCD namespace + minimal root application
2. **ArgoCD takes over**: Root app self-configures and deploys all applications
3. **Self-management**: ArgoCD manages its own lifecycle via argocd-app.yaml template

### Application Management
- Applications are defined as Helm templates in `management-clusters/templates/`
- Each template creates an ArgoCD Application that deploys to the cluster
- Applications can be Helm charts (ArgoCD, Prometheus, cert-manager) or raw manifests (Hypershift)
- Environment-specific overrides in `values-{env}.yaml` files

## Common Commands

### Helm Operations
```bash
# Validate Helm chart syntax
helm lint management-clusters/

# Template rendering for debugging
helm template management-clusters/ --values management-clusters/values-dev.yaml

# Dry-run template with specific values
helm template management-clusters/ \
  --values management-clusters/values.yaml \
  --values management-clusters/values-dev.yaml
```

### Hypershift Manifest Generation
```bash
# Regenerate Hypershift manifests (when operator version changes)
hypershift install render --development > hypershift/hypershift-dev.yaml
```

### Repository Validation
```bash
# Validate YAML syntax across repository
find . -name "*.yaml" -o -name "*.yml" | xargs -I {} yaml-lint {}

# Validate ArgoCD Application templates
argocd app validate --file management-clusters/templates/
```

## Key Configuration Patterns

### Adding New Applications
1. Create template in `management-clusters/templates/{app-name}-app.yaml`
2. Add application configuration to `management-clusters/values.yaml`
3. Add environment-specific overrides in `values-dev.yaml` and `values-prod.yaml`
4. Use conditional logic: `{{- if .Values.applications.{app-name}.enabled }}`

### Environment Detection
- Root application automatically determines environment from cluster metadata ConfigMap
- Dynamically loads appropriate values file (`values-dev.yaml` or `values-prod.yaml`)
- Injects cluster metadata (project_id, region, vpc_network_id) to all applications

### Self-Management Pattern
- ArgoCD manages its own lifecycle via `argocd-app.yaml` template
- Root application updates itself from Git changes
- All applications follow GitOps principles with automated sync

## Architecture Context

This repository implements a multi-tier architecture:
- **Regional Clusters**: Infrastructure management
- **Management Clusters**: Hypershift hosting (this repository manages these)
- **Customer Clusters**: Hypershift-managed hosted clusters

For detailed architecture documentation, see:
- `BOOTSTRAP-ARCHITECTURE.md`: Bootstrap flow and component relationships
- `GitOps-repo-structure.md`: Comprehensive analysis of GitOps patterns and alternatives
- `README.md`: Usage patterns and repository structure

# Security Rules

## Global security rules for all projects 🛡️

### Security Principles

- **Complete Mediation:** Ensure every access request is validated and authorized. No bypasses allowed.
- **Compromise Recording:** Implement mechanisms to detect, record, and respond to security breaches.
- **Defense in Depth:** Use multiple, layered security controls to protect systems and data.
- **Economy of Mechanism:** Keep designs simple and easy to understand. Avoid unnecessary complexity.
- **Least Common Mechanism:** Minimize shared resources and isolate components to reduce risk.
- **Least Privilege:** Grant only the minimum permissions necessary for users and systems.
- **Open Design:** Favor transparency and well-understood mechanisms over security by obscurity.
- **Psychological Acceptability:** Make security controls user-friendly and aligned with user expectations.
- **Secure by Design, Default, Deployment (SD3):** Ship with secure defaults, deny by default, and avoid hardcoded credentials.

### Security Controls

- **Authentication:** Use strong, standard authentication methods. Require authentication for all non-public areas. Store credentials securely and enforce password policies. Use multi-factor authentication where possible.
- **Authorization:** Enforce least privilege and explicit permissions. Use a single, trusted component for authorization checks. Deny by default and audit permissions regularly.
- **Encryption:** Encrypt all network traffic and data at rest where applicable. Use approved certificates and protocols.
- **Logging:** Log security events centrally. Do not log sensitive data. Restrict log access and monitor for suspicious activity.
- **Networking:** Encrypt all communications. Do not expose unnecessary endpoints or ports. Restrict network access to only what is required.

Apply these rules to all code, infrastructure, and processes to maintain a strong security posture across your projects.

## Secure coding rules for Helm charts ⎈

- Check for vulnerable dependencies and validate chart provenance.
- Secure configuration and manage secrets outside of values.yaml.
- Use tools like checkov for security scanning.
