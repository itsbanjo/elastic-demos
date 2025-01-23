from search import Search

es = Search()

# Get some products from the main index
results = es.search(
    query={"match_all": {}},
    size=100
)

# Add them to autocomplete index
for hit in results['hits']['hits']:
    source = hit['_source']
    es.add_suggestion({
        "suggest": [source['name']],
        "name": source['name'],
        "description": source.get('description', '')
    })