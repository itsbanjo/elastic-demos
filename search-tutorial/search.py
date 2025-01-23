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
    
    def get(self, **query_args):
        return self.es.get(index='search-dev-spark-product-index', **query_args)