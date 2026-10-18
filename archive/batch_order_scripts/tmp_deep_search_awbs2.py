import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

orders = [
    ('SOL1197271', 'SHP27-03434', 'Inzamam Ul Islam'),
    ('SOL1201623', 'SHP27-07830', 'Monica Chahal'),
    ('SOL1198284', 'SHP27-04454', 'Teresa Moktan'),
    ('REP-2627-SHP-00271', 'REP-2627-SHP-00271', 'Mohammed Arshad'),
    ('SOL1196443', 'SHP27-02603', 'Bhawna Panjwani'),
    ('REP-2627-OTH-00033', 'REP-2627-OTH-00033', 'Srinivasulu Bhuvanagiri'),
    ('SOL1201901', 'SHP27-08125', 'Suhas Kulkarni'),
    ('REP-2627-SHP-00202', 'REP-2627-SHP-00202', 'Gopi .'),
]

for sol, so_name, cust in orders:
    print(f'\n{"="*80}')
    print(f'=== {sol} | {cust} ===')

    all_dns = []

    # Method 1: shopify_order_number = sol
    r1 = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','awb_number','courier_partner','shopify_fulfillment_id','amended_from','creation']),
                'limit_page_length': 10}, timeout=15)
    for d in r1.json().get('data', []):
        if d['name'] not in [x['name'] for x in all_dns]:
            all_dns.append(d)

    # Method 2: shopify_order_number = so_name (for REP)
    if sol != so_name:
        r2 = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
            params={'filters': json.dumps([['shopify_order_number','=',so_name]]),
                    'fields': json.dumps(['name','docstatus','awb_number','courier_partner','shopify_fulfillment_id','amended_from','creation']),
                    'limit_page_length': 10}, timeout=15)
        for d in r2.json().get('data', []):
            if d['name'] not in [x['name'] for x in all_dns]:
                all_dns.append(d)

    # Method 3: customer_name search (broad)
    r3 = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['customer_name','=',cust]]),
                'fields': json.dumps(['name','docstatus','awb_number','courier_partner','shopify_fulfillment_id','amended_from','creation','shopify_order_number']),
                'order_by': 'creation desc',
                'limit_page_length': 15}, timeout=15)
    for d in r3.json().get('data', []):
        if d['name'] not in [x['name'] for x in all_dns]:
            all_dns.append(d)

    # Method 4: search by SO amended variants
    r4 = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['name','like',so_name+'%']]),
                'fields': json.dumps(['name','docstatus','amended_from']),
                'limit_page_length': 10}, timeout=15)
    amended_sos = r4.json().get('data', [])
    if amended_sos:
        for aso in amended_sos:
            if aso['name'] != so_name:
                print(f'  Amended SO: {aso["name"]} | ds={aso.get("docstatus",0)} | amended_from={aso.get("amended_from","")}')

    if all_dns:
        for d in sorted(all_dns, key=lambda x: x.get('creation', '')):
            awb = d.get('awb_number', '') or ''
            cp = d.get('courier_partner', '') or ''
            ds = d.get('docstatus', 0)
            ds_label = {0: 'Draft', 1: 'Submitted', 2: 'Cancelled'}
            ful = d.get('shopify_fulfillment_id', '') or ''
            amended = d.get('amended_from', '') or ''
            son = d.get('shopify_order_number', '') or ''
            print(f'  DN: {d["name"]} | {ds_label.get(ds,ds)} | AWB={awb} | {cp} | SON={son} | ful={ful} | amended={amended}')
    else:
        print(f'  NO DNs FOUND (all methods)')

    time.sleep(0.3)
