# Activation des APIs GCP nécessaires
resource "google_project_service" "required_apis" {
  for_each = toset(var.enable_apis)
  
  service            = each.key
  disable_on_destroy = false
  
  # Éviter les problèmes de dépendances
  timeouts {
    create = "30m"
    update = "40m"
  }
}

# Buckets GCS pour staging/temp
resource "google_storage_bucket" "dataflow_temp" {
  name          = "${var.project_id}-dataflow-temp"
  location      = var.region
  force_destroy = false
  
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = 7 # Supprimer fichiers > 7 jours
    }
    action {
      type = "Delete"
    }
  }
  
  depends_on = [google_project_service.required_apis]
}

resource "google_storage_bucket" "dataflow_staging" {
  name          = "${var.project_id}-dataflow-staging"
  location      = var.region
  force_destroy = false
  
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
  
  depends_on = [google_project_service.required_apis]
}

resource "google_storage_bucket" "ml_models" {
  name          = "${var.project_id}-ml-models"
  location      = var.region
  force_destroy = false
  
  uniform_bucket_level_access = true
  
  versioning {
    enabled = true
  }
  
  depends_on = [google_project_service.required_apis]
}

resource "google_storage_bucket" "cold_storage" {
  name          = "${var.project_id}-cold-storage"
  location      = var.region
  storage_class = "COLDLINE"
  force_destroy = false
  
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = 365 # Archiver après 1 an
    }
    action {
      type          = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
  }
  
  depends_on = [google_project_service.required_apis]
}

# Bucket pour Terraform state (créer manuellement avant terraform init)
resource "google_storage_bucket" "terraform_state" {
  name          = "${var.project_id}-terraform-state"
  location      = var.region
  force_destroy = false
  
  uniform_bucket_level_access = true
  
  versioning {
    enabled = true
  }
  
  depends_on = [google_project_service.required_apis]
}

# Outputs
output "dataflow_temp_bucket" {
  value = google_storage_bucket.dataflow_temp.url
}

output "dataflow_staging_bucket" {
  value = google_storage_bucket.dataflow_staging.url
}

output "ml_models_bucket" {
  value = google_storage_bucket.ml_models.url
}

output "cold_storage_bucket" {
  value = google_storage_bucket.cold_storage.url
}
