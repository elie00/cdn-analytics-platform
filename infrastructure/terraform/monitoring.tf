# Notification channels
resource "google_monitoring_notification_channel" "pagerduty" {
  display_name = "PagerDuty"
  type         = "pagerduty"
  
  labels = {
    service_key = var.pagerduty_service_key
  }
  
  enabled = true
}

resource "google_monitoring_notification_channel" "slack" {
  display_name = "Slack CDN Alerts"
  type         = "slack"
  
  labels = {
    channel_name = "#cdn-alerts"
    url          = var.slack_webhook_url
  }
  
  enabled = true
}

resource "google_monitoring_notification_channel" "email" {
  display_name = "Email Oncall"
  type         = "email"
  
  labels = {
    email_address = "oncall@example.com"
  }
  
  enabled = true
}

# Alert: High Latency
resource "google_monitoring_alert_policy" "high_latency" {
  display_name = "CDN High Latency Alert"
  combiner     = "OR"
  enabled      = true
  
  conditions {
    display_name = "Average latency > 500ms for 5 minutes"
    
    condition_threshold {
      filter          = "resource.type=\"bigtable_table\" AND metric.type=\"custom.googleapis.com/cdn/avg_latency_ms\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 500
      
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_MEAN"
        group_by_fields      = ["resource.pop"]
      }
    }
  }
  
  notification_channels = [
    google_monitoring_notification_channel.pagerduty.id,
    google_monitoring_notification_channel.slack.id
  ]
  
  alert_strategy {
    auto_close = "86400s"
    
    notification_rate_limit {
      period = "300s"
    }
  }
  
  documentation {
    content   = "Average CDN latency exceeded 500ms. Check POP performance in Grafana dashboard."
    mime_type = "text/markdown"
  }
}

# Alert: High Error Rate
resource "google_monitoring_alert_policy" "high_error_rate" {
  display_name = "CDN High Error Rate"
  combiner     = "OR"
  enabled      = true
  
  conditions {
    display_name = "Error rate > 5% for 5 minutes"
    
    condition_threshold {
      filter          = "resource.type=\"bigtable_table\" AND metric.type=\"custom.googleapis.com/cdn/error_rate\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05
      
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_MEAN"
        group_by_fields      = ["resource.pop"]
      }
    }
  }
  
  notification_channels = [
    google_monitoring_notification_channel.pagerduty.id,
    google_monitoring_notification_channel.slack.id
  ]
  
  alert_strategy {
    auto_close = "86400s"
  }
  
  documentation {
    content   = "CDN error rate exceeded 5%. Investigate origin health and POP status."
    mime_type = "text/markdown"
  }
}

# Alert: Dataflow High Backlog
resource "google_monitoring_alert_policy" "dataflow_backlog" {
  display_name = "Dataflow High Backlog"
  combiner     = "OR"
  enabled      = true
  
  conditions {
    display_name = "Pub/Sub backlog > 1M messages"
    
    condition_threshold {
      filter          = "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 1000000
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }
  
  notification_channels = [
    google_monitoring_notification_channel.pagerduty.id
  ]
  
  alert_strategy {
    auto_close = "86400s"
  }
  
  documentation {
    content   = "Pub/Sub subscription backlog exceeded 1M messages. Check Dataflow job scaling and health."
    mime_type = "text/markdown"
  }
}

# Alert: Bigtable CPU High
resource "google_monitoring_alert_policy" "bigtable_cpu" {
  display_name = "Bigtable High CPU Usage"
  combiner     = "OR"
  enabled      = true
  
  conditions {
    display_name = "Bigtable CPU > 80% for 10 minutes"
    
    condition_threshold {
      filter          = "resource.type=\"bigtable_cluster\" AND metric.type=\"bigtable.googleapis.com/cluster/cpu_load\""
      duration        = "600s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.80
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }
  
  notification_channels = [
    google_monitoring_notification_channel.slack.id,
    google_monitoring_notification_channel.email.id
  ]
  
  alert_strategy {
    auto_close = "86400s"
  }
  
  documentation {
    content   = "Bigtable cluster CPU usage > 80%. Consider scaling up nodes."
    mime_type = "text/markdown"
  }
}

# Alert: BigQuery Slot Utilization
resource "google_monitoring_alert_policy" "bigquery_slots" {
  display_name = "BigQuery High Slot Usage"
  combiner     = "OR"
  enabled      = true
  
  conditions {
    display_name = "Slot utilization > 90%"
    
    condition_threshold {
      filter          = "resource.type=\"bigquery_project\" AND metric.type=\"bigquery.googleapis.com/slots/total_allocated\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 1800 # Assuming 2000 slots reservation
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }
  
  notification_channels = [
    google_monitoring_notification_channel.slack.id
  ]
  
  alert_strategy {
    auto_close = "86400s"
  }
}

# Alert: Anomaly Detected
resource "google_monitoring_alert_policy" "anomaly_detected" {
  display_name = "CDN Anomaly Detected"
  combiner     = "OR"
  enabled      = true
  
  conditions {
    display_name = "Critical anomaly detected"
    
    condition_threshold {
      filter          = "resource.type=\"global\" AND metric.type=\"custom.googleapis.com/cdn/anomaly/critical\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
  
  notification_channels = [
    google_monitoring_notification_channel.pagerduty.id,
    google_monitoring_notification_channel.slack.id
  ]
  
  alert_strategy {
    auto_close = "3600s"
  }
  
  documentation {
    content   = "Critical anomaly detected in CDN traffic. Check Grafana for details."
    mime_type = "text/markdown"
  }
}

# Uptime check pour API
resource "google_monitoring_uptime_check_config" "api_health" {
  display_name = "CDN API Health Check"
  timeout      = "10s"
  period       = "60s"
  
  http_check {
    path           = "/health"
    port           = 8080
    request_method = "GET"
    
    accepted_response_status_codes {
      status_class = "STATUS_CLASS_2XX"
    }
  }
  
  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = "cdn-api.example.com"
    }
  }
  
  content_matchers {
    content = "healthy"
    matcher = "CONTAINS_STRING"
  }
}

# Dashboard SLO
resource "google_monitoring_slo" "availability_slo" {
  service      = "cdn-api-service"
  slo_id       = "availability-slo"
  display_name = "99.9% Availability SLO"
  
  goal                = 0.999
  rolling_period_days = 30
  
  request_based_sli {
    good_total_ratio {
      good_service_filter = join(" AND ", [
        "metric.type=\"serviceruntime.googleapis.com/api/request_count\"",
        "metric.label.response_code_class=\"2xx\""
      ])
      
      total_service_filter = "metric.type=\"serviceruntime.googleapis.com/api/request_count\""
    }
  }
}

# Outputs
output "pagerduty_channel_id" {
  value = google_monitoring_notification_channel.pagerduty.id
}

output "slack_channel_id" {
  value = google_monitoring_notification_channel.slack.id
}
