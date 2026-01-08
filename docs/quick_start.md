# Guide de Démarrage Rapide

## 🚀 Déploiement en 10 minutes

Ce guide vous permet de déployer une version minimale de la plateforme pour tester rapidement.

### Prérequis

- Compte Google Cloud Platform avec billing activé
- `gcloud` CLI installé et configuré
- `terraform` >= 1.5.0 installé
- `python` 3.11+ installé

### Étape 1: Configuration (2 min)

```bash
# Clone repository
git clone https://github.com/your-org/cdn-analytics-platform.git
cd cdn-analytics-platform

# Configuration GCP
export GCP_PROJECT_ID="votre-projet-id"
gcloud config set project $GCP_PROJECT_ID
gcloud auth application-default login

# Setup Python
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Étape 2: Déploiement Infrastructure (5 min)

```bash
# Utiliser Makefile pour déploiement rapide
make GCP_PROJECT_ID=$GCP_PROJECT_ID deploy-infra
```

Ou manuellement:

```bash
# Terraform
cd infrastructure/terraform
terraform init
terraform apply -var="project_id=$GCP_PROJECT_ID" -auto-approve
```

### Étape 3: Déploiement SQL & ML (1 min)

```bash
make GCP_PROJECT_ID=$GCP_PROJECT_ID deploy-sql
```

### Étape 4: Génération de Données Test (30 sec)

```bash
# Script de génération de trafic simulé
python scripts/generate_test_data.py \
  --project $GCP_PROJECT_ID \
  --duration 60 \
  --rate 100
```

### Étape 5: Vérification (1 min)

```bash
# Vérifier que tout fonctionne
make GCP_PROJECT_ID=$GCP_PROJECT_ID verify

# Vérifier données dans BigQuery
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) FROM \`${GCP_PROJECT_ID}.cdn_analytics.qos_metrics_5min\`"
```

## 🎯 Prochaines Étapes

### Déployer les Pipelines Dataflow

```bash
make GCP_PROJECT_ID=$GCP_PROJECT_ID deploy-dataflow
```

### Déployer l'API

```bash
make GCP_PROJECT_ID=$GCP_PROJECT_ID deploy-api
```

### Accéder aux Dashboards

```bash
# Ouvrir monitoring
make GCP_PROJECT_ID=$GCP_PROJECT_ID monitor
```

## 📊 Visualiser les Données

### BigQuery Console

```bash
# Ouvrir BigQuery
open "https://console.cloud.google.com/bigquery?project=${GCP_PROJECT_ID}"
```

Requêtes utiles:

```sql
-- Vue d'ensemble dernière heure
SELECT
  pop,
  COUNT(*) as measurements,
  AVG(avg_response_time_ms) as avg_latency,
  SUM(total_requests) as total_requests
FROM `cdn_analytics.qos_metrics_5min`
WHERE window_start >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
GROUP BY pop
ORDER BY total_requests DESC;

-- Anomalies récentes
SELECT *
FROM `cdn_analytics.anomalies`
WHERE detected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
ORDER BY detected_at DESC
LIMIT 10;
```

### API Tests

```bash
# Obtenir URL de l'API
API_URL=$(gcloud run services describe routing-api --region=europe-west1 --format='value(status.url)')

# Health check
curl $API_URL/health | jq

# Meilleur POP pour une IP
curl "$API_URL/api/v1/best-pop?client_ip=8.8.8.8" | jq

# Statistiques globales
curl "$API_URL/api/v1/stats/global" | jq
```

## 🧹 Nettoyage

Pour supprimer toutes les ressources:

```bash
make GCP_PROJECT_ID=$GCP_PROJECT_ID destroy
```

⚠️ **Attention**: Ceci supprimera toutes les données et ressources!

## 📚 Documentation Complète

- [Architecture](architecture.md)
- [Déploiement Production](deployment.md)
- [Optimisations Performance](performance.md)
- [Monitoring](monitoring.md)

## 🆘 Support

Problèmes courants:

**1. Quotas insuffisants**
```bash
# Vérifier quotas
gcloud compute project-info describe --project=$GCP_PROJECT_ID
```

**2. APIs non activées**
```bash
# Activer toutes les APIs
gcloud services enable \
  pubsub.googleapis.com \
  dataflow.googleapis.com \
  bigquery.googleapis.com \
  bigtable.googleapis.com
```

**3. Permissions manquantes**
```bash
# Vérifier permissions
gcloud projects get-iam-policy $GCP_PROJECT_ID
```

## 💰 Estimation des Coûts

Pour cette configuration minimale de test:
- **~$50-100/jour** pendant les tests
- Penser à **arrêter/supprimer** les ressources après tests

Ressources les plus coûteuses:
1. Bigtable (SSD, multi-cluster)
2. Dataflow (workers continus)
3. BigQuery (requêtes + stockage)

## 🎓 Tutoriels

### Ajouter un Nouveau POP

```bash
# 1. Mettre à jour la configuration
vim api/routing_service.py  # Ajouter dans POP_REGIONS

# 2. Redéployer API
make deploy-api

# 3. Configurer agents sur nouveau serveur
# Voir docs/deployment.md section "Configuration Agents"
```

### Créer un Dashboard Personnalisé

```bash
# 1. Éditer dashboard Grafana
vim dashboards/grafana/custom_dashboard.json

# 2. Importer via API
curl -X POST http://grafana-url/api/dashboards/db \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -d @dashboards/grafana/custom_dashboard.json
```

### Ajouter une Nouvelle Métrique

```sql
-- 1. Créer nouvelle colonne dans BigQuery
ALTER TABLE `cdn_analytics.qos_metrics_5min`
ADD COLUMN new_metric FLOAT64;

-- 2. Mettre à jour pipeline Dataflow
vim pipelines/dataflow/enrichment_pipeline.py

-- 3. Redéployer
make deploy-dataflow
```

---

**Bon déploiement! 🚀**
