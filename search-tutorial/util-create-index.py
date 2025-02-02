from search import Search

es = Search()

mapping = {
    "settings": {
        "analysis": {
            "analyzer": {
                "trigram": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "shingle"]
                }
            },
            "filter": {
                "shingle": {
                    "type": "shingle",
                    "min_shingle_size": 2,
                    "max_shingle_size": 3
                }
            }
        }
    },
    "mappings": {
        "properties": {
            "suggest": {
                "type": "completion",
                "analyzer": "simple",
                "preserve_separators": True,
                "preserve_position_increments": True,
                "max_input_length": 50
            },
            "name": {
                "type": "text",
                "fields": {
                    "trigram": {
                        "type": "text",
                        "analyzer": "trigram"
                    }
                }
            },
            "description": {"type": "text"}
        }
    }
}

# Create index
es.es.indices.create(index="search-dev-spark-product-autocomplete", body=mapping)