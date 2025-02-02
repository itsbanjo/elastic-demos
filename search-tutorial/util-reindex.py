from search import Search
from elasticsearch.helpers import bulk

es = Search()

# Get all products from main index
results = es.search(
    query={"match_all": {}},
    size=10000  # Adjust based on your data size
)

# Prepare bulk actions
actions = []
for hit in results['hits']['hits']:
    source = hit['_source']
    actions.append({
        '_index': es.autocomplete_index,
        '_source': {
            "suggest": [source['name']],
            "name": source['name'],
            "description": source.get('description', '')
        }
    })

# Bulk index
if actions:
    bulk(es.es, actions)