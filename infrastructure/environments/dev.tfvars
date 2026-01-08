# Development Environment Configuration

project_id  = "your-gcp-project-id-dev"
region      = "europe-west1"
zone        = "europe-west1-b"
environment = "dev"

# Dataflow - Configuration réduite pour dev
dataflow_num_workers = 2
dataflow_max_workers = 10

# Bigtable - Configuration minimale
bigtable_num_nodes = 3

# Memorystore
memorystore_size_gb = 5

# GKE
gke_node_count = 2

# Alerting
pagerduty_service_key = "dev-pagerduty-key"
slack_webhook_url     = "https://hooks.slack.com/services/DEV/WEBHOOK/URL"
