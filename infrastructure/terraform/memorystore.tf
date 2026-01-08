# Memorystore Redis pour cache API
resource "google_redis_instance" "cache" {
  name           = "cdn-analytics-cache"
  tier           = "STANDARD_HA" # High Availability avec réplication
  memory_size_gb = var.memorystore_size_gb
  region         = var.region
  
  redis_version = "REDIS_7_0"
  display_name  = "CDN Analytics Cache"
  
  # Configuration Redis optimisée pour cache
  redis_configs = {
    # Politique d'éviction: supprimer clés les moins récemment utilisées
    "maxmemory-policy" = "allkeys-lru"
    
    # Timeout connexions inactives
    "timeout" = "300"
    
    # Désactiver persistence (cache uniquement)
    "save" = ""
    
    # Compression
    "lfu-log-factor" = "10"
    "lfu-decay-time" = "1"
  }
  
  # Maintenance window
  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_time {
        hours   = 3
        minutes = 0
        seconds = 0
        nanos   = 0
      }
    }
  }
  
  labels = {
    environment = var.environment
    project     = "cdn-analytics"
    purpose     = "api-cache"
  }
  
  depends_on = [google_project_service.required_apis]
}

# Outputs
output "redis_host" {
  value       = google_redis_instance.cache.host
  description = "Redis instance host"
}

output "redis_port" {
  value       = google_redis_instance.cache.port
  description = "Redis instance port"
}

output "redis_connection_string" {
  value       = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}"
  description = "Redis connection string"
  sensitive   = false
}

output "redis_current_location_id" {
  value = google_redis_instance.cache.current_location_id
}
