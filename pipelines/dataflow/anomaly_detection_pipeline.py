"""
Pipeline Dataflow de détection d'anomalies
Analyse les métriques en temps réel et détecte les anomalies de performance
"""

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions
from apache_beam.transforms.window import FixedWindows, SlidingWindows
from apache_beam.io.gcp.bigquery import WriteToBigQuery, BigQueryDisposition
import json
import time
import logging
import statistics
from typing import Dict, List
import os

logging.basicConfig(level=logging.INFO)


class CalculateBaseline(beam.DoFn):
    """Calcule les statistiques de baseline pour chaque POP"""
    
    def process(self, element):
        pop, metrics_list = element
        
        if not metrics_list:
            return
        
        # Extraction des valeurs
        latencies = [m.get('avg_response_time_ms', 0) for m in metrics_list if m.get('avg_response_time_ms')]
        error_rates = [
            m.get('error_count', 0) / max(m.get('total_requests', 1), 1)
            for m in metrics_list
        ]
        
        if not latencies:
            return
        
        # Calcul des statistiques
        baseline = {
            'pop': pop,
            'timestamp': int(time.time() * 1000),
            'mean_latency': statistics.mean(latencies),
            'std_latency': statistics.stdev(latencies) if len(latencies) > 1 else 0,
            'median_latency': statistics.median(latencies),
            'mean_error_rate': statistics.mean(error_rates) if error_rates else 0,
            'std_error_rate': statistics.stdev(error_rates) if len(error_rates) > 1 else 0,
            'sample_count': len(latencies),
        }
        
        yield baseline


class DetectAnomalies(beam.DoFn):
    """Détecte les anomalies en comparant aux baselines"""
    
    def __init__(self, z_score_threshold=3.0):
        self.z_score_threshold = z_score_threshold
        self.baselines = {}  # Cache des baselines
    
    def process(self, element):
        try:
            pop = element.get('pop')
            current_latency = element.get('avg_response_time_ms', 0)
            current_error_rate = element.get('error_count', 0) / max(element.get('total_requests', 1), 1)
            
            # Récupération baseline (simplifié - devrait venir de Bigtable)
            baseline = self.baselines.get(pop, {
                'mean_latency': 100,  # Valeurs par défaut
                'std_latency': 50,
                'mean_error_rate': 0.01,
                'std_error_rate': 0.005,
            })
            
            # Calcul z-scores
            z_score_latency = 0
            if baseline.get('std_latency', 0) > 0:
                z_score_latency = (current_latency - baseline['mean_latency']) / baseline['std_latency']
            
            z_score_errors = 0
            if baseline.get('std_error_rate', 0) > 0:
                z_score_errors = (current_error_rate - baseline['mean_error_rate']) / baseline['std_error_rate']
            
            max_z_score = max(abs(z_score_latency), abs(z_score_errors))
            
            # Détection d'anomalie
            if max_z_score > self.z_score_threshold:
                anomaly_type = 'latency' if abs(z_score_latency) > abs(z_score_errors) else 'errors'
                severity = 'critical' if max_z_score > 5 else 'warning'
                
                anomaly = {
                    'detected_at': element.get('window_start'),
                    'pop': pop,
                    'datacenter': element.get('datacenter'),
                    'country': element.get('country'),
                    'anomaly_type': anomaly_type,
                    'severity': severity,
                    'current_value': current_latency if anomaly_type == 'latency' else current_error_rate,
                    'baseline_value': baseline['mean_latency'] if anomaly_type == 'latency' else baseline['mean_error_rate'],
                    'z_score': max_z_score,
                    'confidence': min(0.99, max_z_score / 10),  # Confidence score
                    'description': self._generate_description(anomaly_type, current_latency, current_error_rate, baseline),
                    'resolved_at': None,
                }
                
                yield anomaly
                logging.warning(f"Anomaly detected: {anomaly}")
                
        except Exception as e:
            logging.error(f"Error detecting anomalies: {e}")
    
    def _generate_description(self, anomaly_type, current_latency, current_error_rate, baseline):
        if anomaly_type == 'latency':
            return (f"Latency spike: {current_latency:.2f}ms "
                   f"(baseline: {baseline.get('mean_latency', 0):.2f}ms)")
        else:
            return (f"Error rate spike: {current_error_rate*100:.2f}% "
                   f"(baseline: {baseline.get('mean_error_rate', 0)*100:.2f}%)")


class DetectTrafficSpikes(beam.DoFn):
    """Détecte les pics de trafic inhabituels (potentiel DDoS)"""
    
    def process(self, element):
        try:
            pop = element.get('pop')
            current_rps = element.get('total_requests', 0) / 300  # requests per second
            
            # Seuil simple (devrait être dynamique basé sur historique)
            baseline_rps = 1000  # À calculer depuis historique
            threshold_multiplier = 3.0
            
            if current_rps > baseline_rps * threshold_multiplier:
                anomaly = {
                    'detected_at': element.get('window_start'),
                    'pop': pop,
                    'anomaly_type': 'traffic_spike',
                    'severity': 'critical' if current_rps > baseline_rps * 5 else 'warning',
                    'current_value': current_rps,
                    'baseline_value': baseline_rps,
                    'z_score': current_rps / baseline_rps,
                    'confidence': 0.9,
                    'description': f"Traffic spike: {current_rps:.0f} rps (baseline: {baseline_rps:.0f} rps)",
                    'resolved_at': None,
                }
                
                yield anomaly
                logging.warning(f"Traffic spike detected: {anomaly}")
                
        except Exception as e:
            logging.error(f"Error detecting traffic spikes: {e}")


def run(argv=None):
    """Pipeline principal de détection d'anomalies"""
    
    pipeline_options = PipelineOptions(argv)
    pipeline_options.view_as(StandardOptions).streaming = True
    
    project_id = os.getenv('GCP_PROJECT_ID', 'your-project-id')
    
    # Schéma BigQuery pour anomalies
    anomalies_schema = {
        'fields': [
            {'name': 'detected_at', 'type': 'TIMESTAMP', 'mode': 'REQUIRED'},
            {'name': 'pop', 'type': 'STRING', 'mode': 'REQUIRED'},
            {'name': 'datacenter', 'type': 'STRING', 'mode': 'NULLABLE'},
            {'name': 'country', 'type': 'STRING', 'mode': 'NULLABLE'},
            {'name': 'anomaly_type', 'type': 'STRING', 'mode': 'REQUIRED'},
            {'name': 'severity', 'type': 'STRING', 'mode': 'REQUIRED'},
            {'name': 'current_value', 'type': 'FLOAT64', 'mode': 'REQUIRED'},
            {'name': 'baseline_value', 'type': 'FLOAT64', 'mode': 'REQUIRED'},
            {'name': 'z_score', 'type': 'FLOAT64', 'mode': 'NULLABLE'},
            {'name': 'confidence', 'type': 'FLOAT64', 'mode': 'NULLABLE'},
            {'name': 'description', 'type': 'STRING', 'mode': 'NULLABLE'},
            {'name': 'resolved_at', 'type': 'TIMESTAMP', 'mode': 'NULLABLE'},
        ]
    }
    
    with beam.Pipeline(options=pipeline_options) as pipeline:
        # Lecture des métriques agrégées depuis BigQuery (stream)
        metrics = (
            pipeline
            | 'Read Metrics from Pub/Sub' >> beam.io.ReadFromPubSub(
                subscription=f'projects/{project_id}/subscriptions/cdn-logs-dataflow-sub'
            )
            | 'Parse JSON' >> beam.Map(lambda x: json.loads(x))
        )
        
        # Fenêtre glissante pour calcul de baseline (30 minutes)
        baseline = (
            metrics
            | 'Window 30min Sliding' >> beam.WindowInto(SlidingWindows(size=1800, period=300))
            | 'Key by POP' >> beam.Map(lambda x: (x.get('pop'), x))
            | 'Group by POP' >> beam.GroupByKey()
            | 'Calculate Baseline' >> beam.ParDo(CalculateBaseline())
        )
        
        # Détection d'anomalies (fenêtre 5 minutes)
        anomalies_latency = (
            metrics
            | 'Window 5min' >> beam.WindowInto(FixedWindows(300))
            | 'Detect Latency Anomalies' >> beam.ParDo(DetectAnomalies(z_score_threshold=3.0))
        )
        
        anomalies_traffic = (
            metrics
            | 'Window 5min Traffic' >> beam.WindowInto(FixedWindows(300))
            | 'Detect Traffic Spikes' >> beam.ParDo(DetectTrafficSpikes())
        )
        
        # Fusion des anomalies
        all_anomalies = (
            (anomalies_latency, anomalies_traffic)
            | 'Flatten Anomalies' >> beam.Flatten()
            | 'Deduplicate' >> beam.Distinct()
        )
        
        # Écriture vers BigQuery
        all_anomalies | 'Write Anomalies to BigQuery' >> WriteToBigQuery(
            table=f'{project_id}:cdn_analytics.anomalies',
            schema=anomalies_schema,
            write_disposition=BigQueryDisposition.WRITE_APPEND,
            create_disposition=BigQueryDisposition.CREATE_IF_NEEDED,
            method='STREAMING_INSERTS'
        )


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    run()
