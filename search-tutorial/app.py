import re
from flask import Flask, render_template, request
from search import Search

app = Flask(__name__)
es = Search()

if __name__ == "__main__":
    app.run(debug=True)

@app.get('/')
def index():
    return render_template('index.html')

@app.post('/')
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
                        'fields': ['name', 'description'],
                    }
                },
                **filters
            }
        },
        size=5,
        from_=from_
    )
    return render_template('index.html', results=results['hits']['hits'],
                           query=query, from_=from_,
                           total=results['hits']['total']['value'])

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
def get_document(doc_id):
    # Retrieve the document from Elasticsearch
    result = es.get(id=doc_id)    
    # Extract the necessary fields from the document's source
    source = result['_source']
    print(source)
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