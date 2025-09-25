from elasticapm.metrics.base_metrics import SpanBoundMetricSet
import time

class SearchMetrics(SpanBoundMetricSet):
    def __init__(self, registry):
        super().__init__(registry)
        # Initialize counters and histograms
        self._search_latency = self.histogram("search.latency", unit="ms", buckets=[5, 10, 25, 50, 100, 250, 500])
        self._search_requests = self.counter("search.requests")
        self._zero_results = self.counter("search.zero_results")
        self._suggestion_requests = self.counter("search.suggestions.requests")
        self._suggestion_clicks = self.counter("search.suggestions.clicks")
        
    def record_search(self, duration_ms, hits_count):
        """Record search metrics"""
        self._search_latency.update(duration_ms)
        self._search_requests.inc()
        if hits_count == 0:
            self._zero_results.inc()
            
    def record_suggestion_request(self):
        """Record suggestion request"""
        self._suggestion_requests.inc()
        
    def record_suggestion_click(self):
        """Record when a user clicks a suggestion"""
        self._suggestion_clicks.inc()
