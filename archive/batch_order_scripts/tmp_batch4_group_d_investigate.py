import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

r2 = requests.post(f'{BASE}/api/method/frappe.client.get_password',
    headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
token = r2.json().get('message', '')
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}

# Group D: Ghost SKU orders
orders = [
    ('SOL1204795', 'a49i51ruvk'),   # Prateek Gumber - 1 ghost + SOL-CKW-WSPA-101
    ('SOL1204921', '9666jb7jg8'),   # Keshav Krishan - 1 ghost + 4 others
    ('SOL1204933', '9u9s1bnaas'),   # Sheeru Gupta - 1 ghost + 5 others
]

for sol, ghost_child in orders:
    print(f'\n{"="*80}')
    print(f'=== {sol} | Ghost child: {ghost_child} ===')

    # Get SO
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','shopify_order_id','customer_name','grand_total','custom_order_type']),
                'limit_page_length': 1}, timeout=15)
    so = r_so.json().get('data', [{}])[0]
    so_name = so['name']
    shopify_oid = so.get('shopify_order_id', '')
    print(f'  SO: {so_name} | {so.get("customer_name","")} | {so.get("custom_order_type","")} | Total={so.get("grand_total",0)}')

    # Get SO items - full details of ghost
    r_full = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full = r_full.json().get('data', {})
    print(f'  SO Items:')
    for it in so_full.get('items', []):
        ic = it.get('item_code', '') or ''
        child_name = it.get('name', '')
        qty = int(it.get('qty', 0))
        rate = float(it.get('rate', 0) or 0)
        item_name = it.get('item_name', '') or ''
        desc = it.get('description', '') or ''
        shopify_item_id = it.get('shopify_item_id', '') or ''
        if not ic:
            print(f'    *** GHOST: child={child_name} | qty={qty} | rate={rate} | item_name="{item_name}" | desc="{desc[:80]}" | shopify_item_id={shopify_item_id}')
        else:
            print(f'    {ic} x{qty} @ {rate} | child={child_name}')

    # Get Shopify order items to identify ghost SKU
    if shopify_oid:
        r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
        sh_order = r_sh.json().get('order', {})
        print(f'  Shopify Items:')
        for li in sh_order.get('line_items', []):
            sku = li.get('sku', '')
            title = li.get('title', '')
            variant = li.get('variant_title', '')
            qty = li.get('quantity', 0)
            price = li.get('price', '')
            product_id = li.get('product_id', '')
            variant_id = li.get('variant_id', '')
            print(f'    SKU={sku} | "{title}" {variant} | qty={qty} | price={price} | prod_id={product_id} | var_id={variant_id}')

    # Check if the SKU exists on Atlas
    print(f'  Atlas item check:')
    if shopify_oid:
        for li in sh_order.get('line_items', []):
            sku = li.get('sku', '')
            if sku:
                r_item = requests.get(f'{BASE}/api/resource/Item/{sku}', headers=H, timeout=10)
                if r_item.status_code == 200:
                    it_data = r_item.json().get('data', {})
                    print(f'    {sku}: EXISTS | is_stock={it_data.get("is_stock_item",0)} | stock_uom={it_data.get("stock_uom","")}')
                else:
                    print(f'    {sku}: NOT FOUND on Atlas')

    time.sleep(0.5)
