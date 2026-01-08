"""
Tests unitaires pour l'API de routage
"""

import unittest
import json
from unittest.mock import Mock, patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.routing_service import app


class TestRoutingAPI(unittest.TestCase):
    """Tests pour l'API de routage intelligent"""
    
    def setUp(self):
        """Setup test client"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
    
    def test_health_check(self):
        """Test endpoint de health check"""
        response = self.client.get('/health')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')
        self.assertIn('timestamp', data)
        self.assertIn('services', data)
    
    def test_best_pop_missing_ip(self):
        """Test best-pop sans IP client"""
        response = self.client.get('/api/v1/best-pop')
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('error', data)
    
    def test_best_pop_with_ip(self):
        """Test best-pop avec IP client"""
        response = self.client.get('/api/v1/best-pop?client_ip=8.8.8.8')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertIn('pop', data)
        self.assertIn('country', data)
        self.assertIn('estimated_latency_ms', data)
        self.assertIn('candidates', data)
        self.assertIn('timestamp', data)
    
    def test_best_pop_with_content_type(self):
        """Test best-pop avec type de contenu"""
        response = self.client.get('/api/v1/best-pop?client_ip=8.8.8.8&content_type=video')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIsNotNone(data['pop'])
    
    def test_pop_metrics(self):
        """Test endpoint métriques POP"""
        response = self.client.get('/api/v1/metrics/pop/par01')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data['pop'], 'par01')
        self.assertIn('metrics', data)
        self.assertIn('aggregated', data)
        self.assertGreater(data['count'], 0)
    
    def test_pop_metrics_with_minutes(self):
        """Test métriques POP avec paramètre minutes"""
        response = self.client.get('/api/v1/metrics/pop/par01?minutes=10')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data['metrics']), 10)
    
    def test_global_stats(self):
        """Test statistiques globales"""
        response = self.client.get('/api/v1/stats/global')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertIn('total_pops', data)
        self.assertIn('total_requests_per_sec', data)
        self.assertIn('global_avg_latency_ms', data)
        self.assertIn('regions', data)
    
    def test_anomalies_endpoint(self):
        """Test endpoint anomalies"""
        response = self.client.get('/api/v1/anomalies')
        
        # Peut retourner 500 si BigQuery pas configuré en test
        self.assertIn(response.status_code, [200, 500])
        
        if response.status_code == 200:
            data = json.loads(response.data)
            self.assertIn('anomalies', data)
            self.assertIn('count', data)
    
    def test_anomalies_with_filters(self):
        """Test anomalies avec filtres"""
        response = self.client.get('/api/v1/anomalies?hours=24&severity=critical')
        
        self.assertIn(response.status_code, [200, 500])


class TestGeoIPFunctions(unittest.TestCase):
    """Tests pour les fonctions GeoIP"""
    
    @patch('api.routing_service.geoip_reader')
    def test_geoip_lookup_success(self, mock_geoip):
        """Test lookup GeoIP réussi"""
        from api.routing_service import geoip_lookup
        
        mock_geoip.get.return_value = {
            'country': {'iso_code': 'FR'},
            'city': {'names': {'en': 'Paris'}},
            'continent': {'code': 'EU'},
            'location': {'latitude': 48.8566, 'longitude': 2.3522}
        }
        
        result = geoip_lookup('8.8.8.8')
        
        self.assertEqual(result['country'], 'FR')
        self.assertEqual(result['city'], 'Paris')
        self.assertEqual(result['continent'], 'EU')
    
    def test_get_candidate_pops_france(self):
        """Test sélection POPs pour France"""
        from api.routing_service import get_candidate_pops
        
        pops = get_candidate_pops('FR')
        
        self.assertIsInstance(pops, list)
        self.assertGreater(len(pops), 0)
        self.assertIn('par01', pops)
    
    def test_get_candidate_pops_unknown_country(self):
        """Test sélection POPs pour pays inconnu"""
        from api.routing_service import get_candidate_pops
        
        pops = get_candidate_pops('XX')  # Pays inconnu
        
        self.assertIsInstance(pops, list)
        self.assertGreater(len(pops), 0)  # Devrait retourner fallback


if __name__ == '__main__':
    unittest.main()
