import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

stuck = [
    ('SOL1202852', 'SHP27-09148', 'SHPDN27-10799'),
    ('SOL1202897', 'SHP27-09193', 'SHPDN27-10831'),
    ('SOL1202968', 'SHP27-09263', 'SHPDN27-10861'),
    ('SOL1202978', 'SHP27-09273', 'SHPDN27-10765'),
    ('SOL1202984', 'SHP27-09279', 'SHPDN27-10865'),
    ('SOL1202999', 'SHP27-09294', 'SHPDN27-10671'),
    ('SOL1203024', 'SHP27-09319', 'SHPDN27-10871'),
]

# Already got SOL1202824: PIN 201308, "201308 is not serviceable"

for sol, so, dn in stuck:
    print(f"\n=== {sol} | DN={dn} ===")
    try:
        r = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=45)
        d = r.json().get('data', {})
        print(f"  customer={d.get('customer_name','')} | ds={d.get('docstatus')} | awb={d.get('awb_number','')}")

        items = [it.get('item_code','?') for it in d.get('items', [])]
        print(f"  items: {', '.join(items)}")

        addr = d.get('shipping_address_name', '')
        if addr:
            try:
                r_a = requests.get(f'{BASE}/api/resource/Address/{addr}', headers=H,
                    params={'fields': json.dumps(['pincode','city','state','phone'])}, timeout=30)
                ad = r_a.json().get('data', {})
                print(f"  pin={ad.get('pincode','')} city={ad.get('city','')} state={ad.get('state','')} phone={ad.get('phone','')}")
            except:
                print(f"  address timeout")
    except Exception as e:
        print(f"  DN fetch error: {str(e)[:80]}")

    # Error log
    try:
        r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
            params={'filters': json.dumps([['error','like',f'%{dn}%']]),
                    'fields': json.dumps(['error','creation']),
                    'order_by': 'creation desc', 'limit_page_length': 1}, timeout=30)
        errs = r_err.json().get('data', [])
        if errs:
            err = str(errs[0].get('error', ''))
            # Extract clickpost error
            for line in err.split('\n'):
                if 'clickpost' in line.lower() or 'serviceable' in line.lower() or 'phone' in line.lower() or 'pincode' in line.lower() or 'Error' in line:
                    print(f"  ERR: {line.strip()[:150]}")
                    break
            else:
                print(f"  ERR: {err[:150]}")
        else:
            print(f"  No error logs")
    except:
        print(f"  Error log timeout")

    time.sleep(1)
