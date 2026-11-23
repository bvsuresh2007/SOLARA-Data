import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

# Get Shopify token for order lookup
r = requests.post(f'{BASE}/api/method/frappe.client.get_password',
                   headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
token = r.json().get('message', '')
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}

ghosts = [
    ('SOL1202977', 'SHP27-09272'),
    ('SOL1203097', 'SHP27-09408'),
]

for sol, so in ghosts:
    print(f"\n=== {sol} ({so}) ===")

    # Get SO with shopify_order_id
    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so}', headers=H, timeout=30)
    so_d = r_so.json().get('data', {})
    shopify_oid = so_d.get('shopify_order_id', '')
    print(f"  Shopify order ID: {shopify_oid}")

    # Show SO items with details
    print(f"  SO Items:")
    for i, it in enumerate(so_d.get('items', [])):
        ic = it.get('item_code', '')
        item_name = it.get('item_name', '')
        desc = it.get('description', '')[:80]
        rate = it.get('rate', 0)
        print(f"    [{i}] code='{ic}' name='{item_name}' rate={rate} desc={desc}")

    # Look up Shopify order to find what the ghost item should be
    if shopify_oid:
        try:
            r_shop = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json',
                                  headers=SHOP_H, timeout=15)
            order = r_shop.json().get('order', {})
            print(f"\n  Shopify line items:")
            for li in order.get('line_items', []):
                sku = li.get('sku', '')
                title = li.get('title', '')
                variant = li.get('variant_title', '')
                qty = li.get('quantity', 0)
                price = li.get('price', '')
                print(f"    SKU={sku} title='{title}' variant='{variant}' qty={qty} price={price}")
        except Exception as e:
            print(f"  Shopify lookup error: {str(e)[:80]}")

    time.sleep(0.5)
