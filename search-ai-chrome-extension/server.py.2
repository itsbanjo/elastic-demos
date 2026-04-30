import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from elasticsearch import Elasticsearch
from openai import OpenAI
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Initialize clients
es_client = Elasticsearch(
    cloud_id=os.environ.get("ELASTIC_CLOUD_ID"),
    api_key=os.environ.get("ELASTIC_API_KEY")
)

openai_client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
)

# Configuration
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
SEARCH_INDEX = os.environ.get("SEARCH_INDEX", "search-spark-products-all-segments")

def search_semantic_body(query, website=None):
    """
    Simple semantic search using ELSER on semantic_body field only
    """
    try:
        # Build the nested query for semantic_body
        bool_query = {
            "must": [
                {
                    "nested": {
                        "path": "semantic_body.inference.chunks",
                        "query": {
                            "sparse_vector": {
                                "inference_id": ".elser-2-elasticsearch",
                                "field": "semantic_body.inference.chunks.embeddings",
                                "query": query
                            }
                        },
                        "inner_hits": {
                            "size": 10,
                            "name": "semantic_body",
                            "_source": ["text"]
                        }
                    }
                }
            ]
        }
        
        # Add website filter if provided
        if website:
            bool_query["must"].append({
                "term": {"url_host": website}
            })

        es_query = {
            "query": {"bool": bool_query},
            "size": 10,
            "_source": [
                "name", "title", "description", "price", "sku", "url", 
                "image", "color", "meta_description", "url_host"
            ]
        }

        logger.info(f"Searching index: {SEARCH_INDEX}")
        logger.info(f"Query: {query}")
        
        result = es_client.search(index=SEARCH_INDEX, body=es_query)
        
        logger.info(f"Found {len(result['hits']['hits'])} results")
        return result["hits"]["hits"]
        
    except Exception as e:
        logger.error(f"Elasticsearch search error: {str(e)}")
        raise

def extract_products(results):
    """
    Extract product data from search results
    """
    products = []
    
    for hit in results:
        source = hit["_source"]
        
        # Get product name from available fields
        name = source.get('name') or source.get('title') or 'Unknown Product'
        
        # Skip if no meaningful name
        if not name or name == 'Unknown Product':
            continue
            
        product = {
            "name": name,
            "price": source.get('price'),
            "url": source.get('url'),
            "image": source.get('image'),
            "sku": source.get('sku'),
            "description": source.get('description') or source.get('meta_description', ''),
            "color": source.get('color')
        }
        
        products.append(product)
        logger.info(f"Added product: {name}")
    
    return products

def create_context(results, products):
    """
    Create context from search results and semantic chunks
    """
    context = ""
    
    for i, hit in enumerate(results, 1):
        source = hit["_source"]
        context_parts = []
        
        # Extract text from semantic_body inner_hits
        if 'inner_hits' in hit and 'semantic_body' in hit['inner_hits']:
            for inner_hit in hit['inner_hits']['semantic_body']['hits']['hits']:
                text = inner_hit['_source'].get('text', '')
                if text:
                    context_parts.append(f"Content: {text}")
        
        # Add product metadata if available
        if source.get('name'):
            context_parts.append(f"Product: {source['name']}")
        if source.get('price'):
            context_parts.append(f"Price: ${source['price']}")
        if source.get('color'):
            context_parts.append(f"Color: {source['color']}")
        if source.get('url'):
            context_parts.append(f"URL: {source['url']}")

        if context_parts:
            context += f"[{i}] " + ' | '.join(context_parts) + "\n\n"

    # Add product summary
    if products:
        context += "\nAVAILABLE PRODUCTS:\n"
        for i, product in enumerate(products, 1):
            context += f"Product {i}: {product['name']}"
            if product['price']:
                context += f" - ${product['price']}"
            context += "\n"

    return context

def generate_response(context, question):
    """
    Generate OpenAI response
    """
    prompt = f"""
You are a helpful shopping assistant for Spark NZ. Answer questions about products using only the provided context.

Instructions:
- Be conversational and helpful
- When asked about COLORS or AVAILABILITY, always list ALL available options from the context organized by product type
- For color queries about phones, list all phone colors separately from accessory colors
- Look for color information in both the product names and the Color fields
- Example format for color questions: "iPhone 16 is available in these colors: Pink, Natural Titanium, White, Teal "
- Focus on helping customers find the right products
- Use markdown formatting

Context:
{context}
"""
    
    try:
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": question}
            ],
            temperature=0.7,
            max_tokens=800
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"OpenAI error: {str(e)}")
        raise

def generate_smart_suggestions(context, user_question, ai_response, products):
    """
    Generate smart follow-up query suggestions using LLM
    """
    try:
        # Create a summary of available products for context
        product_summary = ""
        if products:
            product_types = set()
            brands = set()
            price_ranges = []
            
            for product in products:
                if product.get('name'):
                    # Extract product type (rough categorization)
                    name_lower = product['name'].lower()
                    if 'iphone' in name_lower:
                        product_types.add('iPhone')
                    elif 'samsung' in name_lower:
                        product_types.add('Samsung Phone')
                    elif 'case' in name_lower:
                        product_types.add('Phone Case')
                    elif 'charger' in name_lower:
                        product_types.add('Charger')
                    elif 'cable' in name_lower:
                        product_types.add('Cable')
                    
                    # Extract brand info
                    if 'apple' in name_lower:
                        brands.add('Apple')
                    elif 'samsung' in name_lower:
                        brands.add('Samsung')
                
                if product.get('price'):
                    try:
                        price = float(product['price'])
                        price_ranges.append(price)
                    except:
                        pass
            
            price_range_text = f"${min(price_ranges):.0f} - ${max(price_ranges):.0f}" if price_ranges else "Varied pricing"
            product_summary = f"""
Available Product Types: {', '.join(product_types) if product_types else 'Various electronics'}
Available Brands: {', '.join(brands) if brands else 'Multiple brands'}
Price Range: {price_range_text}
"""

        suggestions_prompt = f"""
Based on this customer conversation about products, generate 3 smart follow-up questions that would be helpful and relevant.

Customer Question: "{user_question}"
AI Response: "{ai_response}"

Context about available products:
{product_summary}

STRICT RULES for generating suggestions:
1. NEVER start questions with: "Would you", "What are your", "What's your", "Do you", "Are you"
2. NEVER ask about personal preferences, opinions, or user characteristics
3. NEVER ask conversational questions like "How can I help you?" or "What do you think?"
4. ONLY generate product-focused, actionable questions
5. Focus on: specifications, availability, comparisons, pricing, features, accessories, alternatives
6. Keep questions concise (under 8 words each)
7. Make questions specific to the products discussed

Good examples:
- "What colors are available for <product name?>"
- "Show me similar products for <product name>"
- "Compare <product name> models"
- "Check current pricing for <product name>"
- "What accessories are included for <product name>?"
- "View technical specifications for <product name>"
- "Find compatible cases for <product name>"
- "See customer reviews for <product name>"

Bad examples (NEVER generate):
- "Would you like to see more?"
- "What are your preferences?"
- "What's your budget?"
- "Do you need help with anything?"

Generate suggestions that help customers:
- Find specific product information
- Compare different options  
- Discover related/compatible products
- Check availability and pricing
- Learn about features and specs
- Upsell accessories related to the product

Return ONLY a JSON array of 3-4 question strings focused on PRODUCTS, not personal queries.
Example format: ["Check available colors", "Compare similar models", "View technical specs"]
"""

        logger.info("Generating smart suggestions...")
        
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that generates relevant follow-up questions for e-commerce conversations. Always respond with valid JSON array of strings."},
                {"role": "user", "content": suggestions_prompt}
            ],
            temperature=0.8,
            max_tokens=200
        )
        
        suggestions_text = response.choices[0].message.content.strip()
        logger.info(f"Raw suggestions response: {suggestions_text}")
        
        # Parse JSON response
        import json
        try:
            suggestions = json.loads(suggestions_text)
            if isinstance(suggestions, list) and len(suggestions) > 0:
                # Ensure we have strings and limit to 4 suggestions
                suggestions = [str(s).strip() for s in suggestions[:4] if s and str(s).strip()]
                logger.info(f"Parsed suggestions: {suggestions}")
                return suggestions
            else:
                logger.warning("Suggestions not in expected format")
                return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse suggestions JSON: {e}")
            # Fallback to default suggestions
            return [
                "What colors are available?",
                "Show me similar products",
                "Any current deals?",
                "What accessories do I need?"
            ]
        
    except Exception as e:
        logger.error(f"Error generating suggestions: {str(e)}")
        # Return default suggestions on error
        return [
            "What colors are available?",
            "Show me similar products", 
            "Any current deals?",
            "What accessories do I need?"
        ]

def extract_source_details(results):
    """
    Extract source details for clickable references
    """
    source_details = []
    
    for i, hit in enumerate(results, 1):
        source = hit["_source"]
        
        name = source.get('name') or source.get('title') or f"Product {i}"
        url = source.get('url', '')
        description = source.get('description') or source.get('meta_description', '')
        
        source_details.append({
            'index': i,
            'title': name,
            'url': url,
            'description': description[:100] + "..." if len(description) > 100 else description,
            'host': source.get('url_host', 'spark.co.nz')
        })
    
    return source_details

@app.route('/query', methods=['POST'])
def query_products():
    """
    Main query endpoint - now with smart suggestions
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        query = data.get('text', '').strip()
        website = data.get('website', '').strip()
        
        if not query:
            return jsonify({"error": "No query provided"}), 400

        logger.info(f"Processing query: '{query}' for website: '{website}'")
        
        # Step 1: Search using semantic_body only
        results = search_semantic_body(query, website)
        
        if not results:
            return jsonify({
                "response": "I couldn't find any relevant products for your query. Please try different keywords.",
                "sources": 0,
                "products": [],
                "sourceDetails": [],
                "suggestions": ["Browse all products", "Check new arrivals", "View popular items", "Contact support"]
            })
        
        # Step 2: Extract products
        products = extract_products(results)
        
        # Step 3: Create context and generate response
        context = create_context(results, products)
        ai_response = generate_response(context, query)
        
        # Step 4: Extract source details for clickable references
        source_details = extract_source_details(results)
        
        # Step 5: Generate smart suggestions
        smart_suggestions = generate_smart_suggestions(context, query, ai_response, products)
        
        return jsonify({
            "response": ai_response,
            "sources": len(results),
            "products": products,
            "sourceDetails": source_details,
            "suggestions": smart_suggestions,  # NEW: Smart query suggestions
            "website": website
        })
        
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        return jsonify({
            "error": "An error occurred processing your request. Please try again.",
            "details": str(e) if app.debug else None
        }), 500

@app.route('/status', methods=['GET'])
def status_check():
    """
    System status check
    """
    try:
        # Test Elasticsearch
        es_info = es_client.info()
        
        # Test OpenAI
        try:
            openai_client.models.list()
            openai_status = "connected"
        except:
            openai_status = "error"
        
        return jsonify({
            "status": "OK",
            "elasticsearch": {
                "status": "connected",
                "cluster_name": es_info.get("cluster_name", "unknown"),
                "index": SEARCH_INDEX
            },
            "openai": {
                "status": openai_status,
                "model": OPENAI_MODEL
            }
        })
        
    except Exception as e:
        return jsonify({
            "status": "Error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    # Validate required environment variables
    required_vars = ["ELASTIC_CLOUD_ID", "ELASTIC_API_KEY", "OPENAI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        exit(1)
    
    logger.info("Starting RAG server with smart suggestions")
    logger.info(f"Elasticsearch index: {SEARCH_INDEX}")
    logger.info(f"OpenAI model: {OPENAI_MODEL}")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
