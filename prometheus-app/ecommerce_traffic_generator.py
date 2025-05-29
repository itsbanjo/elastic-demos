#!/usr/bin/env python3
"""
E-commerce Traffic Generator for Prometheus Metrics
Continuously generates realistic e-commerce traffic patterns with various HTTP status codes,
request durations, and user behavior patterns.
"""

import time
import random
import threading
from datetime import datetime
from prometheus_client import Counter, Histogram, Gauge, start_http_server, CollectorRegistry
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EcommerceTrafficGenerator:
    def __init__(self, port=8000):
        self.port = port
        self.registry = CollectorRegistry()
        self.running = False
        
        # Initialize Prometheus metrics
        self._init_metrics()
        
        # Traffic patterns configuration
        self.endpoints = [
            ('/api/products', 0.25, 'GET'),
            ('/api/products/{id}', 0.15, 'GET'),
            ('/api/cart', 0.12, 'GET'),
            ('/api/cart/add', 0.10, 'POST'),
            ('/api/cart/remove', 0.05, 'DELETE'),
            ('/api/orders', 0.08, 'POST'),
            ('/api/orders/{id}', 0.06, 'GET'),
            ('/api/users/profile', 0.07, 'GET'),
            ('/api/auth/login', 0.04, 'POST'),
            ('/api/auth/logout', 0.02, 'POST'),
            ('/api/search', 0.06, 'GET'),
        ]
        
        # Status code distributions (weighted)
        self.status_codes = {
            200: 0.85,  # Success
            201: 0.03,  # Created
            400: 0.04,  # Bad Request
            401: 0.02,  # Unauthorized
            403: 0.01,  # Forbidden
            404: 0.03,  # Not Found
            500: 0.015, # Internal Server Error
            502: 0.01,  # Bad Gateway
            503: 0.005  # Service Unavailable
        }
        
        # Response time patterns (in seconds)
        self.response_time_patterns = {
            'fast': (0.01, 0.1),      # Fast responses
            'normal': (0.1, 0.5),     # Normal responses
            'slow': (0.5, 2.0),       # Slow responses
            'timeout': (2.0, 10.0)    # Very slow/timeout responses
        }
        
    def _init_metrics(self):
        """Initialize Prometheus metrics"""
        
        # Total requests counter
        self.total_requests = Counter(
            'total_requests',
            'The total number of requests serviced by this API',
            registry=self.registry
        )
        
        # Request duration histogram
        self.request_duration = Histogram(
            'request_duration_seconds',
            'The duration in seconds between the response to a request',
            ['status_code', 'method', 'endpoint'],
            buckets=[0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24],
            registry=self.registry
        )
        
        # Active connections gauge
        self.active_connections = Gauge(
            'active_connections',
            'Number of active connections',
            registry=self.registry
        )
        
        # Request rate gauge
        self.request_rate = Gauge(
            'request_rate_per_second',
            'Current request rate per second',
            registry=self.registry
        )
        
        # Error rate gauge
        self.error_rate = Gauge(
            'error_rate_percentage',
            'Current error rate percentage',
            registry=self.registry
        )
        
        # Business metrics
        self.cart_additions = Counter(
            'cart_additions_total',
            'Total number of items added to cart',
            registry=self.registry
        )
        
        self.orders_placed = Counter(
            'orders_placed_total',
            'Total number of orders placed',
            registry=self.registry
        )
        
        self.revenue_total = Counter(
            'revenue_total_usd',
            'Total revenue in USD',
            registry=self.registry
        )
        
        # System metrics
        self.cpu_usage = Gauge(
            'cpu_usage_percentage',
            'CPU usage percentage',
            registry=self.registry
        )
        
        self.memory_usage = Gauge(
            'memory_usage_bytes',
            'Memory usage in bytes',
            registry=self.registry
        )
        
    def _get_weighted_choice(self, choices_dict):
        """Get a weighted random choice from a dictionary"""
        choices = list(choices_dict.keys())
        weights = list(choices_dict.values())
        return random.choices(choices, weights=weights)[0]
    
    def _generate_request_duration(self, status_code):
        """Generate realistic request duration based on status code"""
        if status_code == 200:
            pattern = random.choices(
                ['fast', 'normal', 'slow'],
                weights=[0.6, 0.35, 0.05]
            )[0]
        elif status_code in [400, 401, 403, 404]:
            pattern = 'fast'  # Client errors are typically fast
        elif status_code in [500, 502, 503]:
            pattern = random.choices(
                ['slow', 'timeout'],
                weights=[0.7, 0.3]
            )[0]
        else:
            pattern = 'normal'
        
        min_time, max_time = self.response_time_patterns[pattern]
        return random.uniform(min_time, max_time)
    
    def _simulate_single_request(self):
        """Simulate a single HTTP request"""
        # Choose endpoint
        endpoint_data = random.choices(
            self.endpoints,
            weights=[weight for _, weight, _ in self.endpoints]
        )[0]
        endpoint, _, method = endpoint_data
        
        # Choose status code
        status_code = self._get_weighted_choice(self.status_codes)
        
        # Generate request duration
        duration = self._generate_request_duration(status_code)
        
        # Update metrics
        self.total_requests.inc()
        self.request_duration.labels(
            status_code=str(status_code),
            method=method,
            endpoint=endpoint
        ).observe(duration)
        
        # Business logic simulation
        if endpoint == '/api/cart/add' and status_code == 200:
            self.cart_additions.inc()
        elif endpoint == '/api/orders' and status_code in [200, 201]:
            self.orders_placed.inc()
            # Simulate revenue (random order value between $10-500)
            revenue = random.uniform(10, 500)
            self.revenue_total.inc(revenue)
        
        return status_code, duration
    
    def _traffic_burst_pattern(self):
        """Generate traffic with realistic burst patterns"""
        base_rps = 50  # Base requests per second
        
        while self.running:
            current_time = datetime.now()
            hour = current_time.hour
            minute = current_time.minute
            
            # Simulate daily traffic patterns
            if 9 <= hour <= 11 or 13 <= hour <= 15 or 19 <= hour <= 21:
                # Peak hours
                traffic_multiplier = random.uniform(2.0, 4.0)
            elif 6 <= hour <= 8 or 12 <= hour <= 13 or 16 <= hour <= 18:
                # High traffic hours
                traffic_multiplier = random.uniform(1.5, 2.5)
            elif 22 <= hour <= 23 or 0 <= hour <= 6:
                # Low traffic hours
                traffic_multiplier = random.uniform(0.2, 0.6)
            else:
                # Normal traffic
                traffic_multiplier = random.uniform(0.8, 1.2)
            
            # Add some randomness for bursts
            if random.random() < 0.05:  # 5% chance of traffic spike
                traffic_multiplier *= random.uniform(3, 8)
                logger.info(f"Traffic spike! Multiplier: {traffic_multiplier:.2f}")
            
            target_rps = int(base_rps * traffic_multiplier)
            self.request_rate.set(target_rps)
            
            # Generate requests for this second
            requests_this_second = []
            for _ in range(target_rps):
                thread = threading.Thread(target=self._simulate_single_request)
                requests_this_second.append(thread)
                thread.start()
            
            # Wait for all requests to complete or timeout
            for thread in requests_this_second:
                thread.join(timeout=0.1)
            
            time.sleep(1)
    
    def _update_system_metrics(self):
        """Update system performance metrics"""
        while self.running:
            # Simulate realistic system metrics
            base_connections = 100
            connection_variance = random.randint(-20, 50)
            self.active_connections.set(max(0, base_connections + connection_variance))
            
            # Simulate CPU usage (correlated with request rate)
            current_rps = self.request_rate._value._value if hasattr(self.request_rate._value, '_value') else 50
            base_cpu = min(80, current_rps * 0.5 + random.uniform(-10, 10))
            self.cpu_usage.set(max(0, min(100, base_cpu)))
            
            # Simulate memory usage (gradually increasing with some fluctuation)
            base_memory = 512 * 1024 * 1024  # 512MB base
            memory_variance = random.randint(-50 * 1024 * 1024, 100 * 1024 * 1024)
            self.memory_usage.set(base_memory + memory_variance)
            
            time.sleep(10)  # Update every 10 seconds
    
    def _calculate_error_rate(self):
        """Calculate and update error rate"""
        while self.running:
            try:
                # This is a simplified calculation - in production you'd use proper time windows
                time.sleep(30)  # Calculate every 30 seconds
                
                # Simulate error rate calculation
                error_rate = random.uniform(0.5, 5.0)  # 0.5% to 5% error rate
                self.error_rate.set(error_rate)
                
            except Exception as e:
                logger.error(f"Error calculating error rate: {e}")
            
    def start(self):
        """Start the traffic generator"""
        logger.info(f"Starting e-commerce traffic generator on port {self.port}")
        
        # Start Prometheus metrics server
        start_http_server(self.port, registry=self.registry)
        logger.info(f"Prometheus metrics available at http://localhost:{self.port}/metrics")
        
        self.running = True
        
        # Start background threads
        traffic_thread = threading.Thread(target=self._traffic_burst_pattern, daemon=True)
        system_thread = threading.Thread(target=self._update_system_metrics, daemon=True)
        error_thread = threading.Thread(target=self._calculate_error_rate, daemon=True)
        
        traffic_thread.start()
        system_thread.start()
        error_thread.start()
        
        logger.info("Traffic generation started. Press Ctrl+C to stop.")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping traffic generator...")
            self.stop()
    
    def stop(self):
        """Stop the traffic generator"""
        self.running = False
        logger.info("Traffic generator stopped")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='E-commerce Traffic Generator for Prometheus')
    parser.add_argument('--port', type=int, default=8000, 
                       help='Port to serve Prometheus metrics (default: 8000)')
    parser.add_argument('--verbose', action='store_true', 
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    generator = EcommerceTrafficGenerator(port=args.port)
    generator.start()

if __name__ == '__main__':
    main()
