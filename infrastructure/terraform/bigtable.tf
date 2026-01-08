# Instance Bigtable avec multi-cluster replication
resource "google_bigtable_instance" "cdn_analytics" {
  name = "cdn-analytics-instance"
  
  # Production instance (pas de mode development)
  deletion_protection = true
  
  # Cluster Europe
  cluster {
    cluster_id   = "cdn-analytics-cluster-eu"
    zone         = var.zone
    num_nodes    = var.bigtable_num_nodes
    storage_type = "SSD"
    
    autoscaling_config {
      min_nodes  = var.bigtable_num_nodes
      max_nodes  = var.bigtable_num_nodes * 3
      cpu_target = 70
    }
  }
  
  # Cluster US pour replication et haute disponibilité
  cluster {
    cluster_id   = "cdn-analytics-cluster-us"
    zone         = "us-central1-a"
    num_nodes    = var.bigtable_num_nodes
    storage_type = "SSD"
    
    autoscaling_config {
      min_nodes  = var.bigtable_num_nodes
      max_nodes  = var.bigtable_num_nodes * 3
      cpu_target = 70
    }
  }
  
  labels = {
    environment = var.environment
    project     = "cdn-analytics"
  }
  
  depends_on = [google_project_service.required_apis]
}

# Table pour métriques temps réel
resource "google_bigtable_table" "cdn_realtime_metrics" {
  name          = "cdn_realtime_metrics"
  instance_name = google_bigtable_instance.cdn_analytics.name
  
  # Split keys pour distribution uniforme
  split_keys = [
    "ams01#",
    "fra01#",
    "lon01#",
    "par01#",
    "nyc01#",
    "sfo01#",
    "sin01#",
    "tok01#"
  ]
  
  column_family {
    family = "stats"
    
    # TTL de 1 heure pour hot data
    gc_rules {
      mode = "union"
      gc_rule {
        max_age {
          duration = "3600s"
        }
      }
      gc_rule {
        max_num_versions = 1
      }
    }
  }
  
  column_family {
    family = "raw"
    
    # TTL de 15 minutes pour données brutes
    gc_rules {
      mode = "union"
      gc_rule {
        max_age {
          duration = "900s"
        }
      }
      gc_rule {
        max_num_versions = 1
      }
    }
  }
  
  column_family {
    family = "geo"
    
    gc_rules {
      mode = "union"
      gc_rule {
        max_age {
          duration = "3600s"
        }
      }
      gc_rule {
        max_num_versions = 1
      }
    }
  }
}

# Table pour baselines de détection d'anomalies
resource "google_bigtable_table" "anomaly_baselines" {
  name          = "anomaly_baselines"
  instance_name = google_bigtable_instance.cdn_analytics.name
  
  column_family {
    family = "baseline"
    
    # Garde dernière version seulement
    gc_rules {
      mode = "union"
      gc_rule {
        max_age {
          duration = "86400s" # 24 heures
        }
      }
      gc_rule {
        max_num_versions = 1
      }
    }
  }
  
  column_family {
    family = "history"
    
    # Garde historique 7 jours
    gc_rules {
      mode = "union"
      gc_rule {
        max_age {
          duration = "604800s"
        }
      }
      gc_rule {
        max_num_versions = 10
      }
    }
  }
}

# Outputs
output "bigtable_instance_name" {
  value = google_bigtable_instance.cdn_analytics.name
}

output "bigtable_realtime_table_name" {
  value = google_bigtable_table.cdn_realtime_metrics.name
}

output "bigtable_connection_string" {
  value = "projects/${var.project_id}/instances/${google_bigtable_instance.cdn_analytics.name}/tables/${google_bigtable_table.cdn_realtime_metrics.name}"
}
