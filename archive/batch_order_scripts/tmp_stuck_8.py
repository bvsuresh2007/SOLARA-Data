import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

stuck = [
    ('SOL1202824', 'SHP27-09121', 'SHPDN27-10780'),
    ('SOL1202852', 'SHP27-09148', 'SHPDN27-10799'),
    ('SOL1202897', 'SHP27-09193', 'SHPDN27-10831'),
    ('SOL1202968', 'SHP27-09263', 'SHPDN27-10861'),
    ('SOL1202978', 'SHP27-09273', 'SHPDN27-10765'),
    ('SOL1202984', 'SHP27-09279', 'SHPDN27-10865'),
    ('SOL1202999', 'SHP27-09294', 'SHPDN27-10671'),
    ('SOL1203024', 'SHP27-09319', 'SHPDN27-10871'),
]

for sol, so, dn in stuck:
    print(f"\n=== {sol} | SO={so} | DN={dn} ===")

    # DN details
    r = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=30)
    d = r.json().get('data', {})
    print(f"  docstatus={d.get('docstatus')} status={d.get('status')} awb={d.get('awb_number','')}")
    print(f"  customer={d.get('customer_name','')}")
    print(f"  shipping_address={d.get('shipping_address_name','')}")
    print(f"  shopify_order_id={d.get('shopify_order_id','')}")
    print(f"  shopify_order_number={d.get('shopify_order_number','')}")
    print(f"  is_replacement={d.get('is_replacement',0)}")

    items = d.get('items', [])
    for it in items:
        print(f"  item: {it.get('item_code','?')} qty={it.get('qty',0)}")

    # Check if address has pincode
    addr = d.get('shipping_address_name', '')
    if addr:
        r_a = requests.get(f'{BASE}/api/resource/Address/{addr}', headers=H,
            params={'fields': json.dumps(['pincode','phone','city','state'])}, timeout=30)
        ad = r_a.json().get('data', {})
        print(f"  address: pin={ad.get('pincode','')} city={ad.get('city','')} state={ad.get('state','')} phone={ad.get('phone','')}")

    # Check error logs for this DN
    r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
        params={'filters': json.dumps([['error','like',f'%{dn}%']]),
                'fields': json.dumps(['name','error','creation']),
                'order_by': 'creation desc', 'limit_page_length': 2}, timeout=30)
    errs = r_err.json().get('data', [])
    if errs:
        for e in errs:
            err_text = str(e.get('error', ''))
            # Find clickpost or relevant error
            if 'clickpost' in err_text.lower() or 'awb' in err_text.lower() or 'pincode' in err_text.lower() or 'phone' in err_text.lower():
                print(f"  ERROR LOG: {err_text[:200]}")
            else:
                print(f"  ERROR LOG: {err_text[:150]}")
    else:
        print(f"  No error logs found for this DN")

    time.sleep(0.3)
