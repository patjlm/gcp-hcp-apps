.PHONY: generate test check

# Generate ArgoCD applications for all fleet targets
generate:
	uv run hack/generate.py

# Run unit and integration tests
test:
	uv run hack/test_generate.py -v

# Check that generated files are current (for CI/CD)
check: generate
	@if git diff --exit-code rendered/; then \
		echo "✓ Generated files are current"; \
	else \
		echo "✗ Generated files are stale. Run 'make generate'"; \
		exit 1; \
	fi