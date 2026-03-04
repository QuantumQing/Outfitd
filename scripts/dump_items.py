import sqlite3, json
conn = sqlite3.connect('data/trunk.db')
conn.row_factory = sqlite3.Row
trunk = conn.execute('SELECT id FROM trunk ORDER BY generated_at DESC LIMIT 1').fetchone()
items = conn.execute('SELECT id, product_name, brand, retailer, purchase_url, image_url FROM trunk_item WHERE trunk_id=? ORDER BY id', (trunk['id'],)).fetchall()
data = [dict(i) for i in items]
with open('/tmp/items.json', 'w') as f:
    json.dump(data, f, indent=2)
print(f"Dumped {len(data)} items to /tmp/items.json")
conn.close()
