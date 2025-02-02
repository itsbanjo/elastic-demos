from search import Search

es = Search()

# Update product index mapping
product_mapping = {
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
            "name": {
                "type": "text",
                "fields": {
                    "trigram": {
                        "type": "text",
                        "analyzer": "trigram"
                    }
                }
            }
        }
    }
}

# Delete and recreate product index
es.es.indices.delete(index=es.product_index)
es.es.indices.create(index=es.product_index, body=product_mapping)