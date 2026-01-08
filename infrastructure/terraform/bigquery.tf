# Dataset principal
resource "google_bigquery_dataset" "cdn_analytics" {
  dataset_id  = "cdn_analytics"
  description = "Dataset principal pour analytics CDN/Télécom"
  location    = "EU"
  
  # Rétention par défaut: 90 jours
  default_table_expiration_ms = 7776000000
  
  labels = {
    environment = var.environment
    project     = "cdn-analytics"
  }
  
  depends_on = [google_project_service.required_apis]
}

# Table principale: métriques QoS agrégées par fenêtre de 5 minutes
resource "google_bigquery_table" "qos_metrics_5min" {
  dataset_id = google_bigquery_dataset.cdn_analytics.dataset_id
  table_id   = "qos_metrics_5min"
  
  description = "Métriques QoS agrégées par fenêtre de 5 minutes"
  
  # Partitioning par jour pour optimiser les queries
  time_partitioning {
    type          = "DAY"
    field         = "window_start"
    expiration_ms = 7776000000 # 90 jours
  }
  
  # Clustering pour filtres fréquents
  clustering = ["pop", "country", "cache_status"]
  
  schema = jsonencode([
    {
      name = "window_start"
      type = "TIMESTAMP"
      mode = "REQUIRED"
      description = "Début de la fenêtre temporelle"
    },
    {
      name = "window_end"
      type = "TIMESTAMP"
      mode = "REQUIRED"
      description = "Fin de la fenêtre temporelle"
    },
    {
      name = "pop"
      type = "STRING"
      mode = "REQUIRED"
      description = "Point of Presence ID"
    },
    {
      name = "datacenter"
      type = "STRING"
      mode = "NULLABLE"
      description = "Datacenter location"
    },
    {
      name = "country"
      type = "STRING"
      mode = "NULLABLE"
      description = "Code pays ISO (client)"
    },
    {
      name = "city"
      type = "STRING"
      mode = "NULLABLE"
      description = "Ville (client)"
    },
    {
      name = "asn"
      type = "INT64"
      mode = "NULLABLE"
      description = "Autonomous System Number"
    },
    {
      name = "isp"
      type = "STRING"
      mode = "NULLABLE"
      description = "Internet Service Provider"
    },
    {
      name = "avg_response_time_ms"
      type = "FLOAT64"
      mode = "REQUIRED"
      description = "Temps de réponse moyen en ms"
    },
    {
      name = "p50_response_time_ms"
      type = "FLOAT64"
      mode = "NULLABLE"
      description = "Percentile 50 du temps de réponse"
    },
    {
      name = "p95_response_time_ms"
      type = "FLOAT64"
      mode = "NULLABLE"
      description = "Percentile 95 du temps de réponse"
    },
    {
      name = "p99_response_time_ms"
      type = "FLOAT64"
      mode = "NULLABLE"
      description = "Percentile 99 du temps de réponse"
    },
    {
      name = "total_requests"
      type = "INT64"
      mode = "REQUIRED"
      description = "Nombre total de requêtes"
    },
    {
      name = "error_count"
      type = "INT64"
      mode = "REQUIRED"
      description = "Nombre d'erreurs (status 5xx)"
    },
    {
      name = "error_4xx_count"
      type = "INT64"
      mode = "NULLABLE"
      description = "Nombre d'erreurs 4xx"
    },
    {
      name = "cache_hit_count"
      type = "INT64"
      mode = "REQUIRED"
      description = "Nombre de cache hits"
    },
    {
      name = "cache_miss_count"
      type = "INT64"
      mode = "NULLABLE"
      description = "Nombre de cache miss"
    },
    {
      name = "cache_status"
      type = "STRING"
      mode = "NULLABLE"
      description = "Status du cache (HIT, MISS, BYPASS)"
    },
    {
      name = "total_bytes_sent"
      type = "INT64"
      mode = "REQUIRED"
      description = "Total bytes envoyés"
    },
    {
      name = "total_bytes_received"
      type = "INT64"
      mode = "NULLABLE"
      description = "Total bytes reçus"
    },
    {
      name = "avg_bandwidth_mbps"
      type = "FLOAT64"
      mode = "NULLABLE"
      description = "Bande passante moyenne en Mbps"
    }
  ])
  
  labels = {
    table_type = "metrics"
    granularity = "5min"
  }
}

# Table pour logs bruts (optionnel, pour debugging)
resource "google_bigquery_table" "cdn_logs_raw" {
  dataset_id = google_bigquery_dataset.cdn_analytics.dataset_id
  table_id   = "cdn_logs_raw"
  
  description = "Logs CDN bruts (échantillon pour debugging)"
  
  time_partitioning {
    type          = "DAY"
    field         = "timestamp"
    expiration_ms = 604800000 # 7 jours seulement
  }
  
  clustering = ["pop", "status_code"]
  
  schema = jsonencode([
    {
      name = "timestamp"
      type = "TIMESTAMP"
      mode = "REQUIRED"
    },
    {
      name = "pop"
      type = "STRING"
      mode = "REQUIRED"
    },
    {
      name = "client_ip"
      type = "STRING"
      mode = "REQUIRED"
    },
    {
      name = "request_method"
      type = "STRING"
      mode = "NULLABLE"
    },
    {
      name = "request_uri"
      type = "STRING"
      mode = "NULLABLE"
    },
    {
      name = "status_code"
      type = "INT64"
      mode = "REQUIRED"
    },
    {
      name = "response_time_ms"
      type = "FLOAT64"
      mode = "REQUIRED"
    },
    {
      name = "bytes_sent"
      type = "INT64"
      mode = "NULLABLE"
    },
    {
      name = "cache_status"
      type = "STRING"
      mode = "NULLABLE"
    },
    {
      name = "user_agent"
      type = "STRING"
      mode = "NULLABLE"
    }
  ])
}

# Table pour anomalies détectées
resource "google_bigquery_table" "anomalies" {
  dataset_id = google_bigquery_dataset.cdn_analytics.dataset_id
  table_id   = "anomalies"
  
  description = "Anomalies détectées dans le trafic CDN"
  
  time_partitioning {
    type          = "DAY"
    field         = "detected_at"
    expiration_ms = 15552000000 # 180 jours
  }
  
  clustering = ["severity", "pop", "anomaly_type"]
  
  schema = jsonencode([
    {
      name = "detected_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
    },
    {
      name = "pop"
      type = "STRING"
      mode = "REQUIRED"
    },
    {
      name = "anomaly_type"
      type = "STRING"
      mode = "REQUIRED"
      description = "Type: latency, errors, traffic_spike, ddos"
    },
    {
      name = "severity"
      type = "STRING"
      mode = "REQUIRED"
      description = "Severité: warning, critical"
    },
    {
      name = "current_value"
      type = "FLOAT64"
      mode = "REQUIRED"
    },
    {
      name = "baseline_value"
      type = "FLOAT64"
      mode = "REQUIRED"
    },
    {
      name = "z_score"
      type = "FLOAT64"
      mode = "NULLABLE"
    },
    {
      name = "confidence"
      type = "FLOAT64"
      mode = "NULLABLE"
    },
    {
      name = "description"
      type = "STRING"
      mode = "NULLABLE"
    },
    {
      name = "resolved_at"
      type = "TIMESTAMP"
      mode = "NULLABLE"
    }
  ])
}

# Outputs
output "bigquery_dataset_id" {
  value = google_bigquery_dataset.cdn_analytics.dataset_id
}

output "qos_metrics_table_id" {
  value = google_bigquery_table.qos_metrics_5min.table_id
}

output "anomalies_table_id" {
  value = google_bigquery_table.anomalies.table_id
}
