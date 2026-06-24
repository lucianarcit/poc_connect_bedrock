.PHONY: install test lint build clean terraform-init terraform-plan terraform-apply terraform-destroy

install:
	pip install -r requirements-dev.txt

test:
	pytest

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/

build:
	./scripts/build_lambdas.sh

terraform-init:
	cd terraform && terraform init

terraform-plan:
	cd terraform && terraform plan

terraform-apply:
	cd terraform && terraform apply

terraform-destroy:
	cd terraform && terraform destroy

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ packages/ htmlcov/ .coverage
