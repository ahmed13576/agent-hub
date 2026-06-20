import json

db = json.load(open('data/database.json'))
print(f'Items in DB: {len(db)}')

enriched = [i for i in db if i.get('enriched_at')]
print(f'Enriched: {len(enriched)}')

has_score = [i for i in db if isinstance(i.get('relevance_score'), (int, float))]
print(f'Has relevance_score: {len(has_score)}')

if db:
    print(f'Sample keys: {list(db[0].keys())}')
    print(f'Sample title: {db[0].get("title", "N/A")}')
    print(f'Sample source: {db[0].get("source", "N/A")}')
