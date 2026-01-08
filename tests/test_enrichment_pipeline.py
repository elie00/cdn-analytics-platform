"""
Tests unitaires pour le pipeline d'enrichissement
"""

import unittest
import json
from unittest.mock import Mock, patch
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pipelines.dataflow.enrichment_pipeline import (
    ParseCDNLog,
    EnrichWithGeoIP,
    CalculateQoSMetrics,
    AggregateMetrics
)


class TestParseCDNLog(unittest.TestCase):
    """Tests pour ParseCDNLog DoFn"""
    
    def setUp(self):
        self.parser = ParseCDNLog()
    
    def test_parse_valid_log(self):
        """Test parsing d'un log valide"""
        log_data = {
            "client_ip": "8.8.8.8",
            "pop": "par01",
            "status_code": 200,
            "response_time_ms": 50
        }
        log_json = json.dumps(log_data)
        
        results = list(self.parser.process(log_json))
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["client_ip"], "8.8.8.8")
        self.assertEqual(results[0]["pop"], "par01")
    
    def test_parse_invalid_json(self):
        """Test parsing d'un JSON invalide"""
        log_json = "invalid json"
        
        results = list(self.parser.process(log_json))
        
        self.assertEqual(len(results), 0)
    
    def test_parse_missing_required_fields(self):
        """Test parsing avec champs requis manquants"""
        log_data = {"status_code": 200}
        log_json = json.dumps(log_data)
        
        results = list(self.parser.process(log_json))
        
        self.assertEqual(len(results), 0)


class TestEnrichWithGeoIP(unittest.TestCase):
    """Tests pour EnrichWithGeoIP DoFn"""
    
    def setUp(self):
        self.enricher = EnrichWithGeoIP()
        # Mock GeoIP readers
        self.enricher.geoip_reader = Mock()
        self.enricher.asn_reader = Mock()
    
    def test_enrich_with_geo_data(self):
        """Test enrichissement avec données géographiques"""
        self.enricher.geoip_reader.get.return_value = {
            'country': {'iso_code': 'FR'},
            'city': {'names': {'en': 'Paris'}},
            'location': {'latitude': 48.8566, 'longitude': 2.3522}
        }
        self.enricher.asn_reader.get.return_value = {
            'autonomous_system_number': 15169,
            'autonomous_system_organization': 'Google LLC'
        }
        
        log = {
            'client_ip': '8.8.8.8',
            'pop': 'par01',
            'status_code': 200
        }
        
        results = list(self.enricher.process(log))
        
        self.assertEqual(len(results), 1)
        enriched = results[0]
        self.assertEqual(enriched['country'], 'FR')
        self.assertEqual(enriched['city'], 'Paris')
        self.assertEqual(enriched['asn'], 15169)
        self.assertEqual(enriched['isp'], 'Google LLC')
    
    def test_enrich_without_geoip(self):
        """Test enrichissement sans GeoIP"""
        self.enricher.geoip_reader = None
        self.enricher.asn_reader = None
        
        log = {
            'client_ip': '8.8.8.8',
            'pop': 'par01'
        }
        
        results = list(self.enricher.process(log))
        
        self.assertEqual(len(results), 1)
        enriched = results[0]
        self.assertIsNone(enriched.get('country'))


class TestCalculateQoSMetrics(unittest.TestCase):
    """Tests pour CalculateQoSMetrics DoFn"""
    
    def setUp(self):
        self.calculator = CalculateQoSMetrics()
    
    def test_calculate_metrics(self):
        """Test calcul des métriques QoS"""
        from datetime import datetime
        from apache_beam.transforms.window import IntervalWindow
        
        log = {
            'pop': 'par01',
            'country': 'FR',
            'response_time_ms': 50.5,
            'status_code': 200,
            'cache_status': 'HIT',
            'bytes_sent': 1024
        }
        
        window = IntervalWindow(0, 60)
        
        results = list(self.calculator.process(log, window=window))
        
        self.assertEqual(len(results), 1)
        metrics = results[0]
        self.assertEqual(metrics['pop'], 'par01')
        self.assertEqual(metrics['response_time_ms'], 50.5)
        self.assertEqual(metrics['is_cache_hit'], 1)
        self.assertEqual(metrics['is_error'], 0)


class TestAggregateMetrics(unittest.TestCase):
    """Tests pour AggregateMetrics CombineFn"""
    
    def setUp(self):
        self.aggregator = AggregateMetrics()
    
    def test_aggregate_single_metric(self):
        """Test agrégation d'une seule métrique"""
        acc = self.aggregator.create_accumulator()
        
        metric = {
            'response_time_ms': 50,
            'is_error': 0,
            'is_cache_hit': 1,
            'bytes_sent': 1024
        }
        
        acc = self.aggregator.add_input(acc, metric)
        result = self.aggregator.extract_output(acc)
        
        self.assertEqual(result['total_requests'], 1)
        self.assertEqual(result['avg_response_time_ms'], 50)
        self.assertEqual(result['cache_hit_count'], 1)
    
    def test_aggregate_multiple_metrics(self):
        """Test agrégation de plusieurs métriques"""
        acc = self.aggregator.create_accumulator()
        
        metrics = [
            {'response_time_ms': 50, 'is_error': 0, 'is_cache_hit': 1, 'bytes_sent': 1024},
            {'response_time_ms': 100, 'is_error': 1, 'is_cache_hit': 0, 'bytes_sent': 2048},
            {'response_time_ms': 75, 'is_error': 0, 'is_cache_hit': 1, 'bytes_sent': 1536},
        ]
        
        for metric in metrics:
            acc = self.aggregator.add_input(acc, metric)
        
        result = self.aggregator.extract_output(acc)
        
        self.assertEqual(result['total_requests'], 3)
        self.assertEqual(result['error_count'], 1)
        self.assertEqual(result['cache_hit_count'], 2)
        self.assertAlmostEqual(result['avg_response_time_ms'], 75, delta=0.1)
    
    def test_merge_accumulators(self):
        """Test fusion de plusieurs accumulateurs"""
        acc1 = self.aggregator.create_accumulator()
        acc2 = self.aggregator.create_accumulator()
        
        acc1 = self.aggregator.add_input(acc1, {'response_time_ms': 50, 'is_error': 0, 'is_cache_hit': 1, 'bytes_sent': 1024})
        acc2 = self.aggregator.add_input(acc2, {'response_time_ms': 100, 'is_error': 1, 'is_cache_hit': 0, 'bytes_sent': 2048})
        
        merged = self.aggregator.merge_accumulators([acc1, acc2])
        result = self.aggregator.extract_output(merged)
        
        self.assertEqual(result['total_requests'], 2)
        self.assertEqual(result['error_count'], 1)


if __name__ == '__main__':
    unittest.main()
