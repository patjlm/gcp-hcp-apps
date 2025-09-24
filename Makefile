.PHONY: generate test check lint format

# Generate ArgoCD applications for all fleet targets
generate:
	uv run hack/generate.py

# Run unit and integration tests
test:
	uv run pytest hack -v

# Check that generated files are current (for CI/CD)
check: generate
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
