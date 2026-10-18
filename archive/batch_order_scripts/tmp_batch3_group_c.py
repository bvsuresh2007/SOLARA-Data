import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

# Group C: SOL1204467 - nishanth Phonepe, PIN mismatch Atlas=560078 vs Shopify=560073
# Draft DN SHPDN27-12154 exists. Fix PIN on Address, then submit draft DN.

sol = 'SOL1204467'
so_name = 'SHP27-10767'
dn = 'SHPDN27-12154'
addr_name = 'nishanth Phonepe-SOL1204467-Shipping'
correct_pin = '560073'

print(f'=== {sol} | DN={dn} ===')

# Step 1: Fix PIN on Address
print(f'  Step 1: Fixing PIN {addr_name} -> {correct_pin}')
sn = 'tmp_fix_pin_467'
script = (
    "frappe.db.set_value('Address','" + addr_name + "','pincode','" + correct_pin + "',update_modified=False)\n"
    "frappe.db.commit()\n"
    "v = frappe.db.get_value('Address','" + addr_name + "','pincode')\n"
    "frappe.response['message'] = str(v)\n"
)
r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
if r.status_code == 200:
    time.sleep(1)
    r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=15)
    msg = r2.json().get('message', '')
    print(f'  PIN updated: {msg}')
    requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
else:
    print(f'  Script create FAIL {r.status_code} {r.text[:200]}')

time.sleep(1)

# Step 2: Check draft DN has shopify fields
r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H,
    params={'fields': json.dumps(['docstatus','shopify_order_id','shopify_order_number','shipping_address_name'])}, timeout=15)
dn_d = r_dn.json().get('data', {})
print(f'  DN check: ds={dn_d.get("docstatus",0)} | OID={dn_d.get("shopify_order_id","")} | SON={dn_d.get("shopify_order_number","")} | Ship={dn_d.get("shipping_address_name","")}')

dn_oid = dn_d.get('shopify_order_id', '') or ''
dn_son = dn_d.get('shopify_order_number', '') or ''
dn_ship = dn_d.get('shipping_address_name', '') or ''

# If missing shopify fields, delete and recreate
if not dn_oid or not dn_son:
    print(f'  Missing Shopify fields on draft DN, deleting and recreating...')
    requests.delete(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=15)
    time.sleep(1)

    print(f'  Creating DN from SO {so_name}...')
    r_make = requests.post(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
                           headers=H, json={'source_name': so_name}, timeout=30)
    if r_make.status_code != 200:
        print(f'  make_dn FAIL: {r_make.status_code} {r_make.text[:200]}')
        exit()

    dn_doc = r_make.json().get('message', {})

    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H,
        params={'fields': json.dumps(['shopify_order_id','shopify_order_number','shipping_address_name','customer_address'])}, timeout=15)
    so_d = r_so.json().get('data', {})
    dn_doc['shopify_order_id'] = so_d.get('shopify_order_id') or ''
    dn_doc['shopify_order_number'] = so_d.get('shopify_order_number') or sol
    dn_doc['shipping_address_name'] = so_d.get('shipping_address_name') or dn_doc.get('shipping_address_name', '')
    dn_doc['customer_address'] = so_d.get('customer_address') or dn_doc.get('customer_address', '')

    r_ins = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_doc, timeout=30)
    if r_ins.status_code != 200:
        print(f'  DN insert FAIL: {r_ins.status_code} {r_ins.text[:200]}')
        exit()

    dn = r_ins.json().get('data', {}).get('name', '')
    print(f'  DN created: {dn}')
else:
    print(f'  Shopify fields OK, submitting existing draft')

# Step 3: Submit DN
print(f'  Submitting {dn}...')
r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{dn}',
                     headers=H, json={'docstatus': 1}, timeout=60)
time.sleep(4)

# Step 4: Check result
r_v = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H,
    params={'fields': json.dumps(['docstatus','awb_number','courier_partner','shopify_fulfillment_id'])}, timeout=15)
vd = r_v.json().get('data', {})
ds = vd.get('docstatus', 0)
awb = vd.get('awb_number', '') or ''
cp = vd.get('courier_partner', '') or ''
ful = vd.get('shopify_fulfillment_id', '') or ''

if ds == 1 and awb:
    print(f'  OK: AWB={awb} | {cp} | Fulfillment={ful}')
elif ds == 1:
    print(f'  SUBMITTED but NO AWB — checking errors...')
    try:
        r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
            params={'filters': json.dumps([['error','like','%'+dn+'%']]),
                    'fields': json.dumps(['error']),
                    'order_by': 'creation desc', 'limit_page_length': 1}, timeout=15)
        errs = r_err.json().get('data', [])
        if errs:
            err = str(errs[0].get('error',''))
            for line in err.split('\n'):
                ll = line.lower()
                if any(k in ll for k in ['clickpost','serviceable','cod','pincode','error','fail','stock','negative','mismatch','address','phone']):
                    print(f'  ERR: {line.strip()[:200]}')
    except:
        pass
else:
    msg = ''
    try:
        msgs = r_sub.json().get('_server_messages', '')
        if msgs:
            for p in json.loads(msgs):
                inner = json.loads(p) if isinstance(p, str) else p
                m = inner.get('message', str(inner))
                if 'Item Price' not in m:
                    msg = m[:150]
                    break
    except:
        msg = str(r_sub.status_code)
    print(f'  FAIL ds={ds}: {msg}')
