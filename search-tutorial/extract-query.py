from search import Search
import csv

es = Search()
results = es.search(
    query={
        'match_all': {}
    },
    size=1000  # Increase this number to get more results, max is usually 10000
)

with open('all_products.csv', 'w', newline='', encoding='utf-8') as f:
   writer = csv.writer(f)
   writer.writerow(['Name', 'Description'])
   for hit in results['hits']['hits']:
       writer.writerow([
           hit['_source']['name'],
           hit['_source']['description']
       ])