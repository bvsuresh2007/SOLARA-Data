import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

orders = [
    ('SOL1204715', 'SOL-AF-MITTEN'),
    ('SOL1204710', 'SOL-INS-WB-CP-CHUG-101'),
    ('SOL1204617', 'SOL-AF-501-CVR-BAG'),
    ('SOL1204551', 'SOL-AF-501-SIL-BASKET-P6-SPY-101'),
    ('SOL1204541', 'SOL-CI-KD-103-DT-103-FP-102'),
    ('SOL1204541', 'SOL-CKW-WSPA-101'),
    ('SOL1204467', 'SOL-AF-501-SIL-BASKET-P6-SPY-101'),
    ('SOL1204435', 'SOL-AF-501-CVR-BAG'),
    ('SOL1204435', 'SOL-AF-501-SIL-BASKET-P6-SPY-101'),
    ('SOL1204432', 'SOL-AF-501'),
    ('SOL1204408', 'SOL-AF-501-SIL-BASKET-P6-SPY-101'),
    ('SOL1204568', 'SOL-AF-501'),
]

# Unique order numbers
unique_sols = list(dict.fromkeys([o[0] for o in orders]))

print(f'{"SOL":<14} {"SO":<16} {"DS":<4} {"Customer":<25} {"Type":<8} {"COD":<10} {"Total":<10} {"DN":<18} {"DN_DS":<6} {"AWB":<20} {"Courier":<12} {"Items"}')
print("=" * 180)

for sol in unique_sols:
    # Get SO
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','customer_name','custom_order_type','custom_cod_amount','grand_total','shopify_order_id','shipping_address_name']),
                'limit_page_length': 5}, timeout=15)
    sos = r_so.json().get('data', [])
    
    if not sos:
        print(f'{sol:<14} {"NOT FOUND":<16}')
        continue
    
    for so in sos:
        so_name = so['name']
        ds = so.get('docstatus', 0)
        cust = so.get('customer_name', '')[:24]
        otype = so.get('custom_order_type', '') or ''
        cod = float(so.get('custom_cod_amount', 0) or 0)
        total = float(so.get('grand_total', 0) or 0)
        
        # Get items
        r_items = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H,
            params={'fields': json.dumps(['name'])}, timeout=15)
        so_full = r_items.json().get('data', {})
        items_list = so_full.get('items', [])
        items_str = ', '.join([f'{it.get("item_code","")} x{int(it.get("qty",0))}' for it in items_list])
        
        # Get DNs
        r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
            params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                    'fields': json.dumps(['name','docstatus','awb_number','courier_partner','shopify_fulfillment_id']),
                    'limit_page_length': 5}, timeout=15)
        dns = r_dn.json().get('data', [])
        
        if dns:
            for d in dns:
                dn_name = d['name']
                dn_ds = d.get('docstatus', 0)
                awb = d.get('awb_number', '') or ''
                courier = d.get('courier_partner', '') or ''
                ful = d.get('shopify_fulfillment_id', '') or ''
                print(f'{sol:<14} {so_name:<16} {ds:<4} {cust:<25} {otype:<8} {cod:<10.1f} {total:<10.1f} {dn_name:<18} {dn_ds:<6} {awb:<20} {courier:<12} {items_str}')
        else:
            print(f'{sol:<14} {so_name:<16} {ds:<4} {cust:<25} {otype:<8} {cod:<10.1f} {total:<10.1f} {"NO DN":<18} {"":<6} {"":<20} {"":<12} {items_str}')
    
    time.sleep(0.3)

