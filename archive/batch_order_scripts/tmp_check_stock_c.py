import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

# Check stock for SOL-CI-DT-101
item = 'SOL-CI-DT-101'
r_bin = requests.get(f'{BASE}/api/resource/Bin', headers=H,
    params={'filters': json.dumps([['item_code','=',item],['warehouse','=','Main Warehouse - WTBBPL']]),
            'fields': json.dumps(['actual_qty','reserved_qty','projected_qty','ordered_qty']),
            'limit_page_length': 1}, timeout=15)
bins = r_bin.json().get('data', [])
if bins:
    b = bins[0]
    print(f'SOL-CI-DT-101 Stock:')
    print(f'  actual_qty = {b.get("actual_qty",0)}')
    print(f'  reserved_qty = {b.get("reserved_qty",0)}')
    print(f'  projected_qty = {b.get("projected_qty",0)}')
    print(f'  ordered_qty = {b.get("ordered_qty",0)}')
else:
    print(f'No Bin found for {item}')

# Check how many units needed across Group C
orders = ['SOL1204751','SOL1205004','SOL1205008','SOL1205037','SOL1205090']
total_needed = 0
items_needed = {}

for sol in orders:
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol],['docstatus','=',0]]),
                'fields': json.dumps(['name']),
                'limit_page_length': 1}, timeout=15)
    dns = r_dn.json().get('data', [])
    if dns:
        dn_name = dns[0]['name']
        r_dnf = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=15)
        d = r_dnf.json().get('data', {})
        print(f'\n{sol} ({dn_name}):')
        for it in d.get('items', []):
            ic = it.get('item_code', '')
            qty = int(it.get('qty', 0))
            print(f'  {ic} x{qty}')
            items_needed[ic] = items_needed.get(ic, 0) + qty

print(f'\n\nTotal items needed across Group C:')
for ic, qty in sorted(items_needed.items()):
    print(f'  {ic}: {qty} units')

# Check stock for all items
print(f'\nStock check for all items:')
for ic in sorted(items_needed.keys()):
    r_b = requests.get(f'{BASE}/api/resource/Bin', headers=H,
        params={'filters': json.dumps([['item_code','=',ic],['warehouse','=','Main Warehouse - WTBBPL']]),
                'fields': json.dumps(['actual_qty','reserved_qty','projected_qty']),
                'limit_page_length': 1}, timeout=15)
    bs = r_b.json().get('data', [])
    if bs:
        b = bs[0]
        avail = float(b.get('actual_qty',0)) - float(b.get('reserved_qty',0))
        print(f'  {ic}: actual={b.get("actual_qty",0)} reserved={b.get("reserved_qty",0)} available={avail} | need={items_needed[ic]}')
    else:
        # Check if it's a product bundle
        r_pb = requests.get(f'{BASE}/api/resource/Product Bundle', headers=H,
            params={'filters': json.dumps([['name','=',ic]]),
                    'fields': json.dumps(['name']),
                    'limit_page_length': 1}, timeout=15)
        pbs = r_pb.json().get('data', [])
        if pbs:
            print(f'  {ic}: PRODUCT BUNDLE (stock on components)')
        else:
            print(f'  {ic}: NO BIN')
    time.sleep(0.2)
