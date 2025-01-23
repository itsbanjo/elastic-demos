import json
from pprint import pprint
import os
import time

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv()

class Search:
    def __init__(self):
        self.es = Elasticsearch(cloud_id=os.environ['ELASTIC_CLOUD_ID'],
                              api_key=os.environ['ELASTIC_API_KEY'])
        self.product_index = 'search-dev-spark-product-index'
        self.autocomplete_index = 'search-dev-spark-product-autocomplete'
        
    def search(self, **query_args):
        return self.es.search(index=self.product_index, **query_args)
    
    def get(self, **query_args):
        return self.es.get(index=self.product_index, **query_args)
    
    def suggest(self, text):
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
    
    def add_suggestion(self, doc):
        return self.es.index(index=self.autocomplete_index, document=doc)