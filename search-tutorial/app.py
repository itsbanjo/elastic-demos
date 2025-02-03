import os
import re
from elasticapm.contrib.flask import ElasticAPM
from flask import Flask, render_template, request, jsonify
from search import Search
import elasticapm

app = Flask(__name__)

app.config['ELASTIC_APM'] = {
    'SERVICE_NAME': os.getenv('ELASTIC_APM_SERVICE_NAME', 'spark-search'),
    'SECRET_TOKEN': os.getenv('ELASTIC_APM_SECRET_TOKEN'),
    'SERVER_URL': os.getenv('ELASTIC_APM_SERVER_URL'),
    'ENVIRONMENT': os.getenv('ELASTIC_APM_ENVIRONMENT', 'development'),
    'METRICS_INTERVAL': '30s'
}

apm = ElasticAPM(app)

es = Search()

if __name__ == "__main__":
    app.run(debug=True)

@app.get('/')

def index():
    return render_template('index.html')

@app.get('/suggest')
@elasticapm.capture_span()
def suggest():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
        
    suggestions = es.suggest(query)
    options = []
    if 'suggest' in suggestions:
        for suggestion in suggestions['suggest']['completion_suggestion'][0]['options']:
            options.append({
                'text': suggestion['text'],
                'score': suggestion['_score']
            })
    return jsonify(options)

@app.post('/')
@elasticapm.capture_span()
def handle_search():
    query = request.form.get('query', '')
    filters, parsed_query = extract_filters(query)
    from_ = request.form.get('from_', type=int, default=0)

    results = es.search(
        query={
            'bool': {
                'must': {
                    'multi_match': {
                        'query': parsed_query,
                        'fields': ['name', 'description', 'sku']
                    }
                },
                **filters
            }
        },
        size=5,
        from_=from_
    )
    suggestion = None

    if results['hits']['total']['value'] == 0:
        spell_results = es.suggest_spelling(parsed_query)
        if spell_results.get('suggest') and spell_results['suggest']['simple_phrase'][0]['options']:
            suggestion = spell_results['suggest']['simple_phrase'][0]['options'][0]['text']

    return render_template('index.html', results=results['hits']['hits'],
                           query=query, from_=from_,
                           total=results['hits']['total']['value'],
                           suggestion=suggestion)

def extract_filters(query):
    filters = []

    filter_regex = r'category:([^\s]+)\s*'
    m = re.search(filter_regex, query)
    if m:
        filters.append({
            'term': {
                'category.keyword': {
                    'value': m.group(1)
                }
            }
        })
        query = re.sub(filter_regex, '', query).strip()

    return {'filter': filters}, query


@app.get('/document/<doc_id>')
@elasticapm.capture_span()
def get_document(doc_id):
    # Retrieve the document from Elasticsearch
    result = es.get(id=doc_id)    
    # Extract the necessary fields from the document's source
    source = result['_source']
    name = source.get('name', 'No Name')
    color = source.get('color', 'No Color')
    description = source.get('description', 'No Description')
    price = source.get('price', 'N/A')
    capacity = source.get('capacity', 'N/A')
    last_crawled_at = source.get('last_crawled_at', 'N/A')
    domain = 'https://www.spark.co.nz'
    image = [domain + img for img in source.get('image', [])]
    url = source.get('url', '#')
    links = source.get('links', [])
    variants = source.get('variants', [])
    # Pass the extracted fields to the template
    return render_template(
        'document.html',
        name=name,
        color=color,
        description=description,
        price=price,
        capacity=capacity,
        last_crawled_at=last_crawled_at,
        image=image,
        url=url,
        links=links,
        variants=variants
    )

@app.route('/api/suggestions', methods=['GET'])
@elasticapm.capture_span()
def get_suggestions():
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify({
            'suggestions': [],
            'popular': [],
            'categories': []
        })

    # Get completion suggestions
    completion_results = es.search(
        query={
            'suggest': {
                'completion_suggestion': {
                    'prefix': query,
                    'completion': {
                        'field': 'name.completion',
                        'size': 5,
                        'fuzzy': {
                            'fuzziness': 'AUTO'
                        }
                    }
                }
            }
        }
    )

    # Get category suggestions
    category_results = es.search(
        query={
            'size': 0,
            'aggs': {
                'categories': {
                    'terms': {
                        'field': 'category.keyword',
                        'include': f'.*{query}.*'
                    }
                }
            }
        }
    )

    suggestions = []
    if 'suggest' in completion_results:
        for suggestion in completion_results['suggest']['completion_suggestion'][0].get('options', []):
            suggestions.append(suggestion['text'])

    categories = []
    if 'aggregations' in category_results:
        for bucket in category_results['aggregations']['categories']['buckets'][:3]:
            categories.append(bucket['key'])

    return jsonify({
        'suggestions': suggestions,
        'categories': categories,
        'popular': []  # Implement based on your needs
    })

@app.route('/api/correct', methods=['GET'])
@elasticapm.capture_span()
def get_correction():
    query = request.args.get('q', '')
    
    correction_results = es.search(
        query={
            'suggest': {
                'term_suggestion': {
                    'text': query,
                    'term': {
                        'field': 'name',
                        'suggest_mode': 'popular',
                        'max_edits': 2
                    }
                }
            }
        }
    )
