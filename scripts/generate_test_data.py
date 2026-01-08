#!/usr/bin/env python3
"""
Script de génération de données de test pour CDN Analytics Platform
Simule du trafic CDN réaliste vers Pub/Sub
"""

import json
import random
import time
import argparse
from datetime import datetime
from google.cloud import pubsub_v1
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
POPS = ['par01', 'par02', 'lon01', 'fra01', 'ams01', 'nyc01', 'sfo01', 'tok01']
COUNTRIES = ['FR', 'GB', 'DE', 'NL', 'US', 'JP', 'CN', 'BR']
STATUS_CODES = [200, 200, 200, 200, 304, 404, 500, 503]  # Weighted towards 200
CACHE_STATUSES = ['HIT', 'HIT', 'HIT', 'MISS', 'BYPASS']  # Weighted towards HIT

class CDNLogGenerator:
    """Générateur de logs CDN synthétiques"""
    
    def __init__(self, project_id, topic_name):
        self.publisher = pubsub_v1.PublisherClient()
        self.topic_path = self.publisher.topic_path(project_id, topic_name)
        self.message_count = 0
    
    def generate_ip(self):
        """Génère une IP aléatoire"""
        return f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 255)}"
    
    def generate_log(self):
        """Génère un log CDN synthétique"""
        pop = random.choice(POPS)
        status_code = random.choice(STATUS_CODES)
        cache_status = random.choice(CACHE_STATUSES)
        
        # Latence réaliste basée sur le status et le cache
        base_latency = 50 if cache_status == 'HIT' else 150
        if status_code >= 500:
            base_latency += random.randint(100, 500)
        
        log = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "client_ip": self.generate_ip(),
            "pop": pop,
            "datacenter": pop[:3],  # Premiers 3 caractères
            "status_code": status_code,
            "response_time_ms": base_latency + random.normalvariate(0, 20),
            "cache_status": cache_status,
            "bytes_sent": random.randint(1024, 10485760),  # 1KB - 10MB
            "request_method": random.choice(['GET', 'GET', 'GET', 'POST', 'HEAD']),
            "request_uri": f"/content/{random.randint(1, 10000)}.{random.choice(['html', 'jpg', 'mp4', 'css', 'js'])}",
            "http_protocol": "HTTP/1.1",
            "user_agent": "Mozilla/5.0 (Test Data Generator)",
        }
        
        return log
    
    def publish_log(self, log):
        """Publie un log vers Pub/Sub"""
        data = json.dumps(log).encode('utf-8')
        future = self.publisher.publish(self.topic_path, data)
        self.message_count += 1
        return future
    
    def generate_burst(self, count, batch_size=100):
        """Génère un burst de logs"""
        futures = []
        for i in range(count):
            log = self.generate_log()
            future = self.publish_log(log)
            futures.append(future)
            
            if (i + 1) % batch_size == 0:
                # Wait for batch to complete
                for f in futures:
                    f.result()
                futures = []
                logger.info(f"Published {i + 1}/{count} messages")
        
        # Wait for remaining
        for f in futures:
            f.result()
        
        logger.info(f"Completed burst of {count} messages")


def main():
    parser = argparse.ArgumentParser(description='Generate test CDN logs')
    parser.add_argument('--project', required=True, help='GCP Project ID')
    parser.add_argument('--topic', default='cdn-logs-topic', help='Pub/Sub topic name')
    parser.add_argument('--rate', type=int, default=100, help='Messages per second')
    parser.add_argument('--duration', type=int, default=60, help='Duration in seconds')
    parser.add_argument('--burst', action='store_true', help='Send as burst instead of steady rate')
    
    args = parser.parse_args()
    
    generator = CDNLogGenerator(args.project, args.topic)
    total_messages = args.rate * args.duration
    
    logger.info(f"Starting data generation:")
    logger.info(f"  Project: {args.project}")
    logger.info(f"  Topic: {args.topic}")
    logger.info(f"  Rate: {args.rate} msg/sec")
    logger.info(f"  Duration: {args.duration} seconds")
    logger.info(f"  Total messages: {total_messages}")
    
    start_time = time.time()
    
    if args.burst:
        # Send all at once
        generator.generate_burst(total_messages)
    else:
        # Send at steady rate
        interval = 1.0 / args.rate
        for i in range(total_messages):
            log = generator.generate_log()
            generator.publish_log(log)
            
            if (i + 1) % args.rate == 0:
                logger.info(f"Published {i + 1}/{total_messages} messages")
            
            # Rate limiting
            elapsed = time.time() - start_time
            expected_time = (i + 1) * interval
            if elapsed < expected_time:
                time.sleep(expected_time - elapsed)
    
    end_time = time.time()
    duration = end_time - start_time
    actual_rate = total_messages / duration
    
    logger.info(f"\n✅ Generation complete!")
    logger.info(f"  Total messages: {generator.message_count}")
    logger.info(f"  Duration: {duration:.2f} seconds")
    logger.info(f"  Actual rate: {actual_rate:.2f} msg/sec")


if __name__ == '__main__':
    main()
