from search import Search

es = Search()

mapping = {
    "mappings": {
        "properties": {
            "suggest": {
                "type": "completion",
                "analyzer": "simple",
                "preserve_separators": True,
                "preserve_position_increments": True,
                "max_input_length": 50
            },
            "name": {"type": "text"},
            "description": {"type": "text"}
        }
    }
}

# Create index
es.es.indices.create(index="search-dev-spark-product-autocomplete", body=mapping)