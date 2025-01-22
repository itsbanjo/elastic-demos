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

    def get_suggestions(self, query_text):
        try:
            # Search in the autocomplete index first
            suggest_query = {
                'query': {
                    'prefix': {
                        'name': query_text
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
                suggestions.append({
                    'value': hit['_source']['name'],
                    'label': hit['_source']['name']
                })
            
            # If no suggestions found, try the main search index
            if not suggestions:
                search_query = {
                    'query': {
                        'match_phrase_prefix': {
                            'name': {
                                'query': query_text,
                                'max_expansions': 10
                            }
                        }
                    },
                    'size': 10
                }
                
                response = self.es.search(
                    index=self.search_index,
                    body=search_query
                )
                
                for hit in response['hits']['hits']:
                    suggestions.append({
                        'value': hit['_source']['name'],
                        'label': hit['_source']['name']
                    })
            
            return suggestions
            
        except Exception as e:
            print(f"Error getting suggestions: {e}")
            return []