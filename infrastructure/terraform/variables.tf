variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "europe-west1"
}

variable "zone" {
  description = "GCP Zone"
  type        = string
  default     = "europe-west1-b"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "dataflow_num_workers" {
  description = "Nombre initial de workers Dataflow"
  type        = number
  default     = 20
}

variable "dataflow_max_workers" {
  description = "Nombre maximum de workers Dataflow"
  type        = number
  default     = 100
}

variable "bigtable_num_nodes" {
  description = "Nombre de nodes Bigtable par cluster"
  type        = number
  default     = 10
}

variable "memorystore_size_gb" {
  description = "Taille Memorystore Redis en GB"
  type        = number
  default     = 20
}

variable "gke_node_count" {
  description = "Nombre de nodes GKE"
  type        = number
  default     = 3
}

variable "pagerduty_service_key" {
  description = "PagerDuty service key pour alertes"
  type        = string
  sensitive   = true
}

variable "slack_webhook_url" {
  description = "Slack webhook URL pour notifications"
  type        = string
  sensitive   = true
}

variable "enable_apis" {
  description = "Liste des APIs GCP à activer"
  type        = list(string)
  default = [
    "pubsub.googleapis.com",
    "dataflow.googleapis.com",
    "bigquery.googleapis.com",
    "bigtable.googleapis.com",
    "bigtableadmin.googleapis.com",
    "redis.googleapis.com",
    "container.googleapis.com",
    "aiplatform.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "storage.googleapis.com",
    "compute.googleapis.com"
  ]
}
