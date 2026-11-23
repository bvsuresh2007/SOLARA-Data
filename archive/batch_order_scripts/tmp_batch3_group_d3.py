import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

sol = 'SOL1204435'
oid = '7068627271912'
addr_name = 'Nikhil ranjan-Shipping'

# Clean up failed draft SO
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

def run_server_script(name, script, wait=2):
    """Create temp server script, run it, delete it."""
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': name, 'script_type': 'API', 'api_method': name, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code != 200:
        print(f'  Script create FAIL: {r.status_code} {r.text[:300]}')
        return None
    time.sleep(wait)
    r2 = requests.get(f'{BASE}/api/method/{name}', headers=H, timeout=30)
    result = r2.json()
    msg = str(result.get('message', ''))
    exc = result.get('exception', '')
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=10)
    if exc:
        print(f'  Script exec error: {exc[:300]}')
        return None
    return msg

# Step 1: Create draft SO
print(f'Step 1: Creating draft SO...')
script1 = (
    "so = frappe.new_doc('Sales Order')\n"
    "so.naming_series = 'SHP27-.#####'\n"
    "so.customer = 'Shopify D2C Customer'\n"
    "so.order_type = 'Sales'\n"
    "so.transaction_date = '2026-05-06'\n"
    "so.delivery_date = '2026-05-06'\n"
    "so.shopify_order_id = '" + oid + "'\n"
    "so.shopify_order_number = '" + sol + "'\n"
    "so.custom_order_type = 'Prepaid'\n"
    "so.custom_cod_amount = 0\n"
    "so.custom_prepaid_amount = 8648.0\n"
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

msg1 = run_server_script('tmp_cso435c', script1, wait=3)
print(f'  Result: {msg1}')

if not msg1 or not msg1.startswith('DRAFT|'):
    print('Failed to create SO')
    exit()

so_name = msg1.split('|')[1]
print(f'  Draft SO: {so_name}')
time.sleep(1)

# Step 2: Submit SO
print(f'\nStep 2: Submitting SO {so_name}...')
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

msg2 = run_server_script('tmp_sso435c', script2, wait=3)
print(f'  Result: {msg2}')

if not msg2 or not msg2.startswith('OK'):
    print('Failed to submit SO')
    exit()

print(f'  SO submitted: {so_name}')
time.sleep(2)

# Step 3: Create DN
print(f'\nStep 3: Creating DN from SO {so_name}...')
r_make = requests.post(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
                       headers=H, json={'source_name': so_name}, timeout=30)
if r_make.status_code != 200:
    print(f'  make_dn FAIL: {r_make.status_code} {r_make.text[:200]}')
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
    print(f'  DN insert FAIL: {r_ins.status_code} {r_ins.text[:200]}')
    exit()

new_dn = r_ins.json().get('data', {}).get('name', '')
print(f'  DN created: {new_dn}')

# Step 4: Submit DN
print(f'  Submitting {new_dn}...')
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
                    print(f'  ERR: {line.strip()[:200]}')
    except:
        pass
else:
    print(f'\nFAIL ds={ds}')
    try:
        msgs = r_sub.json().get('_server_messages', '')
        if msgs:
            for p in json.loads(msgs):
                inner = json.loads(p) if isinstance(p, str) else p
                print(f'  MSG: {inner.get("message", str(inner))[:200]}')
    except:
        print(f'  Status: {r_sub.status_code}')
