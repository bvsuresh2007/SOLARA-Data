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

sol = 'SOL1204435'
oid = '7068627271912'
addr_name = 'Nikhil ranjan-Shipping'
order_type = 'Prepaid'
cod_amount = 0
captured = 8648.0
txn_date = '2026-05-06'

# Clean up failed draft SO if any
r_check = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
    params={'filters': json.dumps([['shopify_order_number','=',sol]]),
            'fields': json.dumps(['name','docstatus']),
            'limit_page_length': 5}, timeout=15)
existing = r_check.json().get('data', [])
for e in existing:
    if e.get('docstatus') == 0:
        print(f'Deleting draft SO {e["name"]}...')
        requests.delete(f'{BASE}/api/resource/Sales Order/{e["name"]}', headers=H, timeout=15)
        time.sleep(1)

# Step 1: Create SO via server script - inline items with append
print(f'Step 1: Creating SO...')
sn1 = 'tmp_create_so_435b'
script1 = (
    "so = frappe.new_doc('Sales Order')\n"
    "so.naming_series = 'SHP27-.#####'\n"
    "so.customer = 'Shopify D2C Customer'\n"
    "so.order_type = 'Sales'\n"
    "so.transaction_date = '" + txn_date + "'\n"
    "so.delivery_date = '" + txn_date + "'\n"
    "so.shopify_order_id = '" + oid + "'\n"
    "so.shopify_order_number = '" + sol + "'\n"
    "so.custom_order_type = '" + order_type + "'\n"
    "so.custom_cod_amount = " + str(cod_amount) + "\n"
    "so.custom_prepaid_amount = " + str(captured) + "\n"
    "so.shipping_address_name = '" + addr_name + "'\n"
    "so.customer_address = '" + addr_name + "'\n"
    "so.append('items', {'item_code': 'SOL-AF-501-CVR-BAG', 'qty': 1, 'rate': 499.0, 'warehouse': 'Main Warehouse - WTBBPL'})\n"
    "so.append('items', {'item_code': 'SOL-AF-501-SIL-BASKET-P6-SPY-101', 'qty': 1, 'rate': 8499.0, 'warehouse': 'Main Warehouse - WTBBPL'})\n"
    "so.flags.ignore_validate = True\n"
    "so.flags.ignore_mandatory = True\n"
    "so.insert(ignore_permissions=True)\n"
    "frappe.db.commit()\n"
    "frappe.response['message'] = 'DRAFT|' + so.name\n"
)

r_s1 = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn1, 'script_type': 'API', 'api_method': sn1, 'script': script1, 'allow_guest': 0}, timeout=15)
if r_s1.status_code != 200:
    print(f'Script1 create FAIL: {r_s1.status_code} {r_s1.text[:300]}')
    exit()

time.sleep(1)
r_r1 = requests.get(f'{BASE}/api/method/{sn1}', headers=H, timeout=30)
msg1 = str(r_r1.json().get('message', ''))
print(f'Result: {msg1}')
requests.delete(f'{BASE}/api/resource/Server Script/{sn1}', headers=H, timeout=10)

if not msg1.startswith('DRAFT|'):
    print(f'SO creation failed')
    print(f'Full: {json.dumps(r_r1.json())[:500]}')
    exit()

so_name = msg1.split('|')[1]
print(f'Draft SO: {so_name}')
time.sleep(1)

# Step 2: Set proper fields and submit
print(f'\nStep 2: Submitting SO...')
sn2 = 'tmp_submit_so_435b'
script2 = (
    "so = frappe.get_doc('Sales Order', '" + so_name + "')\n"
    "so.company_address = 'Win The Buy Box Private Limited-Billing'\n"
    "so.gst_category = 'Unregistered'\n"
    "so.taxes_and_charges = 'GST 18% Interstate - WTBBPL'\n"
    "so.run_method('set_missing_values')\n"
    "so.run_method('calculate_taxes_and_totals')\n"
    "so.flags.ignore_validate = True\n"
    "so.save(ignore_permissions=True)\n"
    "so.submit()\n"
    "frappe.db.commit()\n"
    "frappe.response['message'] = 'OK|' + str(so.grand_total)\n"
)

r_s2 = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn2, 'script_type': 'API', 'api_method': sn2, 'script': script2, 'allow_guest': 0}, timeout=15)
if r_s2.status_code != 200:
    print(f'Script2 create FAIL: {r_s2.status_code} {r_s2.text[:300]}')
    exit()

time.sleep(1)
r_r2 = requests.get(f'{BASE}/api/method/{sn2}', headers=H, timeout=30)
msg2 = str(r_r2.json().get('message', ''))
print(f'Result: {msg2}')
requests.delete(f'{BASE}/api/resource/Server Script/{sn2}', headers=H, timeout=10)

if not msg2.startswith('OK'):
    print(f'SO submit failed')
    print(f'Full: {json.dumps(r_r2.json())[:500]}')
    exit()

print(f'SO submitted: {so_name} | {msg2}')
time.sleep(2)

# Step 3: Create DN
print(f'\nStep 3: Creating DN...')
r_make = requests.post(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
                       headers=H, json={'source_name': so_name}, timeout=30)
if r_make.status_code != 200:
    print(f'make_dn FAIL: {r_make.status_code} {r_make.text[:200]}')
    exit()

dn_doc = r_make.json().get('message', {})
r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H,
    params={'fields': json.dumps(['shopify_order_id','shopify_order_number','shipping_address_name','customer_address'])}, timeout=15)
so_d = r_so.json().get('data', {})
dn_doc['shopify_order_id'] = so_d.get('shopify_order_id') or oid
dn_doc['shopify_order_number'] = so_d.get('shopify_order_number') or sol
dn_doc['shipping_address_name'] = so_d.get('shipping_address_name') or addr_name
dn_doc['customer_address'] = so_d.get('customer_address') or addr_name

r_ins = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_doc, timeout=30)
if r_ins.status_code != 200:
    print(f'DN insert FAIL: {r_ins.status_code} {r_ins.text[:200]}')
    exit()

new_dn = r_ins.json().get('data', {}).get('name', '')
print(f'DN created: {new_dn}')

# Step 4: Submit DN
print(f'Submitting {new_dn}...')
r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}',
                     headers=H, json={'docstatus': 1}, timeout=60)
time.sleep(4)

r_v = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
    params={'fields': json.dumps(['docstatus','awb_number','courier_partner','shopify_fulfillment_id'])}, timeout=15)
vd = r_v.json().get('data', {})
ds = vd.get('docstatus', 0)
awb = vd.get('awb_number', '') or ''
cp = vd.get('courier_partner', '') or ''
ful = vd.get('shopify_fulfillment_id', '') or ''

if ds == 1 and awb:
    print(f'\nSUCCESS: {sol} | SO={so_name} | DN={new_dn} | AWB={awb} | {cp} | Fulfillment={ful}')
elif ds == 1:
    print(f'\nSUBMITTED but NO AWB on {new_dn}')
    try:
        r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
            params={'filters': json.dumps([['error','like','%'+new_dn+'%']]),
                    'fields': json.dumps(['error']),
                    'order_by': 'creation desc', 'limit_page_length': 1}, timeout=15)
        errs = r_err.json().get('data', [])
        if errs:
            err = str(errs[0].get('error',''))
            for line in err.split('\n'):
                ll = line.lower()
                if any(k in ll for k in ['clickpost','serviceable','cod','pincode','error','fail','stock','negative']):
                    print(f'ERR: {line.strip()[:200]}')
    except:
        pass
else:
    print(f'\nFAIL ds={ds}')
    try:
        msgs = r_sub.json().get('_server_messages', '')
        if msgs:
            for p in json.loads(msgs):
                inner = json.loads(p) if isinstance(p, str) else p
                print(f'MSG: {inner.get("message", str(inner))[:200]}')
    except:
        print(f'Status: {r_sub.status_code}')
