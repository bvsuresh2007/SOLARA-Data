import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

sols = ['SOL1202824','SOL1202828','SOL1202832','SOL1202834','SOL1202845','SOL1202852',
        'SOL1202858','SOL1202862','SOL1202868','SOL1202886','SOL1202897','SOL1202927',
        'SOL1202946','SOL1202968','SOL1202970','SOL1202977','SOL1202978','SOL1202984',
        'SOL1202999','SOL1203003','SOL1203024','SOL1203039','SOL1203048','SOL1203089',
        'SOL1203090','SOL1203097','SOL1203130','SOL1203135','SOL1203151','SOL1203153',
        'SOL1203161','SOL1203170','SOL1203184','SOL1203210','SOL1203223']

print(f"Checking {len(sols)} orders...\n")

results = []
for sol in sols:
    # Find SO
    r = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
                     params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                             'fields': json.dumps(['name','status','docstatus','customer_name','shipping_address_name']),
                             'limit_page_length': 3}, timeout=15)
    sos = r.json().get('data', [])

    if not sos:
        results.append({'sol': sol, 'so': '', 'so_status': 'NOT_ON_ATLAS', 'customer': '', 'dn': '', 'dn_status': '', 'awb': '', 'items': []})
        continue

    # Pick submitted SO, or first
    so = None
    for s in sos:
        if s['docstatus'] == 1:
            so = s
            break
    if not so:
        so = sos[0]

    so_name = so['name']

    # Get SO items
    r_full = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_data = r_full.json().get('data', {})
    items = so_data.get('items', [])
    item_list = [(it.get('item_code','?'), int(it.get('qty',0)), int(it.get('delivered_qty',0))) for it in items]

    # Find DNs for this SO
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
                        params={'filters': json.dumps([['items.against_sales_order','=',so_name]]),
                                'fields': json.dumps(['name','status','docstatus','posting_date']),
                                'limit_page_length': 5}, timeout=15)
    dns = r_dn.json().get('data', [])

    # Get AWB from active DN
    active_dn = ''
    dn_status = ''
    awb = ''
    for d in dns:
        if d['docstatus'] == 1:
            r_dnd = requests.get(f'{BASE}/api/resource/Delivery Note/{d["name"]}', headers=H,
                                 params={'fields': json.dumps(['awb_number','courier_partner'])}, timeout=15)
            dd = r_dnd.json().get('data', {})
            active_dn = d['name']
            dn_status = d['status']
            awb = dd.get('awb_number', '') or ''
            break
        elif d['docstatus'] == 0:
            active_dn = d['name']
            dn_status = 'Draft'

    results.append({
        'sol': sol,
        'so': so_name,
        'so_status': so['status'],
        'so_ds': so['docstatus'],
        'customer': so.get('customer_name', ''),
        'dn': active_dn,
        'dn_status': dn_status,
        'awb': awb,
        'items': item_list,
        'all_dns': [(d['name'], d['docstatus'], d['status']) for d in dns],
    })
    time.sleep(0.2)

# Classify
ready = []       # Has submitted DN with AWB
draft_dn = []    # Has draft DN, needs submit
no_dn = []       # Has SO, no DN
stuck = []       # Has DN but no AWB or other issue
not_atlas = []   # Not on Atlas
cancelled_so = []

for r in results:
    if r['so_status'] == 'NOT_ON_ATLAS':
        not_atlas.append(r)
    elif r.get('so_ds', 0) != 1:
        cancelled_so.append(r)
    elif r['awb']:
        ready.append(r)
    elif r['dn_status'] == 'Draft':
        draft_dn.append(r)
    elif r['dn'] and not r['awb']:
        stuck.append(r)
    else:
        no_dn.append(r)

print(f"{'='*100}")
print(f"STATUS SUMMARY")
print(f"{'='*100}")
print(f"Already shipped (AWB): {len(ready)}")
print(f"Draft DN (need submit): {len(draft_dn)}")
print(f"No DN (need create+submit): {len(no_dn)}")
print(f"Stuck (DN but no AWB): {len(stuck)}")
print(f"Not on Atlas: {len(not_atlas)}")
print(f"Cancelled SO: {len(cancelled_so)}")

if ready:
    print(f"\n--- ALREADY SHIPPED ---")
    for r in ready:
        skus = ', '.join([f"{ic}" for ic, q, d in r['items']])
        print(f"  {r['sol']} {r['so']} -> {r['dn']} AWB={r['awb']} | {r['customer'][:25]}")

if draft_dn:
    print(f"\n--- DRAFT DN (submit to get AWB) ---")
    for r in draft_dn:
        skus = ', '.join([f"{ic}x{q}" for ic, q, d in r['items']])
        print(f"  {r['sol']} {r['so']} -> {r['dn']} | {r['customer'][:25]} | {skus}")

if no_dn:
    print(f"\n--- NO DN (create from SO + submit) ---")
    for r in no_dn:
        skus = ', '.join([f"{ic}x{q}" for ic, q, d in r['items']])
        print(f"  {r['sol']} {r['so']} | {r['customer'][:25]} | {skus}")

if stuck:
    print(f"\n--- STUCK (DN exists, no AWB) ---")
    for r in stuck:
        skus = ', '.join([f"{ic}x{q}" for ic, q, d in r['items']])
        dns_info = ' '.join([f"{n}(ds={ds})" for n, ds, st in r['all_dns']])
        print(f"  {r['sol']} {r['so']} -> DNs: {dns_info} | {r['customer'][:25]} | {skus}")

if not_atlas:
    print(f"\n--- NOT ON ATLAS ---")
    for r in not_atlas:
        print(f"  {r['sol']}")

if cancelled_so:
    print(f"\n--- CANCELLED SO ---")
    for r in cancelled_so:
        print(f"  {r['sol']} {r['so']} ds={r.get('so_ds',0)}")
