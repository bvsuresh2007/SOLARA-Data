import requests, json, time
from dotenv import dotenv_values
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

env = dotenv_values('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
s = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
s.mount('https://', HTTPAdapter(max_retries=retries))
s.headers.update({
    'Authorization': f'token {env["ERPNEXT_API_KEY"]}:{env["ERPNEXT_API_SECRET"]}',
    'Content-Type': 'application/json'
})
BASE = env['ERPNEXT_URL']

orders = """SOL1194660 SOL1194654 SOL1194651 SOL1194647 SOL1194645 SOL1194644 SOL1194643 SOL1194639
SOL1194637 SOL1194635 SOL1194623 SOL1194622 SOL1194619 SOL1194616 SOL1194612 SOL1194610
SOL1194604 SOL1194603 SOL1194602 SOL1194600 SOL1194597 SOL1194595 SOL1194594 SOL1194591
SOL1194590 SOL1194588 SOL1194587 SOL1194585 SOL1194583 SOL1194580 SOL1194577 SOL1194575
SOL1194574 SOL1194571 SOL1194566 SOL1194562 SOL1194657 SOL1194632 SOL1194601 SOL1194564
SOL1194636 SOL1194593 SOL1194582 SOL1194560 SOL1194653 SOL1194625 SOL1194565 SOL1194572
SOL1194626 SOL1194605 SOL1194586 SOL1194634 SOL1194581 SOL1194663 SOL1194633 SOL1194579
SOL1194641 SOL1194661 SOL1194656 SOL1194655 SOL1194658 SOL1194627 SOL1194618 SOL1194617
SOL1194614 SOL1194471 SOL1194621 SOL1194606 SOL1194599 SOL1194608 SOL1194542 SOL1194426""".split()

orders = list(dict.fromkeys(orders))

# Step 1: Batch lookup - fetch all SOs with these order numbers in batches
print(f"Looking up {len(orders)} orders...")
so_by_order = {}  # oid -> list of SOs

batch_size = 20
for i in range(0, len(orders), batch_size):
    batch = orders[i:i+batch_size]
    numeric_batch = [o.replace('SOL', '') for o in batch]

    for field, values in [('custom_shopify_order_number', batch), ('shopify_order_number', batch), ('shopify_order_number', numeric_batch)]:
        try:
            r = s.get(f'{BASE}/api/resource/Sales Order', params={
                'filters': json.dumps([[field, 'in', values]]),
                'fields': json.dumps(['name', 'status', 'docstatus', 'amended_from', field]),
                'limit_page_length': 100
            }, timeout=30)
            for so in r.json().get('data', []):
                val = so.get(field, '')
                # Map back to SOL format
                oid = val if val.startswith('SOL') else f'SOL{val}'
                if oid not in so_by_order:
                    so_by_order[oid] = {}
                so_by_order[oid][so['name']] = so
        except Exception as e:
            print(f"  Batch error: {e}")
            time.sleep(2)

    time.sleep(0.3)

# Step 2: Check for amended versions of cancelled SOs
print("Checking amended SOs...")
for oid, sos in list(so_by_order.items()):
    cancelled = [name for name, so in sos.items() if so['docstatus'] == 2]
    for c_name in cancelled:
        for suffix in ['-1', '-2']:
            amended = c_name + suffix
            if amended not in sos:
                try:
                    r = s.get(f'{BASE}/api/resource/Sales Order/{amended}', params={
                        'fields': json.dumps(['name', 'status', 'docstatus', 'amended_from'])
                    }, timeout=15)
                    if r.status_code == 200:
                        so_by_order[oid][amended] = r.json()['data']
                except:
                    pass
    time.sleep(0.1)

# Step 3: Get items for active SOs
print("Fetching SO items...")
so_items = {}  # so_name -> items list
active_sos = set()
for oid, sos in so_by_order.items():
    for name, so in sos.items():
        if so['docstatus'] == 1:
            active_sos.add(name)

for i, so_name in enumerate(sorted(active_sos)):
    try:
        r = s.get(f'{BASE}/api/resource/Sales Order/{so_name}', params={
            'fields': json.dumps(['name', 'items'])
        }, timeout=15)
        if r.status_code == 200:
            items = [(item['item_code'], int(item['qty'])) for item in r.json()['data'].get('items', [])]
            so_items[so_name] = items
    except Exception as e:
        print(f"  Error fetching {so_name}: {e}")
        time.sleep(2)

    if (i + 1) % 15 == 0:
        time.sleep(1)
    else:
        time.sleep(0.2)

# Output
print(f'\n{"Order":<14} {"SO":<24} {"Status":<22} {"SKU Codes"}')
print('=' * 120)
for oid in orders:
    if oid not in so_by_order:
        print(f'{oid:<14} {"NOT FOUND":<24} {"":22}')
        continue

    sos = so_by_order[oid]
    # Pick active SO
    active = [(name, so) for name, so in sos.items() if so['docstatus'] == 1]
    if active:
        so_name, so = active[0]
        items = so_items.get(so_name, [])
        skus = ', '.join([f'{sku} x{qty}' for sku, qty in items])
        print(f'{oid:<14} {so_name:<24} {so["status"]:<22} {skus}')
    else:
        # Show cancelled
        for name, so in sos.items():
            print(f'{oid:<14} {name:<24} {"Cancelled":<22}')
