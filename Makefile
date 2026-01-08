.PHONY: help install test lint format deploy-infra deploy-dataflow deploy-api clean

# Variables
GCP_PROJECT_ID ?= your-project-id
GCP_REGION ?= europe-west1
PYTHON := python3.11
VENV := venv

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	$(PYTHON) -m venv $(VENV)
	. $(VENV)/bin/activate && pip install --upgrade pip
	. $(VENV)/bin/activate && pip install -r requirements.txt

test: ## Run tests
	. $(VENV)/bin/activate && pytest tests/ --cov=pipelines --cov=api --cov-report=html

lint: ## Run linters
	. $(VENV)/bin/activate && flake8 pipelines/ api/ --count --statistics
	. $(VENV)/bin/activate && mypy pipelines/ api/ --ignore-missing-imports

format: ## Format code
	. $(VENV)/bin/activate && black pipelines/ api/ tests/
	. $(VENV)/bin/activate && isort pipelines/ api/ tests/

terraform-init: ## Initialize Terraform
	cd infrastructure/terraform && terraform init \
		-backend-config="bucket=$(GCP_PROJECT_ID)-terraform-state"

terraform-plan: terraform-init ## Plan Terraform changes
	cd infrastructure/terraform && terraform plan \
		-var="project_id=$(GCP_PROJECT_ID)" \
		-var-file=../environments/prod.tfvars \
		-out=tfplan

terraform-apply: ## Apply Terraform changes
	cd infrastructure/terraform && terraform apply tfplan

deploy-infra: terraform-apply ## Deploy infrastructure

deploy-sql: ## Deploy SQL models and views
	bq query --use_legacy_sql=false < sql/materialized_views/hourly_pop_performance.sql
	bq query --use_legacy_sql=false < sql/ml_models/load_prediction.sql

deploy-dataflow: ## Deploy Dataflow pipelines
	. $(VENV)/bin/activate && python pipelines/dataflow/enrichment_pipeline.py \
		--runner=DataflowRunner \
		--project=$(GCP_PROJECT_ID) \
		--region=$(GCP_REGION) \
		--job_name=cdn-enrichment-$$(date +%s) \
		--temp_location=gs://$(GCP_PROJECT_ID)-dataflow-temp/temp \
		--staging_location=gs://$(GCP_PROJECT_ID)-dataflow-staging/staging \
		--num_workers=20 \
		--max_num_workers=100 \
		--update
	. $(VENV)/bin/activate && python pipelines/dataflow/anomaly_detection_pipeline.py \
		--runner=DataflowRunner \
		--project=$(GCP_PROJECT_ID) \
		--region=$(GCP_REGION) \
		--job_name=cdn-anomaly-detection-$$(date +%s) \
		--update

build-api: ## Build API Docker image
	cd api && docker build -t gcr.io/$(GCP_PROJECT_ID)/routing-api:latest .

push-api: build-api ## Push API Docker image
	docker push gcr.io/$(GCP_PROJECT_ID)/routing-api:latest

deploy-api: push-api ## Deploy API to Cloud Run
	gcloud run deploy routing-api \
		--image gcr.io/$(GCP_PROJECT_ID)/routing-api:latest \
		--platform managed \
		--region $(GCP_REGION) \
		--allow-unauthenticated \
		--memory 2Gi \
		--cpu 2 \
		--min-instances 2 \
		--max-instances 20

deploy-all: deploy-infra deploy-sql deploy-dataflow deploy-api ## Deploy everything

verify: ## Verify deployment
	@echo "Checking Pub/Sub topics..."
	@gcloud pubsub topics list --project=$(GCP_PROJECT_ID)
	@echo "\nChecking BigQuery datasets..."
	@bq ls --project_id=$(GCP_PROJECT_ID)
	@echo "\nChecking Dataflow jobs..."
	@gcloud dataflow jobs list --region=$(GCP_REGION) --status=active
	@echo "\nChecking Cloud Run services..."
	@gcloud run services list --region=$(GCP_REGION)

clean: ## Clean temporary files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .pytest_cache htmlcov .coverage
	rm -rf infrastructure/terraform/.terraform infrastructure/terraform/tfplan

destroy: ## Destroy all infrastructure (WARNING: destructive!)
	@echo "⚠️  WARNING: This will destroy ALL infrastructure!"
	@read -p "Are you sure? Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ]
	cd infrastructure/terraform && terraform destroy \
		-var="project_id=$(GCP_PROJECT_ID)" \
		-var-file=../environments/prod.tfvars

logs-dataflow: ## Show Dataflow logs
	gcloud dataflow jobs list --region=$(GCP_REGION) --status=active --format="value(id)" | head -1 | xargs -I {} gcloud dataflow jobs show {} --region=$(GCP_REGION)

logs-api: ## Show API logs
	gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=routing-api" \
		--limit 50 --format json --project=$(GCP_PROJECT_ID)

monitor: ## Open monitoring dashboard
	@echo "Opening Cloud Console Monitoring..."
	@open "https://console.cloud.google.com/monitoring/dashboards?project=$(GCP_PROJECT_ID)"

cost-report: ## Show cost estimation
	@echo "Fetching cost data from last 30 days..."
	@gcloud billing accounts list
