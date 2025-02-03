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
        self.client = elasticapm.get_client()
        if self.client:
            self.metrics = self.client.metrics.register(SearchMetrics)

    @elasticapm.capture_span("elasticsearch_search")
    def search(self, **query_args):
        start_time = time.time()
        self.client.begin_transaction("search")
        try:
            results = self.es.search(index=self.product_index, **query_args)
            duration_ms = (time.time() - start_time) * 1000
            
            if hasattr(self, 'metrics'):
                self.metrics.record_search(
                    duration_ms=duration_ms,
                    hits_count=results['hits']['total']['value']
                )
            self.client.end_transaction("search", "success")
            return results
        except Exception as e:
            self.client.end_transaction("search", "error")
            raise e

    @elasticapm.capture_span("elasticsearch_suggest")
    def suggest(self, text):
        if hasattr(self, 'metrics'):
            self.metrics.record_suggestion_request()
        
        self.client.begin_transaction("suggest")
        try:
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
            results = self.es.search(index=self.autocomplete_index, body=suggestion_query)
            self.client.end_transaction("suggest", "success")
            return results
        except Exception as e:
            self.client.end_transaction("suggest", "error")
            raise e

    @elasticapm.capture_span("elasticsearch_get")
    def get(self, **query_args):
        self.client.begin_transaction("get_document")
        try:
            result = self.es.get(index=self.product_index, **query_args)
            self.client.end_transaction("get_document", "success")
            return result
        except Exception as e:
            self.client.end_transaction("get_document", "error")
            raise e

    @elasticapm.capture_span("elasticsearch_suggest_spelling")
    def suggest_spelling(self, text):
        self.client.begin_transaction("spell_check")
        try:
            spell_query = {
                "suggest": {
                    "simple_phrase": {
                        "text": text,
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
            results = self.es.search(index=self.product_index, body=spell_query)
            self.client.end_transaction("spell_check", "success")
            return results
        except Exception as e:
            self.client.end_transaction("spell_check", "error")
            raise e
