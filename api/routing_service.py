"""
API de routage intelligent CDN
Fournit des décisions de routage basées sur performance temps réel
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from google.cloud import bigtable
from google.cloud import bigquery
import redis
import json
import time
import logging
import os
from functools import wraps
import maxminddb

# Configuration
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# Configuration GCP
PROJECT_ID = os.getenv('GCP_PROJECT_ID', 'your-project-id')
BIGTABLE_INSTANCE = os.getenv('BIGTABLE_INSTANCE', 'cdn-analytics-instance')
BIGTABLE_TABLE = os.getenv('BIGTABLE_TABLE', 'cdn_realtime_metrics')
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))

# Clients GCP
try:
    bt_client = bigtable.Client(project=PROJECT_ID, admin=True)
    bt_instance = bt_client.instance(BIGTABLE_INSTANCE)
    bt_table = bt_instance.table(BIGTABLE_TABLE)
    logging.info("Bigtable client initialized")
except Exception as e:
    logging.error(f"Failed to initialize Bigtable client: {e}")
    bt_table = None

try:
    bq_client = bigquery.Client(project=PROJECT_ID)
    logging.info("BigQuery client initialized")
except Exception as e:
    logging.error(f"Failed to initialize BigQuery client: {e}")
    bq_client = None

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2
    )
    redis_client.ping()
    logging.info("Redis client initialized")
except Exception as e:
    logging.error(f"Failed to initialize Redis client: {e}")
    redis_client = None

# GeoIP
try:
    geoip_reader = maxminddb.open_database('/data/GeoLite2-City.mmdb')
    logging.info("GeoIP database loaded")
except Exception as e:
    logging.error(f"Failed to load GeoIP database: {e}")
    geoip_reader = None


# Mapping POPs par pays/région
POP_REGIONS = {
    'FR': ['par01', 'par02', 'mrs01'],
    'GB': ['lon01', 'lon02'],
    'DE': ['fra01', 'fra02', 'ber01'],
    'NL': ['ams01', 'ams02'],
    'US': ['nyc01', 'nyc02', 'sfo01', 'sfo02', 'dfw01'],
    'SG': ['sin01', 'sin02'],
    'JP': ['tok01', 'tok02'],
    'AU': ['syd01'],
}


def cache_response(ttl=30):
    """Decorator pour caching Redis"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not redis_client:
                return f(*args, **kwargs)
            
            # Génération de la clé cache
            cache_key = f"{f.__name__}:{request.path}:{request.args}"
            
            try:
                # Check cache
                cached = redis_client.get(cache_key)
                if cached:
                    logging.debug(f"Cache hit: {cache_key}")
                    return jsonify(json.loads(cached))
                
                # Exécution fonction
                result = f(*args, **kwargs)
                
                # Mise en cache
                if result:
                    redis_client.setex(cache_key, ttl, json.dumps(result.get_json()))
                
                return result
                
            except Exception as e:
                logging.error(f"Cache error: {e}")
                return f(*args, **kwargs)
        
        return wrapped
    return decorator


def geoip_lookup(client_ip):
    """Lookup géographique d'une IP"""
    if not geoip_reader:
        return {'country': 'UNKNOWN', 'city': None}
    
    try:
        data = geoip_reader.get(client_ip)
        if data:
            return {
                'country': data.get('country', {}).get('iso_code', 'UNKNOWN'),
                'city': data.get('city', {}).get('names', {}).get('en'),
                'continent': data.get('continent', {}).get('code'),
                'lat': data.get('location', {}).get('latitude'),
                'lon': data.get('location', {}).get('longitude'),
            }
    except Exception as e:
        logging.error(f"GeoIP lookup error: {e}")
    
    return {'country': 'UNKNOWN', 'city': None}


def get_candidate_pops(country, fallback_region='EU'):
    """Retourne la liste des POPs candidats pour un pays"""
    pops = POP_REGIONS.get(country, [])
    
    if not pops:
        # Fallback: POPs de la région
        if fallback_region == 'EU':
            pops = POP_REGIONS.get('FR', []) + POP_REGIONS.get('DE', []) + POP_REGIONS.get('NL', [])
        elif fallback_region == 'US':
            pops = POP_REGIONS.get('US', [])
        elif fallback_region == 'APAC':
            pops = POP_REGIONS.get('SG', []) + POP_REGIONS.get('JP', []) + POP_REGIONS.get('AU', [])
    
    return pops or ['par01']  # Default fallback


def reverse_timestamp(ts):
    """Convertit timestamp en reverse timestamp pour Bigtable"""
    return 9999999999999 - int(ts * 1000)


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    status = {
        'status': 'healthy',
        'timestamp': int(time.time()),
        'services': {
            'bigtable': bt_table is not None,
            'bigquery': bq_client is not None,
            'redis': redis_client is not None,
            'geoip': geoip_reader is not None,
        }
    }
    
    return jsonify(status), 200


@app.route('/api/v1/best-pop', methods=['GET'])
@cache_response(ttl=30)
def get_best_pop():
    """
    Retourne le meilleur POP pour un client donné
    Query params:
    - client_ip: IP du client (required)
    - content_type: Type de contenu (video, image, api, etc.) (optional)
    """
    client_ip = request.args.get('client_ip')
    content_type = request.args.get('content_type', 'general')
    
    if not client_ip:
        return jsonify({'error': 'client_ip parameter required'}), 400
    
    # GeoIP lookup
    geo_data = geoip_lookup(client_ip)
    country = geo_data.get('country', 'UNKNOWN')
    
    # Sélection des POPs candidats
    candidate_pops = get_candidate_pops(country)
    
    # Scoring des POPs basé sur métriques temps réel
    best_pop = None
    best_score = float('inf')
    pop_scores = []
    
    for pop in candidate_pops:
        try:
            # Lecture métriques depuis Bigtable (mock ici)
            # En production: lecture réelle depuis Bigtable
            metrics = {
                'latency_ms': 50 + hash(pop) % 100,  # Mock
                'error_rate': 0.01,  # Mock
                'load': 0.5,  # Mock
            }
            
            # Score composite: latency * (1 + error_rate) * (1 + load)
            score = metrics['latency_ms'] * (1 + metrics['error_rate']) * (1 + metrics['load'])
            
            pop_scores.append({
                'pop': pop,
                'score': score,
                'latency_ms': metrics['latency_ms'],
                'error_rate': metrics['error_rate'],
                'load': metrics['load'],
            })
            
            if score < best_score:
                best_score = score
                best_pop = pop
                
        except Exception as e:
            logging.error(f"Error evaluating POP {pop}: {e}")
            continue
    
    if not best_pop:
        best_pop = candidate_pops[0] if candidate_pops else 'par01'
    
    result = {
        'pop': best_pop,
        'country': country,
        'city': geo_data.get('city'),
        'estimated_latency_ms': best_score / (1.01 * 1.5) if best_score != float('inf') else 100,
        'candidates': sorted(pop_scores, key=lambda x: x['score'])[:3],
        'timestamp': int(time.time()),
        'cache_ttl': 30,
    }
    
    return jsonify(result)


@app.route('/api/v1/metrics/pop/<pop_id>', methods=['GET'])
@cache_response(ttl=10)
def get_pop_metrics(pop_id):
    """
    Métriques temps réel pour un POP spécifique
    """
    minutes = int(request.args.get('minutes', 5))
    
    # Mock data (en production: lecture depuis Bigtable)
    metrics = []
    current_time = int(time.time())
    
    for i in range(minutes):
        timestamp = current_time - (i * 60)
        metrics.append({
            'timestamp': timestamp,
            'pop': pop_id,
            'avg_latency_ms': 50 + (i * 5) + hash(pop_id) % 20,
            'requests_per_sec': 1000 + hash(pop_id) % 500,
            'error_rate': 0.01 + (i * 0.001),
            'cache_hit_rate': 0.85 - (i * 0.02),
            'bandwidth_gbps': 5.5 + hash(pop_id) % 3,
        })
    
    result = {
        'pop': pop_id,
        'metrics': metrics,
        'count': len(metrics),
        'aggregated': {
            'avg_latency_ms': sum(m['avg_latency_ms'] for m in metrics) / len(metrics),
            'avg_rps': sum(m['requests_per_sec'] for m in metrics) / len(metrics),
            'avg_error_rate': sum(m['error_rate'] for m in metrics) / len(metrics),
            'avg_cache_hit_rate': sum(m['cache_hit_rate'] for m in metrics) / len(metrics),
        },
        'timestamp': current_time,
    }
    
    return jsonify(result)


@app.route('/api/v1/anomalies', methods=['GET'])
def get_anomalies():
    """
    Liste des anomalies récentes
    """
    hours = int(request.args.get('hours', 1))
    severity = request.args.get('severity', 'all')
    
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500
    
    try:
        query = f"""
        SELECT
            detected_at,
            pop,
            anomaly_type,
            severity,
            current_value,
            baseline_value,
            z_score,
            description
        FROM `{PROJECT_ID}.cdn_analytics.anomalies`
        WHERE detected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        """
        
        if severity != 'all':
            query += f" AND severity = '{severity}'"
        
        query += " ORDER BY detected_at DESC LIMIT 100"
        
        query_job = bq_client.query(query)
        results = query_job.result()
        
        anomalies = []
        for row in results:
            anomalies.append({
                'detected_at': row.detected_at.isoformat() if row.detected_at else None,
                'pop': row.pop,
                'anomaly_type': row.anomaly_type,
                'severity': row.severity,
                'current_value': float(row.current_value) if row.current_value else 0,
                'baseline_value': float(row.baseline_value) if row.baseline_value else 0,
                'z_score': float(row.z_score) if row.z_score else 0,
                'description': row.description,
            })
        
        return jsonify({
            'anomalies': anomalies,
            'count': len(anomalies),
            'timestamp': int(time.time()),
        })
        
    except Exception as e:
        logging.error(f"Error fetching anomalies: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/stats/global', methods=['GET'])
@cache_response(ttl=60)
def get_global_stats():
    """Statistiques globales du CDN"""
    
    # Mock data (en production: agrégation depuis BigQuery)
    stats = {
        'total_pops': len([pop for pops in POP_REGIONS.values() for pop in pops]),
        'active_pops': len([pop for pops in POP_REGIONS.values() for pop in pops]),  # Mock
        'total_requests_per_sec': 50000,  # Mock
        'global_avg_latency_ms': 75,  # Mock
        'global_error_rate': 0.015,  # Mock
        'global_cache_hit_rate': 0.88,  # Mock
        'total_bandwidth_gbps': 150,  # Mock
        'regions': {
            'EU': {'pops': 8, 'rps': 25000, 'latency': 65},
            'US': {'pops': 5, 'rps': 15000, 'latency': 80},
            'APAC': {'pops': 4, 'rps': 10000, 'latency': 90},
        },
        'timestamp': int(time.time()),
    }
    
    return jsonify(stats)


if __name__ == '__main__':
    port = int(os.getenv('API_PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
