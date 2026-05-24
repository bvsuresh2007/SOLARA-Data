import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

addr_name = 'Rose Dee-SOL1202834-Shipping'
dn = 'SHPDN27-10786'

# Step 1: Fix Atlas Address to match Shopify
sn = 'tmp_fix_addr_1202834'
script = """
addr = 'Rose Dee-SOL1202834-Shipping'
frappe.db.set_value('Address', addr, 'address_line1', '57 Friends Colony, opposite Shiv Crockery and Plastics, Katol Road, Nagpur', update_modified=False)
frappe.db.set_value('Address', addr, 'address_line2', '', update_modified=False)
frappe.db.set_value('Address', addr, 'city', 'NAGPUR', update_modified=False)
frappe.db.set_value('Address', addr, 'state', 'Maharashtra', update_modified=False)
frappe.db.set_value('Address', addr, 'pincode', '440013', update_modified=False)
frappe.db.commit()

chk = frappe.db.get_value('Address', addr, ['address_line1', 'pincode', 'city'], as_dict=True)
frappe.response["message"] = "OK pin=" + str(chk.pincode) + " city=" + str(chk.city) + " addr=" + str(chk.address_line1)[:60]
"""

print("=== Step 1: Fixing Atlas Address ===")
r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
if r.status_code == 200:
    time.sleep(1)
    r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=15)
    print(f"  {r2.json().get('message', '')}")
    requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
else:
    print(f"  FAIL: {r.status_code} {r.text[:200]}")

# Step 2: Submit DN
print(f"\n=== Step 2: Submitting {dn} ===")
time.sleep(1)
r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{dn}',
                     headers=H, json={'docstatus': 1}, timeout=60)
time.sleep(4)

r_v = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H,
                   params={'fields': json.dumps(['docstatus','awb_number','courier_partner'])}, timeout=15)
vd = r_v.json().get('data', {})
awb = vd.get('awb_number') or ''
cp = vd.get('courier_partner') or ''
ds = vd.get('docstatus', 0)

if ds == 1 and awb:
    print(f"  OK: AWB={awb} {cp}")
elif ds == 1:
    print(f"  SUBMITTED no AWB")
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
    print(f"  FAIL ds={ds}: {msg[:120]}")
