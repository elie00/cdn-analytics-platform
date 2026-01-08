# Architecture Détaillée - CDN Analytics Platform

## Vue d'ensemble

Cette plateforme Big Data traite **5 TB/jour** de données de télémétrie CDN/réseau avec une latence **< 30 secondes** (near real-time) sur Google Cloud Platform.

## Architecture en Couches

### 1. Couche Ingestion

**Technologies**: Google Cloud Pub/Sub + Fluentd/Telegraf

#### Composants:
- **Fluentd agents**: Déployés sur chaque edge server CDN
  - Collecte logs Nginx (access + error)
  - Enrichissement basique à la source
  - Compression gzip + batching (1000 msgs/batch)
  - Buffer disque pour haute disponibilité
  
- **Telegraf agents**: Monitoring infrastructure
  - Métriques système (CPU, RAM, disk, network)
  - Métriques réseau (latence, bande passante, packet loss)
  - Health checks vers origins
  
- **Pub/Sub Topics**:
  - `cdn-logs-topic`: Logs d'accès CDN (500K+ msg/sec)
  - `network-metrics-topic`: Métriques réseau (100K+ msg/sec)
  - `events-topic`: Événements infrastructure
  - `dlq-topic`: Dead letter queue

**Optimisations**:
- Exactly-once delivery
- Multi-région replication (EU + US)
- Retry exponentiel avec backoff
- Métriques Prometheus intégrées

### 2. Couche ETL/Processing

**Technologies**: Apache Beam + Google Cloud Dataflow

#### Pipeline d'Enrichissement (`enrichment_pipeline.py`)

```
Pub/Sub → Parse → Enrich (GeoIP) → Window → Aggregate
                                         ├─→ Bigtable (1min)
                                         └─→ BigQuery (5min)
```

**Étapes**:
1. **Parse**: Validation et parsing JSON
2. **Enrich**: 
   - Lookup GeoIP local (MaxMind)
   - Ajout country, city, lat/lon, ASN, ISP
3. **Window**:
   - Fixed 1min pour hot data (Bigtable)
   - Fixed 5min pour analytics (BigQuery)
4. **Aggregate**: Calcul métriques QoS par POP/pays
   - Avg, P50, P95, P99 latency
   - Error rates, cache hit rates
   - Volume, bande passante

**Configuration**:
- Workers: 20-100 (autoscaling throughput-based)
- Machine type: n2-standard-4
- Streaming Engine enabled

#### Pipeline Détection d'Anomalies (`anomaly_detection_pipeline.py`)

```
Métriques → Calculate Baseline → Detect Anomalies → BigQuery
                (30min sliding)      (z-score > 3)
```

**Méthodes**:
- Z-score statistique (baseline mobile 30min)
- Détection traffic spikes (potentiel DDoS)
- Alerting via Cloud Monitoring

### 3. Couche Stockage Multi-Tier

#### Bigtable - Hot Data (temps réel)

**Configuration**:
- 2 clusters (EU + US) pour replication
- 10 nodes par cluster avec autoscaling
- SSD storage

**Schéma**:
```
Table: cdn_realtime_metrics
Row Key: {pop}#{reverse_timestamp}#{metric_type}
Column Families:
  - stats (TTL: 1h): Métriques agrégées
  - raw (TTL: 15min): Données brutes
  - geo (TTL: 1h): Données géographiques
```

**Reverse timestamp**: `9999999999999 - timestamp` pour scan récent efficient

**Performance**: < 10ms P95 read latency

#### BigQuery - Data Warehouse

**Configuration**:
- Location: EU
- Partitioning: DAY sur `window_start`
- Clustering: `[pop, country, cache_status]`
- Expiration: 90 jours automatique

**Tables principales**:
- `qos_metrics_5min`: Métriques agrégées 5min
- `cdn_logs_raw`: Logs bruts échantillonnés (7j)
- `anomalies`: Anomalies détectées (180j)

**Vues matérialisées** (refresh auto):
- `hourly_pop_performance`: Perf horaire par POP
- `hourly_country_performance`: Perf par pays
- `daily_trends`: Tendances journalières

**Performance**: Queries < 5 sec avec partitioning/clustering

#### Memorystore Redis - Cache API

**Configuration**:
- Tier: STANDARD_HA (réplication)
- Taille: 20 GB
- Policy: allkeys-lru

**Usage**:
- Cache résultats API (TTL: 30-60s)
- Cache décisions routage intelligent
- < 5ms latency

#### Cloud Storage - Cold Storage

**Configuration**:
- Standard → Coldline (90j) → Archive (1 an)
- Lifecycle policies automatiques

### 4. Couche Analytics & ML

#### BigQuery ML

**Modèles**:
1. **load_forecast_model** (ARIMA_PLUS):
   - Prévision charge 24h par POP
   - Training: 90 jours historique
   - Refresh: quotidien

2. **anomaly_classifier_model** (Logistic Regression):
   - Classification anomalies (normal vs critique)
   - Features: latency, error rate, traffic patterns
   - Accuracy: > 90%

#### Vertex AI

**Use cases**:
- Détection d'anomalies avancée (Isolation Forest)
- Clustering POPs par comportement
- Prédiction pannes infrastructure

### 5. Couche Visualisation

#### Grafana - Monitoring Temps Réel

**Dashboards**:
- NOC Real-time: Carte monde, métriques live
- POP Performance: Détails par POP
- Anomalies: Alertes actives

**Data sources**:
- Bigtable (temps réel)
- BigQuery (historique)
- Prometheus (métriques système)

**Refresh**: 10 secondes

#### Looker Studio - Analytics Business

**Rapports**:
- Executive Summary (KPIs mensuels)
- Performance par région/pays
- Analyse coûts bande passante
- Trends et comparaisons

**Data source**: BigQuery (vues matérialisées)

### 6. Couche API

**Technologies**: Flask + Gunicorn sur Cloud Run

**Endpoints**:
- `GET /api/v1/best-pop`: Routage intelligent
  - Input: client_ip, content_type
  - Output: Meilleur POP basé sur performance temps réel
  - Cache: 30s Redis

- `GET /api/v1/metrics/pop/{pop_id}`: Métriques POP
  - Source: Bigtable
  - Cache: 10s

- `GET /api/v1/anomalies`: Anomalies récentes
  - Source: BigQuery
  - Filtres: severity, hours

- `GET /api/v1/stats/global`: Stats globales CDN

**Performance**:
- P95 latency: < 50ms
- Cache hit rate: > 80%
- Autoscaling: 2-20 instances

## Flux de Données

### Flux Principal (Happy Path)

```
Edge Server (Nginx)
    ↓
Fluentd Agent (batching + compression)
    ↓
Pub/Sub Topic (cdn-logs-topic)
    ↓
Dataflow Enrichment Pipeline
    ├─→ Bigtable (hot data, 1min window)
    │   └─→ API (routage intelligent)
    │       └─→ Client
    │
    └─→ BigQuery (analytics, 5min window)
        ├─→ Materialized Views
        ├─→ BigQuery ML Models
        └─→ Dashboards (Grafana/Looker)
```

### Flux Détection Anomalies

```
BigQuery (qos_metrics_5min)
    ↓
Dataflow Anomaly Detection Pipeline
    ├─→ Calculate Baseline (30min sliding)
    ├─→ Detect Anomalies (z-score)
    └─→ BigQuery (anomalies table)
        └─→ Cloud Monitoring Alerts
            ├─→ PagerDuty (critical)
            └─→ Slack (warning)
```

## Haute Disponibilité

### Resilience

- **Pub/Sub**: Multi-région, retry automatique, DLQ
- **Dataflow**: Auto-healing workers, checkpoint réguliers
- **Bigtable**: Multi-cluster replication, 99.99% SLA
- **Cloud Run**: Multi-zone, health checks, auto-restart

### Disaster Recovery

- **RTO**: < 1 heure
- **RPO**: < 5 minutes
- **Backups**: 
  - BigQuery: 7 jours automatique
  - Bigtable: Snapshots quotidiens
  - Cloud Storage: Versioning activé

## Sécurité

### IAM

- Service accounts dédiés par composant
- Principe du moindre privilège
- Rotation clés automatique (Secret Manager)

### Network

- VPC peering inter-services
- Cloud Armor (protection DDoS)
- Private Service Connect pour Bigtable/Memorystore

### Encryption

- At-rest: Automatique (Google-managed keys)
- In-transit: TLS 1.3
- Application-level: Sensitive data masking

### Audit

- Cloud Audit Logs activés
- Data Access logs pour BigQuery
- Alerting accès inhabituels

## Monitoring & Observability

### Métriques Système

- **Pub/Sub**: Backlog, publish/subscribe rates
- **Dataflow**: Worker CPU/memory, throughput, latency
- **Bigtable**: CPU load, latency, storage
- **BigQuery**: Slot utilization, query performance
- **API**: Request rate, latency, error rate

### SLIs/SLOs

| Service | SLI | SLO | Alerting |
|---------|-----|-----|----------|
| Ingestion | Pub/Sub lag | < 1M msgs | Critical if > 5M |
| Processing | End-to-end latency | < 30s P95 | Warning if > 60s |
| API | Availability | 99.9% | Critical if < 99% |
| API | Latency | < 50ms P95 | Warning if > 100ms |

### Alertes

- **Critical**: PagerDuty + Slack
- **Warning**: Slack
- **Info**: Email

### Logs

- Centralisés dans Cloud Logging
- Rétention: 30 jours
- Export vers BigQuery pour analytics long-terme

## Scalabilité

### Scaling Horizontal

- **Dataflow**: Autoscaling 20-100 workers
- **Bigtable**: Autoscaling 10-30 nodes par cluster
- **API**: Cloud Run autoscaling 2-20 instances

### Limites Actuelles

- Pub/Sub: 2M msg/sec par topic (largement suffisant)
- Dataflow: 100 workers max (peut être augmenté)
- Bigtable: 10K QPS/node (300K+ QPS total)
- BigQuery: 2000 slots réservés

### Évolution Future

- **10 TB/jour**: Doubler workers Dataflow + nodes Bigtable
- **50 TB/jour**: Sharding Bigtable tables + BigQuery reservations
- **100+ TB/jour**: Considérer architecture hybride multi-cloud
