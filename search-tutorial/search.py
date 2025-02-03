import os
import time
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
import elasticapm
from metrics import SearchMetrics

load_dotenv()

class Search:
    def __init__(self):
        self.es = Elasticsearch(cloud_id=os.environ['ELASTIC_CLOUD_ID'],
                              api_key=os.environ['ELASTIC_API_KEY'])
        self.product_index = 'search-dev-spark-product-index'
        self.autocomplete_index = 'search-dev-spark-product-autocomplete'
        
        # Get the existing APM client instead of creating a new one
        self.client = elasticapm.get_client()
        if self.client:
            self.metrics = self.client.metrics.register(SearchMetrics)

    def search(self, **query_args):
        start_time = time.time()
        results = self.es.search(index=self.product_index, **query_args)
        duration_ms = (time.time() - start_time) * 1000
        
        if hasattr(self, 'metrics'):
            self.metrics.record_search(
                duration_ms=duration_ms,
                hits_count=results['hits']['total']['value']
            )
        return results

    def suggest(self, text):
        if hasattr(self, 'metrics'):
            self.metrics.record_suggestion_request()
        suggestion_query = {
            "suggest": {
                "completion_suggestion": {
                    "prefix": text,
                    "completion": {
                        "field": "suggest",
                        "size": 5,
                        "skip_duplicates": True,
                        "fuzzy": {
                            "fuzziness": "AUTO"
                        }
                    }
                }
            }
        }
        return self.es.search(index=self.autocomplete_index, body=suggestion_query)

    def get(self, **query_args):
        return self.es.get(index=self.product_index, **query_args)

    def suggest_spelling(self, text):
        spell_query = {
            "suggest": {
                "text": text,
                "simple_phrase": {
                    "phrase": {
                        "field": "name.trigram",
                        "size": 1,
                        "gram_size": 3,
                        "direct_generator": [{
                            "field": "name.trigram",
                            "suggest_mode": "always"
                        }],
                        "highlight": {
                            "pre_tag": "<em>",
                            "post_tag": "</em>"
                        }
                    }
                }
            }
        }
        return self.es.search(index=self.product_index, body=spell_query)
