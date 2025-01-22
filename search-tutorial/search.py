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
        client_info = self.es.info()
        print('Connected to Elasticsearch!')
        pprint(client_info.body)

    def search(self, **query_args):
        return self.es.search(index='search-dev-spark-product-index', **query_args)

    def get_suggestions(self, query_text):
        try:
            # Using completion suggester
            suggest_query = {
                'suggest': {
                    'product-suggester': {
                        'prefix': query_text,
                        'completion': {
                            'field': 'name.suggest',
                            'fuzzy': {
                                'fuzziness': 1
                            },
                            'size': 10
                        }
                    }
                }
            }
            
            response = self.es.search(
                index='search-dev-spark-product-index',
                body=suggest_query
            )
            
            suggestions = []
            if 'suggest' in response:
                for suggestion in response['suggest']['product-suggester'][0]['options']:
                    suggestions.append({
                        'value': suggestion['text'],
                        'label': suggestion['text']
                    })
            
            # If completion suggester returns no results, fallback to search-as-you-type
            if not suggestions:
                search_query = {
                    'query': {
                        'multi_match': {
                            'query': query_text,
                            'type': 'bool_prefix',
                            'fields': [
                                'name',
                                'name._2gram',
                                'name._3gram'
                            ]
                        }
                    },
                    'size': 10
                }
                
                response = self.es.search(
                    index='search-dev-spark-product-index',
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