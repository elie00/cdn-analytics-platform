"""
Pipeline Dataflow d'enrichissement CDN
Traite les logs bruts, enrichit avec GeoIP, et écrit vers Bigtable et BigQuery
"""

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions
from apache_beam.transforms.window import FixedWindows
from apache_beam.io.gcp.bigquery import WriteToBigQuery, BigQueryDisposition
from apache_beam.io.gcp.bigtable import WriteToBigtable
import json
import time
import maxminddb
import os
from typing import Dict, Any
import logging

logging.basicConfig(level=logging.INFO)


class ParseCDNLog(beam.DoFn):
    """Parse et valide les logs CDN"""
    
    def process(self, element):
        try:
            log = json.loads(element.decode('utf-8') if isinstance(element, bytes) else element)
            
            # Validation basique
            if not log.get('client_ip') or not log.get('pop'):
                logging.warning(f"Invalid log entry: missing required fields")
                return
            
            yield log
            
        except json.JSONDecodeError as e:
            logging.error(f"JSON decode error: {e}")
        except Exception as e:
            logging.error(f"Error parsing log: {e}")


class EnrichWithGeoIP(beam.DoFn):
    """Enrichissement avec données géographiques"""
    
    def __init__(self, geoip_db_path='/data/GeoLite2-City.mmdb', 
                 asn_db_path='/data/GeoLite2-ASN.mmdb'):
        self.geoip_db_path = geoip_db_path
        self.asn_db_path = asn_db_path
        self.geoip_reader = None
        self.asn_reader = None
    
    def setup(self):
        """Charger les bases GeoIP en mémoire pour performance"""
        try:
            self.geoip_reader = maxminddb.open_database(self.geoip_db_path)
            self.asn_reader = maxminddb.open_database(self.asn_db_path)
            logging.info("GeoIP databases loaded successfully")
        except Exception as e:
            logging.error(f"Failed to load GeoIP databases: {e}")
            # Mode dégradé sans GeoIP
            self.geoip_reader = None
            self.asn_reader = None
    
    def process(self, element):
        try:
            client_ip = element.get('client_ip')
            
            # Enrichissement géographique
            geo_data = {}
            asn_data = {}
            
            if self.geoip_reader and client_ip:
                try:
                    geo_data = self.geoip_reader.get(client_ip) or {}
                except:
                    pass
            
            if self.asn_reader and client_ip:
                try:
                    asn_data = self.asn_reader.get(client_ip) or {}
                except:
                    pass
            
            # Construction de l'enregistrement enrichi
            enriched = {
                **element,
                'country': geo_data.get('country', {}).get('iso_code'),
                'country_name': geo_data.get('country', {}).get('names', {}).get('en'),
                'city': geo_data.get('city', {}).get('names', {}).get('en'),
                'latitude': geo_data.get('location', {}).get('latitude'),
                'longitude': geo_data.get('location', {}).get('longitude'),
                'postal_code': geo_data.get('postal', {}).get('code'),
                'continent': geo_data.get('continent', {}).get('code'),
                'asn': asn_data.get('autonomous_system_number'),
                'isp': asn_data.get('autonomous_system_organization'),
                'processing_timestamp': int(time.time() * 1000),  # milliseconds
            }
            
            yield enriched
            
        except Exception as e:
            logging.error(f"Error enriching log: {e}")
            # Yield original en cas d'erreur
            yield element
    
    def teardown(self):
        """Cleanup"""
        if self.geoip_reader:
            self.geoip_reader.close()
        if self.asn_reader:
            self.asn_reader.close()


class CalculateQoSMetrics(beam.DoFn):
    """Calcule les métriques QoS pour chaque fenêtre temporelle"""
    
    def process(self, element, window=beam.DoFn.WindowParam):
        try:
            window_start = window.start.to_utc_datetime()
            window_end = window.end.to_utc_datetime()
            
            # Extraction des métriques
            response_time = float(element.get('response_time_ms', 0))
            status_code = int(element.get('status_code', 0))
            cache_status = element.get('cache_status', 'UNKNOWN')
            bytes_sent = int(element.get('bytes_sent', 0))
            
            metrics = {
                'window_start': window_start.isoformat(),
                'window_end': window_end.isoformat(),
                'pop': element.get('pop'),
                'datacenter': element.get('datacenter'),
                'country': element.get('country'),
                'city': element.get('city'),
                'asn': element.get('asn'),
                'isp': element.get('isp'),
                'cache_status': cache_status,
                
                # Métriques individuelles (à agréger)
                'response_time_ms': response_time,
                'is_error': 1 if status_code >= 500 else 0,
                'is_client_error': 1 if 400 <= status_code < 500 else 0,
                'is_cache_hit': 1 if cache_status == 'HIT' else 0,
                'is_cache_miss': 1 if cache_status == 'MISS' else 0,
                'bytes_sent': bytes_sent,
                'request_count': 1,
            }
            
            yield metrics
            
        except Exception as e:
            logging.error(f"Error calculating QoS metrics: {e}")


class AggregateMetrics(beam.CombineFn):
    """Agrège les métriques par fenêtre et dimensions"""
    
    def create_accumulator(self):
        return {
            'count': 0,
            'error_count': 0,
            'client_error_count': 0,
            'cache_hit_count': 0,
            'cache_miss_count': 0,
            'total_bytes': 0,
            'response_times': [],
        }
    
    def add_input(self, accumulator, input_element):
        accumulator['count'] += 1
        accumulator['error_count'] += input_element.get('is_error', 0)
        accumulator['client_error_count'] += input_element.get('is_client_error', 0)
        accumulator['cache_hit_count'] += input_element.get('is_cache_hit', 0)
        accumulator['cache_miss_count'] += input_element.get('is_cache_miss', 0)
        accumulator['total_bytes'] += input_element.get('bytes_sent', 0)
        accumulator['response_times'].append(input_element.get('response_time_ms', 0))
        return accumulator
    
    def merge_accumulators(self, accumulators):
        merged = self.create_accumulator()
        for acc in accumulators:
            merged['count'] += acc['count']
            merged['error_count'] += acc['error_count']
            merged['client_error_count'] += acc['client_error_count']
            merged['cache_hit_count'] += acc['cache_hit_count']
            merged['cache_miss_count'] += acc['cache_miss_count']
            merged['total_bytes'] += acc['total_bytes']
            merged['response_times'].extend(acc['response_times'])
        return merged
    
    def extract_output(self, accumulator):
        if accumulator['count'] == 0:
            return None
        
        response_times = sorted(accumulator['response_times'])
        count = accumulator['count']
        
        # Calcul des percentiles
        p50_idx = int(count * 0.50)
        p95_idx = int(count * 0.95)
        p99_idx = int(count * 0.99)
        
        return {
            'total_requests': count,
            'error_count': accumulator['error_count'],
            'error_4xx_count': accumulator['client_error_count'],
            'cache_hit_count': accumulator['cache_hit_count'],
            'cache_miss_count': accumulator['cache_miss_count'],
            'total_bytes_sent': accumulator['total_bytes'],
            'avg_response_time_ms': sum(response_times) / count if count > 0 else 0,
            'p50_response_time_ms': response_times[p50_idx] if p50_idx < count else 0,
            'p95_response_time_ms': response_times[p95_idx] if p95_idx < count else 0,
            'p99_response_time_ms': response_times[p99_idx] if p99_idx < count else 0,
            'avg_bandwidth_mbps': (accumulator['total_bytes'] * 8 / 1_000_000 / 300) if count > 0 else 0,  # 5 min window
        }


def format_for_bigtable(element):
    """Formate les données pour écriture dans Bigtable"""
    pop = element[0]['pop']
    metrics = element[1]
    
    # Row key: pop#reverse_timestamp#metric_type
    timestamp = int(time.time() * 1000)
    reverse_timestamp = 9999999999999 - timestamp
    row_key = f"{pop}#{reverse_timestamp}#latency".encode('utf-8')
    
    # Données à écrire
    return {
        'row_key': row_key,
        'stats': {
            'avg_latency_ms': str(metrics['avg_response_time_ms']).encode('utf-8'),
            'p95_latency_ms': str(metrics['p95_response_time_ms']).encode('utf-8'),
            'p99_latency_ms': str(metrics['p99_response_time_ms']).encode('utf-8'),
            'error_rate': str(metrics['error_count'] / max(metrics['total_requests'], 1)).encode('utf-8'),
            'cache_hit_rate': str(metrics['cache_hit_count'] / max(metrics['total_requests'], 1)).encode('utf-8'),
            'rps': str(metrics['total_requests'] / 300).encode('utf-8'),  # requests per second
        }
    }


def run(argv=None):
    """Pipeline principal"""
    
    # Options du pipeline
    pipeline_options = PipelineOptions(argv)
    pipeline_options.view_as(StandardOptions).streaming = True
    
    project_id = os.getenv('GCP_PROJECT_ID', 'your-project-id')
    region = os.getenv('GCP_REGION', 'europe-west1')
    
    # Schéma BigQuery
    bigquery_schema = {
        'fields': [
            {'name': 'window_start', 'type': 'TIMESTAMP', 'mode': 'REQUIRED'},
            {'name': 'window_end', 'type': 'TIMESTAMP', 'mode': 'REQUIRED'},
            {'name': 'pop', 'type': 'STRING', 'mode': 'REQUIRED'},
            {'name': 'datacenter', 'type': 'STRING', 'mode': 'NULLABLE'},
            {'name': 'country', 'type': 'STRING', 'mode': 'NULLABLE'},
            {'name': 'city', 'type': 'STRING', 'mode': 'NULLABLE'},
            {'name': 'asn', 'type': 'INT64', 'mode': 'NULLABLE'},
            {'name': 'isp', 'type': 'STRING', 'mode': 'NULLABLE'},
            {'name': 'cache_status', 'type': 'STRING', 'mode': 'NULLABLE'},
            {'name': 'avg_response_time_ms', 'type': 'FLOAT64', 'mode': 'REQUIRED'},
            {'name': 'p50_response_time_ms', 'type': 'FLOAT64', 'mode': 'NULLABLE'},
            {'name': 'p95_response_time_ms', 'type': 'FLOAT64', 'mode': 'NULLABLE'},
            {'name': 'p99_response_time_ms', 'type': 'FLOAT64', 'mode': 'NULLABLE'},
            {'name': 'total_requests', 'type': 'INT64', 'mode': 'REQUIRED'},
            {'name': 'error_count', 'type': 'INT64', 'mode': 'REQUIRED'},
            {'name': 'error_4xx_count', 'type': 'INT64', 'mode': 'NULLABLE'},
            {'name': 'cache_hit_count', 'type': 'INT64', 'mode': 'REQUIRED'},
            {'name': 'cache_miss_count', 'type': 'INT64', 'mode': 'NULLABLE'},
            {'name': 'total_bytes_sent', 'type': 'INT64', 'mode': 'REQUIRED'},
            {'name': 'avg_bandwidth_mbps', 'type': 'FLOAT64', 'mode': 'NULLABLE'},
        ]
    }
    
    with beam.Pipeline(options=pipeline_options) as pipeline:
        # Lecture depuis Pub/Sub
        cdn_logs = (
            pipeline
            | 'Read from Pub/Sub' >> beam.io.ReadFromPubSub(
                subscription=f'projects/{project_id}/subscriptions/cdn-logs-dataflow-sub'
            )
            | 'Parse Logs' >> beam.ParDo(ParseCDNLog())
        )
        
        # Enrichissement
        enriched = (
            cdn_logs
            | 'Enrich with GeoIP' >> beam.ParDo(EnrichWithGeoIP())
        )
        
        # Branche 1: Hot data vers Bigtable (fenêtre 1 minute)
        hot_data = (
            enriched
            | 'Window 1min' >> beam.WindowInto(FixedWindows(60))
            | 'Calculate QoS 1min' >> beam.ParDo(CalculateQoSMetrics())
            | 'Key by POP+Country' >> beam.Map(
                lambda x: ((x['pop'], x.get('country', 'UNKNOWN')), x)
            )
            | 'Aggregate 1min' >> beam.CombinePerKey(AggregateMetrics())
            | 'Format for Bigtable' >> beam.Map(format_for_bigtable)
            # Note: WriteToBigtable nécessite configuration supplémentaire
            # | 'Write to Bigtable' >> WriteToBigtable(...)
        )
        
        # Branche 2: Analytics vers BigQuery (fenêtre 5 minutes)
        analytics = (
            enriched
            | 'Window 5min' >> beam.WindowInto(FixedWindows(300))
            | 'Calculate QoS 5min' >> beam.ParDo(CalculateQoSMetrics())
            | 'Key by Dimensions' >> beam.Map(
                lambda x: ((x['pop'], x.get('country'), x.get('cache_status'), x['window_start']), x)
            )
            | 'Aggregate 5min' >> beam.CombinePerKey(AggregateMetrics())
            | 'Flatten Results' >> beam.Map(
                lambda x: {**x[1], 'pop': x[0][0], 'country': x[0][1], 'cache_status': x[0][2], 'window_start': x[0][3]}
            )
            | 'Write to BigQuery' >> WriteToBigQuery(
                table=f'{project_id}:cdn_analytics.qos_metrics_5min',
                schema=bigquery_schema,
                write_disposition=BigQueryDisposition.WRITE_APPEND,
                create_disposition=BigQueryDisposition.CREATE_IF_NEEDED,
                method='STREAMING_INSERTS'
            )
        )


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    run()
