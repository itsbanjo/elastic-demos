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
        self.search_index = 'search-dev-spark-product-index'
        self.autocomplete_index = 'search-dev-spark-product-autocomplete'
        client_info = self.es.info()
        print('Connected to Elasticsearch!')
        pprint(client_info.body)

    def search(self, **query_args):
        return self.es.search(index=self.search_index, **query_args)

# search.py

    def get_suggestions(self, term):
        try:
            suggest_query = {
                'query': {
                    'prefix': {
                        'name': term
                    }
                },
                'size': 10
            }
        
            response = self.es.search(
                index=self.autocomplete_index,
                body=suggest_query
            )
        
            suggestions = []
            for hit in response['hits']['hits']:
                if 'suggestions' in hit['_source']:
                    for suggestion in hit['_source']['suggestions']:
                        if suggestion.lower().startswith(term.lower()):
                            suggestions.append({
                                'value': suggestion,
                                'label': suggestion
                            })
        
            return suggestions
            
        except Exception as e:
            print(f"Error getting suggestions: {e}")
            return []