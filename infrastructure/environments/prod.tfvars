# Production Environment Configuration

project_id  = "your-gcp-project-id"
region      = "europe-west1"
zone        = "europe-west1-b"
environment = "prod"

# Dataflow
dataflow_num_workers = 20
dataflow_max_workers = 100

# Bigtable
bigtable_num_nodes = 10

# Memorystore
memorystore_size_gb = 20

# GKE
gke_node_count = 5

# Alerting (à remplacer par vos vraies valeurs)
pagerduty_service_key = "your-pagerduty-service-key"
slack_webhook_url     = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
