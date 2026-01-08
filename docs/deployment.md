# Guide de Déploiement

## Prérequis

### Outils Requis

- **Google Cloud SDK** >= 450.0.0
- **Terraform** >= 1.5.0
- **Python** 3.11+
- **Docker** >= 24.0.0
- **kubectl** >= 1.28.0
- **git**

### Accès GCP

```bash
# Authentication
gcloud auth login
gcloud auth application-default login

# Configuration projet
export GCP_PROJECT_ID="votre-projet-id"
export GCP_REGION="europe-west1"
gcloud config set project $GCP_PROJECT_ID
gcloud config set compute/region $GCP_REGION
```

### Permissions Requises

Votre compte doit avoir les rôles:
- `roles/owner` (ou ensemble de rôles spécifiques)
- `roles/iam.serviceAccountAdmin`
- `roles/resourcemanager.projectIamAdmin`

## Étape 1: Clone et Configuration

```bash
# Clone repository
git clone https://github.com/your-org/cdn-analytics-platform.git
cd cdn-analytics-platform

# Setup Python environment
python3.11 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

## Étape 2: Configuration Terraform

### 2.1 Backend State

Créer bucket GCS pour Terraform state:

```bash
gsutil mb -p $GCP_PROJECT_ID -l $GCP_REGION gs://${GCP_PROJECT_ID}-terraform-state
gsutil versioning set on gs://${GCP_PROJECT_ID}-terraform-state
```

### 2.2 Variables

Éditer `infrastructure/environments/prod.tfvars`:

```hcl
project_id = "votre-projet-id"
region     = "europe-west1"
environment = "prod"

# Ajuster selon besoins
dataflow_num_workers = 20
dataflow_max_workers = 100
bigtable_num_nodes = 10
memorystore_size_gb = 20

# Secrets (ou utiliser Secret Manager)
pagerduty_service_key = "votre-pagerduty-key"
slack_webhook_url = "votre-slack-webhook"
```

### 2.3 Terraform Init

```bash
cd infrastructure/terraform

# Initialize
terraform init \
  -backend-config="bucket=${GCP_PROJECT_ID}-terraform-state" \
  -backend-config="prefix=terraform/state"

# Validate
terraform validate

# Plan
terraform plan -var-file=../environments/prod.tfvars -out=tfplan

# Review plan
terraform show tfplan
```

## Étape 3: Déploiement Infrastructure

### 3.1 Activation APIs (manuel si nécessaire)

```bash
gcloud services enable \
  pubsub.googleapis.com \
  dataflow.googleapis.com \
  bigquery.googleapis.com \
  bigtable.googleapis.com \
  redis.googleapis.com \
  container.googleapis.com \
  aiplatform.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com
```

### 3.2 Apply Terraform

```bash
# Apply
terraform apply -var-file=../environments/prod.tfvars

# Outputs
terraform output -json > outputs.json
```

⏱️ **Durée estimée**: 15-20 minutes

### 3.3 Vérification

```bash
# Vérifier Pub/Sub topics
gcloud pubsub topics list

# Vérifier BigQuery dataset
bq ls

# Vérifier Bigtable instance
gcloud bigtable instances list

# Vérifier Memorystore
gcloud redis instances list --region=$GCP_REGION
```

## Étape 4: Téléchargement GeoIP Databases

```bash
# Créer bucket pour GeoIP
gsutil mb gs://${GCP_PROJECT_ID}-geoip-data

# Télécharger GeoLite2 (nécessite licence MaxMind)
# Alternative: utiliser vos propres fichiers
gsutil cp GeoLite2-City.mmdb gs://${GCP_PROJECT_ID}-geoip-data/
gsutil cp GeoLite2-ASN.mmdb gs://${GCP_PROJECT_ID}-geoip-data/
```

## Étape 5: Déploiement SQL Models

```bash
# Materialized views
bq query --use_legacy_sql=false < sql/materialized_views/hourly_pop_performance.sql

# ML models
bq query --use_legacy_sql=false < sql/ml_models/load_prediction.sql
```

⏱️ **Durée**: 2-5 minutes

## Étape 6: Déploiement Dataflow Pipelines

### 6.1 Enrichment Pipeline

```bash
cd pipelines/dataflow

python enrichment_pipeline.py \
  --runner=DataflowRunner \
  --project=$GCP_PROJECT_ID \
  --region=$GCP_REGION \
  --job_name=cdn-enrichment-prod \
  --temp_location=gs://${GCP_PROJECT_ID}-dataflow-temp/temp \
  --staging_location=gs://${GCP_PROJECT_ID}-dataflow-staging/staging \
  --num_workers=20 \
  --max_num_workers=100 \
  --autoscaling_algorithm=THROUGHPUT_BASED \
  --worker_machine_type=n2-standard-4 \
  --disk_size_gb=50 \
  --streaming=true \
  --enable_streaming_engine=true \
  --service_account_email=dataflow-worker-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com \
  --experiments=enable_windmill_service,enable_streaming_resource_hints
```

### 6.2 Anomaly Detection Pipeline

```bash
python anomaly_detection_pipeline.py \
  --runner=DataflowRunner \
  --project=$GCP_PROJECT_ID \
  --region=$GCP_REGION \
  --job_name=cdn-anomaly-detection-prod \
  --temp_location=gs://${GCP_PROJECT_ID}-dataflow-temp/temp \
  --staging_location=gs://${GCP_PROJECT_ID}-dataflow-staging/staging \
  --num_workers=10 \
  --max_num_workers=50 \
  --autoscaling_algorithm=THROUGHPUT_BASED \
  --worker_machine_type=n2-standard-4 \
  --streaming=true \
  --service_account_email=dataflow-worker-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com
```

⏱️ **Durée**: 5-10 minutes pour démarrage

### 6.3 Vérification

```bash
# Liste jobs Dataflow
gcloud dataflow jobs list --region=$GCP_REGION --status=active

# Monitoring d'un job
gcloud dataflow jobs describe JOB_ID --region=$GCP_REGION
```

## Étape 7: Déploiement API

### 7.1 Build Docker Image

```bash
cd api

# Build
docker build -t gcr.io/${GCP_PROJECT_ID}/routing-api:latest .

# Configure Docker auth
gcloud auth configure-docker gcr.io

# Push
docker push gcr.io/${GCP_PROJECT_ID}/routing-api:latest
```

### 7.2 Déployer sur Cloud Run

```bash
gcloud run deploy routing-api \
  --image gcr.io/${GCP_PROJECT_ID}/routing-api:latest \
  --platform managed \
  --region $GCP_REGION \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --min-instances 2 \
  --max-instances 20 \
  --concurrency 100 \
  --timeout 60 \
  --service-account cdn-api-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars "GCP_PROJECT_ID=${GCP_PROJECT_ID}" \
  --set-env-vars "REDIS_HOST=$(terraform output -raw redis_host)" \
  --set-env-vars "BIGTABLE_INSTANCE=cdn-analytics-instance" \
  --set-env-vars "BIGTABLE_TABLE=cdn_realtime_metrics"
```

### 7.3 Test API

```bash
API_URL=$(gcloud run services describe routing-api --region=$GCP_REGION --format='value(status.url)')

# Health check
curl $API_URL/health

# Test best-pop endpoint
curl "$API_URL/api/v1/best-pop?client_ip=8.8.8.8"

# Test metrics
curl "$API_URL/api/v1/stats/global"
```

## Étape 8: Configuration Agents Ingestion

### 8.1 Déploiement Fluentd

Sur chaque edge server CDN:

```bash
# Installation Fluentd
curl -fsSL https://toolbelt.treasuredata.com/sh/install-ubuntu-focal-fluent-package5-lts.sh | sh

# Copier configuration
sudo cp ingestion/fluentd/fluent.conf /etc/fluent/fluent.conf

# Variables d'environnement
sudo tee /etc/default/fluentd <<EOF
GCP_PROJECT_ID=${GCP_PROJECT_ID}
DATACENTER=eu-west1
POP_ID=par01
EOF

# Restart
sudo systemctl restart fluentd
sudo systemctl enable fluentd

# Vérification
sudo systemctl status fluentd
sudo journalctl -u fluentd -f
```

### 8.2 Déploiement Telegraf

```bash
# Installation Telegraf
wget https://dl.influxdata.com/telegraf/releases/telegraf_1.29.0-1_amd64.deb
sudo dpkg -i telegraf_1.29.0-1_amd64.deb

# Copier configuration
sudo cp ingestion/telegraf/telegraf.conf /etc/telegraf/telegraf.conf

# Variables
export GCP_PROJECT_ID=${GCP_PROJECT_ID}
export DATACENTER=eu-west1
export POP_ID=par01

# Start
sudo systemctl restart telegraf
sudo systemctl enable telegraf
```

## Étape 9: Configuration Monitoring

### 9.1 Dashboards Grafana

```bash
# Import dashboard
curl -X POST http://grafana-url/api/dashboards/db \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -d @dashboards/grafana/noc_realtime.json
```

### 9.2 Alertes Cloud Monitoring

Les alertes sont déjà créées via Terraform, vérifier:

```bash
gcloud alpha monitoring policies list
```

## Étape 10: Tests de Bout en Bout

### 10.1 Génération de Trafic Test

```bash
# Script de génération de logs test
python tests/generate_test_traffic.py \
  --topic projects/${GCP_PROJECT_ID}/topics/cdn-logs-topic \
  --rate 1000 \
  --duration 300
```

### 10.2 Vérifications

```bash
# 1. Vérifier ingestion Pub/Sub
gcloud pubsub subscriptions describe cdn-logs-dataflow-sub

# 2. Vérifier Dataflow processing
gcloud dataflow jobs list --status=active

# 3. Vérifier données BigQuery
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) as count FROM \`${GCP_PROJECT_ID}.cdn_analytics.qos_metrics_5min\` WHERE window_start >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)"

# 4. Vérifier Bigtable
cbt -project=$GCP_PROJECT_ID -instance=cdn-analytics-instance read cdn_realtime_metrics count=10

# 5. Tester API
curl "$API_URL/api/v1/metrics/pop/par01"
```

## Étape 11: Configuration Production

### 11.1 Scaling Policies

```bash
# Augmenter quotas si nécessaire
gcloud services quota list --service=dataflow.googleapis.com
```

### 11.2 Backup & DR

```bash
# Backup Bigtable
gcloud bigtable backups create cdn-backup-$(date +%Y%m%d) \
  --instance=cdn-analytics-instance \
  --cluster=cdn-analytics-cluster-eu \
  --table=cdn_realtime_metrics \
  --retention-period=7d
```

### 11.3 Cost Optimization

```bash
# Activer Committed Use Discounts
# Via Console GCP: Billing > Commitments

# Configurer BigQuery reservations
bq mk --reservation --location=EU --slots=2000 cdn_reservation
```

## Dépannage

### Problèmes Courants

**1. Dataflow job ne démarre pas**
```bash
# Vérifier service account permissions
gcloud projects get-iam-policy $GCP_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:dataflow-worker-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
```

**2. API retourne erreurs Bigtable**
```bash
# Vérifier connectivité
cbt -project=$GCP_PROJECT_ID -instance=cdn-analytics-instance ls
```

**3. Pas de données dans BigQuery**
```bash
# Vérifier backlog Pub/Sub
gcloud pubsub subscriptions describe cdn-logs-dataflow-sub \
  --format="value(pushConfig.numUndeliveredMessages)"
```

## Rollback

En cas de problème:

```bash
# 1. Arrêter jobs Dataflow
gcloud dataflow jobs cancel JOB_ID --region=$GCP_REGION

# 2. Rollback Terraform
cd infrastructure/terraform
terraform apply -var-file=../environments/prod.tfvars -target=module.previous_version

# 3. Redéployer version stable API
gcloud run services update routing-api \
  --image gcr.io/${GCP_PROJECT_ID}/routing-api:stable \
  --region=$GCP_REGION
```

## Maintenance

### Mise à jour régulière

```bash
# 1. Mise à jour dependencies Python
pip install --upgrade -r requirements.txt

# 2. Mise à jour Terraform providers
cd infrastructure/terraform
terraform init -upgrade

# 3. Re-training ML models
bq query --use_legacy_sql=false < sql/ml_models/load_prediction.sql
```

## Support

- **Documentation**: docs/
- **Issues**: GitHub Issues
- **Slack**: #cdn-analytics-support
- **Oncall**: PagerDuty
