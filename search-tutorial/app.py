import re
from flask import Flask, render_template, request, jsonify
from search import Search

app = Flask(__name__)
es = Search()

@app.get('/')
def index():
    return render_template('index.html')

@app.post('/')
def handle_search():
    query = request.form.get('query', '')
    results = es.search(
        query={
            'match': {
                'name': {
                    'query': query
                }
            }
        }
    )
    return render_template('index.html', results=results['hits']['hits'],
                         query=query, from_=0,
                         total=results['hits']['total']['value'])

@app.route('/autocomplete')
def autocomplete():
    query = request.args.get('term', '')
    if not query:
        return jsonify([])
    
    suggestions = es.get_suggestions(query)
    return jsonify(suggestions)

@app.get('/document/<id>')
def get_document(id):
    return 'Document not found'