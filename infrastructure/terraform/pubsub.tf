# Topic pour logs CDN
resource "google_pubsub_topic" "cdn_logs" {
  name = "cdn-logs-topic"
  
  message_retention_duration = "3600s" # 1 heure
  
  message_storage_policy {
    allowed_persistence_regions = [
      var.region,
      "us-central1"  # Multi-région pour haute disponibilité
    ]
  }
  
  depends_on = [google_project_service.required_apis]
}

# Topic pour métriques réseau
resource "google_pubsub_topic" "network_metrics" {
  name = "network-metrics-topic"
  
  message_retention_duration = "3600s"
  
  message_storage_policy {
    allowed_persistence_regions = [var.region, "us-central1"]
  }
  
  depends_on = [google_project_service.required_apis]
}

# Topic pour événements infrastructure
resource "google_pubsub_topic" "events" {
  name = "events-topic"
  
  message_retention_duration = "7200s" # 2 heures pour events
  
  message_storage_policy {
    allowed_persistence_regions = [var.region, "us-central1"]
  }
  
  depends_on = [google_project_service.required_apis]
}

# Dead Letter Queue
resource "google_pubsub_topic" "dlq" {
  name = "dlq-topic"
  
  message_retention_duration = "86400s" # 24 heures
  
  depends_on = [google_project_service.required_apis]
}

# Subscription pour pipeline Dataflow d'enrichissement
resource "google_pubsub_subscription" "cdn_logs_dataflow" {
  name  = "cdn-logs-dataflow-sub"
  topic = google_pubsub_topic.cdn_logs.name
  
  ack_deadline_seconds = 60
  
  # Exactly-once delivery pour cohérence des données
  enable_exactly_once_delivery = true
  
  # Message ordering désactivé pour meilleure performance
  enable_message_ordering = false
  
  # Politique de retry exponentiel
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
  
  # Dead letter queue pour messages problématiques
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dlq.id
    max_delivery_attempts = 5
  }
  
  expiration_policy {
    ttl = "" # Pas d'expiration
  }
}

resource "google_pubsub_subscription" "network_metrics_dataflow" {
  name  = "network-metrics-dataflow-sub"
  topic = google_pubsub_topic.network_metrics.name
  
  ack_deadline_seconds         = 60
  enable_exactly_once_delivery = true
  enable_message_ordering      = false
  
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
  
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dlq.id
    max_delivery_attempts = 5
  }
  
  expiration_policy {
    ttl = ""
  }
}

resource "google_pubsub_subscription" "events_dataflow" {
  name  = "events-dataflow-sub"
  topic = google_pubsub_topic.events.name
  
  ack_deadline_seconds         = 60
  enable_exactly_once_delivery = true
  enable_message_ordering      = false
  
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
  
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dlq.id
    max_delivery_attempts = 5
  }
  
  expiration_policy {
    ttl = ""
  }
}

# Subscription pour monitoring de la DLQ
resource "google_pubsub_subscription" "dlq_monitoring" {
  name  = "dlq-monitoring-sub"
  topic = google_pubsub_topic.dlq.name
  
  ack_deadline_seconds = 600
  
  expiration_policy {
    ttl = ""
  }
}

# Outputs
output "cdn_logs_topic_id" {
  value = google_pubsub_topic.cdn_logs.id
}

output "network_metrics_topic_id" {
  value = google_pubsub_topic.network_metrics.id
}

output "events_topic_id" {
  value = google_pubsub_topic.events.id
}

output "cdn_logs_subscription_id" {
  value = google_pubsub_subscription.cdn_logs_dataflow.id
}
