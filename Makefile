.PHONY: generate test check lint format

# Generate ArgoCD applications for all fleet targets
generate:
	uv run hack/generate.py

# Run unit and integration tests
test:
	uv run pytest hack -v

# Check that generated files are current (for CI/CD)
check: generate
	@echo "Validating generated Helm charts..."
	@find rendered/ -name "Chart.yaml" -exec dirname {} \; | xargs -I {} helm lint {} --quiet --set cluster.environment=test-env --set cluster.sector=test-sector --set cluster.region=test-region --set cluster.name=test-cluster --set cluster.projectId=test-project --set cluster.vpcId=test-vpc --set name=test-cluster --set server=https://test-server --set metadata.annotations.'gcp-hcp/project-id'=test-project --set metadata.annotations.'gcp-hcp/vpc-id'=test-vpc
	@echo "✓ All generated charts are valid"

	@if git diff --exit-code rendered/; then \
		echo "✓ Generated files are current"; \
	else \
		echo "✗ Generated files are stale. Run 'make generate'"; \
		exit 1; \
	fi

# Run linting and type checks
lint:
	ruff check hack/

# Format code and fix auto-fixable issues
format:
	ruff check --fix hack/
	ruff check --select I --fix hack/
	ruff format hack/
