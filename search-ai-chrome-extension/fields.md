# Elasticsearch Index Schema Requirements

## Overview

This document outlines the minimum required fields for the RAG Chatbot to function properly. The schema is designed to be flexible and work with most e-commerce product catalogs with minimal customization.

---

## Minimum Required Fields

### Core Product Fields

These fields are essential for basic functionality:

| Field Name | Type | Required | Description | Example |
|------------|------|----------|-------------|---------|
| `name` | `text` | **Yes** | Primary product name or title | "Wireless Bluetooth Headphones" |
| `description` | `text` | No | Detailed product description | "Premium over-ear headphones with noise cancellation..." |
| `price` | `float` | No | Current product price | 149.99 |
| `url` | `keyword` | No | Product page URL | "https://example.com/products/headphones-123" |
| `image` | `keyword` | No | Product image path or URL | "/images/headphones-123.jpg" |
| `sku` | `keyword` | No | Stock keeping unit / product ID | "WBH-001-BLK" |

### Semantic Search Fields

Required for ELSER semantic search functionality:

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| `semantic_body.inference.chunks` | `nested` | **Yes** | ELSER embedding storage |
| `semantic_body.inference.chunks.text` | `text` | **Yes** | Text chunks for search |
| `semantic_body.inference.chunks.embeddings` | `sparse_vector` | **Yes** | ELSER sparse vectors |

### Optional Enhancement Fields

These fields enhance the user experience but aren't required:

| Field Name | Type | Required | Description | Example |
|------------|------|----------|-------------|---------|
| `title` | `text` | No | Alternative product title | "Premium Wireless Headphones - Black" |
| `color` | `keyword` | No | Product color | "Black", "Silver", "Red" |
| `brand` | `keyword` | No | Product brand | "AudioTech", "SoundPro" |
| `category` | `keyword` | No | Product category | "Electronics", "Audio" |
| `meta_description` | `text` | No | SEO description | "Shop the best wireless headphones..." |
| `url_host` | `keyword` | No | Website hostname for filtering | "example.com" |
| `rating` | `float` | No | Customer rating | 4.5 |
| `reviews_count` | `integer` | No | Number of reviews | 234 |
| `in_stock` | `boolean` | No | Stock availability | true |

---

## Minimal Working Schema

### Basic Index Mapping

Here's a minimal Elasticsearch mapping that will work with the application:

```json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "description": {
        "type": "text"
      },
      "price": {
        "type": "float"
      },
      "url": {
        "type": "keyword"
      },
      "image": {
        "type": "keyword"
      },
      "sku": {
        "type": "keyword"
      },
      "semantic_body": {
        "properties": {
          "inference": {
            "properties": {
              "chunks": {
                "type": "nested",
                "properties": {
                  "text": {
                    "type": "text"
                  },
                  "embeddings": {
                    "type": "sparse_vector"
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

---

## Sample Document Structure

### Minimal Document

The absolute minimum document that will work:

```json
{
  "name": "Wireless Bluetooth Headphones",
  "semantic_body": {
    "inference": {
      "chunks": [
        {
          "text": "Wireless Bluetooth Headphones with noise cancellation and 30-hour battery life",
          "embeddings": {
            /* ELSER vectors generated automatically */
          }
        }
      ]
    }
  }
}
```

### Complete Document Example

A fully populated document with all optional fields:

```json
{
  "name": "Wireless Bluetooth Headphones",
  "title": "Premium Wireless Headphones - Black Edition",
  "description": "Experience premium sound quality with our wireless Bluetooth headphones featuring active noise cancellation, 30-hour battery life, and comfortable over-ear design.",
  "price": 149.99,
  "url": "https://example.com/products/headphones-wbh001",
  "image": "/images/products/headphones-wbh001-black.jpg",
  "sku": "WBH-001-BLK",
  "color": "Black",
  "brand": "AudioTech",
  "category": "Electronics > Audio > Headphones",
  "meta_description": "Shop AudioTech Wireless Bluetooth Headphones with noise cancellation. Free shipping on orders over $50.",
  "url_host": "example.com",
  "rating": 4.5,
  "reviews_count": 234,
  "in_stock": true,
  "semantic_body": {
    "inference": {
      "chunks": [
        {
          "text": "Wireless Bluetooth Headphones with active noise cancellation",
          "embeddings": {
            /* ELSER vectors */
          }
        },
        {
          "text": "30-hour battery life and quick charging support",
          "embeddings": {
            /* ELSER vectors */
          }
        },
        {
          "text": "Premium over-ear design with memory foam cushions for all-day comfort",
          "embeddings": {
            /* ELSER vectors */
          }
        }
      ]
    }
  }
}
```

---

## Field Usage by Application

### Search Phase

The application uses these fields during search:

- `semantic_body.inference.chunks.embeddings` - Primary semantic search
- `semantic_body.inference.chunks.text` - Retrieved for context building
- `url_host` - Optional filtering by website (if provided)

### Response Generation Phase

These fields are extracted and used for context:

- `name` or `title` - Product identification
- `description` - Product details
- `price` - Pricing information
- `color` - Color options
- `brand` - Brand information
- `url` - Product links

### Display Phase

These fields populate the UI components:

**Product Cards:**
- `name` - Card title
- `image` - Product image
- `price` - Price display
- `url` - Click-through link
- `category` - Category label

**References Section:**
- `name` or `title` - Reference title
- `url` - Clickable link
- `description` or `meta_description` - Tooltip text

---

## ELSER Configuration

### Setting Up ELSER

The semantic search requires ELSER v2 to be deployed in your Elasticsearch cluster:

1. **Deploy the ELSER model:**
```bash
POST _ml/trained_models/.elser_model_2/deployment/_start
```

2. **Create an inference pipeline:**
```json
PUT _ingest/pipeline/elser-ingest-pipeline
{
  "processors": [
    {
      "inference": {
        "model_id": ".elser_model_2",
        "target_field": "semantic_body",
        "field_map": {
          "description": "text_field"
        },
        "inference_config": {
          "text_expansion": {
            "results_field": "tokens"
          }
        }
      }
    }
  ]
}
```

3. **Index documents with the pipeline:**
```json
PUT /product-catalog/_doc/1?pipeline=elser-ingest-pipeline
{
  "name": "Wireless Headphones",
  "description": "Premium wireless headphones with noise cancellation..."
}
```

### Alternative: Pre-computed Embeddings

If you're indexing documents with pre-computed ELSER embeddings, ensure the structure matches:

```json
{
  "semantic_body": {
    "inference": {
      "chunks": [
        {
          "text": "Your text chunk here",
          "embeddings": {
            "term1": 0.543,
            "term2": 0.234,
            /* ... sparse vector representation */
          }
        }
      ]
    }
  }
}
```

---

## Field Fallback Logic

The application includes fallback logic to handle missing fields gracefully:

### Product Name Resolution

```python
name = source.get('name') or source.get('title') or 'Unknown Product'
```

If `name` is missing, it tries `title`. If both are missing, displays "Unknown Product".

### Description Resolution

```python
description = source.get('description') or source.get('meta_description', '')
```

Falls back from `description` to `meta_description` to empty string.

### Image Handling

```python
image = source.get('image')
if image:
    display_image(image)
else:
    display_placeholder_icon()
```

If no image is provided, displays a placeholder box icon.

---

## Index Naming Convention

The application uses an environment variable to specify the index:

```bash
SEARCH_INDEX=product-catalog
```

You can name your index anything you want, just update this variable. For multiple indices, you could modify the code to support comma-separated values:

```python
SEARCH_INDICES = os.environ.get("SEARCH_INDICES", "products-us,products-eu,products-asia").split(",")
```

---

## Data Preparation Guidelines

### Creating Text Chunks

For optimal semantic search, break long descriptions into meaningful chunks:

**Bad (too long):**
```json
{
  "text": "This product features a 6.1-inch display, 128GB storage, 12MP camera, 5G connectivity, wireless charging, water resistance, face recognition, and comes in five colors with a one-year warranty and free shipping."
}
```

**Good (meaningful chunks):**
```json
{
  "chunks": [
    {"text": "6.1-inch OLED display with True Tone technology"},
    {"text": "128GB storage capacity"},
    {"text": "12MP dual camera system with night mode"},
    {"text": "5G connectivity for faster downloads"},
    {"text": "Available in five colors: black, white, blue, red, green"}
  ]
}
```

### Handling Missing Data

Not all products need all fields. The application handles missing data gracefully:

- **Missing price:** Won't display price in product card
- **Missing image:** Shows placeholder icon
- **Missing URL:** Product card won't be clickable
- **Missing description:** Uses product name only for context

---

## Performance Considerations

### Index Size

For optimal performance:

- **Small catalog** (< 10,000 products): Single index, no sharding needed
- **Medium catalog** (10,000 - 100,000): Single index, 2-3 shards
- **Large catalog** (> 100,000): Consider multiple indices or increased sharding

### Field Storage

To reduce storage and improve performance:

```json
{
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "index": true,
        "store": false  /* Don't store original, only index */
      },
      "url": {
        "type": "keyword",
        "index": false,  /* Don't index, only retrieve */
        "store": true
      }
    }
  }
}
```

Store fields you need to retrieve but don't need to search. Index fields you need to search but don't need original values.

---

## Validation Checklist

Before deploying, verify your index has:

- ✅ At least one document with a `name` field
- ✅ ELSER model deployed and accessible
- ✅ `semantic_body.inference.chunks` structure present
- ✅ Embeddings generated for at least some documents
- ✅ Index accessible with provided API key
- ✅ Environment variable `SEARCH_INDEX` matches your index name

### Test Query

Run this query to verify your index structure:

```json
POST /your-index/_search
{
  "size": 1,
  "_source": ["name", "price", "url", "image"],
  "query": {
    "nested": {
      "path": "semantic_body.inference.chunks",
      "query": {
        "exists": {
          "field": "semantic_body.inference.chunks.embeddings"
        }
      }
    }
  }
}
```

If this returns documents, your index is properly configured.

---

## Migration from Existing Schemas

### If you have flat product documents:

```json
{
  "product_name": "Headphones",
  "product_price": 99.99,
  "product_desc": "Wireless headphones..."
}
```

Use Elasticsearch reindex API with a script to transform:

```json
POST _reindex
{
  "source": {
    "index": "old-products"
  },
  "dest": {
    "index": "new-products",
    "pipeline": "elser-ingest-pipeline"
  },
  "script": {
    "source": """
      ctx._source.name = ctx._source.remove('product_name');
      ctx._source.price = ctx._source.remove('product_price');
      ctx._source.description = ctx._source.remove('product_desc');
    """
  }
}
```

### If you have nested product variants:

```json
{
  "base_product": "Headphones",
  "variants": [
    {"color": "Black", "sku": "WBH-001-BLK"},
    {"color": "White", "sku": "WBH-001-WHT"}
  ]
}
```

Consider flattening to individual documents per variant or storing variant info in fields like `color`, `size`, etc.

---

## Troubleshooting

### "No search results found"

**Check:**
1. Does at least one document have the `name` field populated?
2. Are ELSER embeddings present in `semantic_body.inference.chunks.embeddings`?
3. Is the ELSER model deployed and running?
4. Does your query match the inference_id (`.elser-2-elasticsearch`)?

### "Products display without images"

**Check:**
1. Is the `image` field populated with valid paths?
2. Is the image path relative or absolute?
3. Does `getDomainForImages()` in overlay.js return the correct domain?
4. Are images accessible from the browser (CORS, permissions)?

### "Citations don't link to products"

**Check:**
1. Is the `url` field populated?
2. Are URLs absolute (starting with http:// or https://)?
3. Are URLs accessible from the user's browser?

---

## Example Index Creation Script

Here's a complete script to create an index from scratch:

```python
from elasticsearch import Elasticsearch

es = Elasticsearch(
    cloud_id="your_cloud_id",
    api_key="your_api_key"
)

# Create index with mapping
es.indices.create(
    index="product-catalog",
    body={
        "mappings": {
            "properties": {
                "name": {"type": "text"},
                "description": {"type": "text"},
                "price": {"type": "float"},
                "url": {"type": "keyword"},
                "image": {"type": "keyword"},
                "sku": {"type": "keyword"},
                "color": {"type": "keyword"},
                "brand": {"type": "keyword"},
                "semantic_body": {
                    "properties": {
                        "inference": {
                            "properties": {
                                "chunks": {
                                    "type": "nested",
                                    "properties": {
                                        "text": {"type": "text"},
                                        "embeddings": {"type": "sparse_vector"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
)

# Index sample product
sample_product = {
    "name": "Wireless Bluetooth Headphones",
    "description": "Premium over-ear headphones with active noise cancellation",
    "price": 149.99,
    "url": "https://example.com/products/headphones-001",
    "image": "/images/headphones-001.jpg",
    "sku": "WBH-001",
    "color": "Black",
    "brand": "AudioTech"
}

es.index(
    index="product-catalog",
    id="1",
    body=sample_product,
    pipeline="elser-ingest-pipeline"  # Generates embeddings automatically
)

print("Index created and sample product indexed!")
```

---

## Summary

**Absolute minimum required fields:**
1. `name` - Product identification
2. `semantic_body.inference.chunks` - ELSER search capability

**Recommended for good UX:**
3. `price` - Display pricing
4. `url` - Enable click-through
5. `image` - Show product visuals
6. `description` - Provide context

**Optional enhancements:**
7. `color`, `brand`, `category` - Filter and categorize
8. `rating`, `reviews_count` - Social proof
9. `in_stock` - Availability status

The schema is designed to be flexible. Start with the minimum and add fields as needed for your specific use case.
