# Service Account pour Dataflow
resource "google_service_account" "dataflow_sa" {
  account_id   = "dataflow-worker-sa"
  display_name = "Dataflow Worker Service Account"
  description  = "Service account pour workers Dataflow"
}

# Permissions Dataflow
resource "google_project_iam_member" "dataflow_worker" {
  project = var.project_id
  role    = "roles/dataflow.worker"
  member  = "serviceAccount:${google_service_account.dataflow_sa.email}"
}

resource "google_project_iam_member" "dataflow_bigquery" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.dataflow_sa.email}"
}

resource "google_project_iam_member" "dataflow_bigtable" {
  project = var.project_id
  role    = "roles/bigtable.user"
  member  = "serviceAccount:${google_service_account.dataflow_sa.email}"
}

resource "google_project_iam_member" "dataflow_pubsub_subscriber" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.dataflow_sa.email}"
}

resource "google_project_iam_member" "dataflow_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.dataflow_sa.email}"
}

# Service Account pour API
resource "google_service_account" "api_sa" {
  account_id   = "cdn-api-sa"
  display_name = "CDN API Service Account"
  description  = "Service account pour API de routage"
}

# Permissions API
resource "google_project_iam_member" "api_bigtable_reader" {
  project = var.project_id
  role    = "roles/bigtable.reader"
  member  = "serviceAccount:${google_service_account.api_sa.email}"
}

resource "google_project_iam_member" "api_bigquery_reader" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.api_sa.email}"
}

resource "google_project_iam_member" "api_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.api_sa.email}"
}

# Service Account pour agents d'ingestion
resource "google_service_account" "ingestion_sa" {
  account_id   = "ingestion-agent-sa"
  display_name = "Ingestion Agent Service Account"
  description  = "Service account pour agents Fluentd/Telegraf"
}

# Permissions Ingestion
resource "google_project_iam_member" "ingestion_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.ingestion_sa.email}"
}

resource "google_project_iam_member" "ingestion_monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.ingestion_sa.email}"
}

# Service Account pour ML (Vertex AI)
resource "google_service_account" "ml_sa" {
  account_id   = "ml-training-sa"
  display_name = "ML Training Service Account"
  description  = "Service account pour entraînement modèles ML"
}

# Permissions ML
resource "google_project_iam_member" "ml_vertex_ai" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.ml_sa.email}"
}

resource "google_project_iam_member" "ml_bigquery" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.ml_sa.email}"
}

resource "google_project_iam_member" "ml_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.ml_sa.email}"
}

# Outputs
output "dataflow_service_account_email" {
  value = google_service_account.dataflow_sa.email
}

output "api_service_account_email" {
  value = google_service_account.api_sa.email
}

output "ingestion_service_account_email" {
  value = google_service_account.ingestion_sa.email
}

output "ml_service_account_email" {
  value = google_service_account.ml_sa.email
}
