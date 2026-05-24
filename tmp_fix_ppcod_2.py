import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

ppcod_fixes = [
    {
        'sol': 'SOL1202828',
        'so': 'SHP27-09124',
        'dn': 'SHPDN27-10845',
        'old_awb': '29044411190512',
        'old_cp': 'Delhivery',
        'grand_total': 2999.0,
        'prepaid_captured': 299.9,
        'cod_amount': 2699.1,
    },
    {
        'sol': 'SOL1202968',
        'so': 'SHP27-09263',
        'dn': 'SHPDN27-10861',
        'old_awb': '50938446996',
        'old_cp': 'Bluedart',
        'grand_total': 1399.0,
        'prepaid_captured': 139.9,
        'cod_amount': 1259.1,
    },
]

for order in ppcod_fixes:
    sol = order['sol']
    so = order['so']
    dn = order['dn']
    cod_amt = order['cod_amount']
    prepaid = order['prepaid_captured']

    print(f"\n{'='*70}")
    print(f"=== {sol} | SO={so} | DN={dn} ===")
    print(f"  COD amount: Rs {cod_amt} | Prepaid: Rs {prepaid}")

    # Step 1: Fix custom_cod_amount on SO
    print(f"\n  Step 1: Fixing SO custom_cod_amount...")
    sn = 'tmp_fix_cod_' + so.replace('-', '_').lower()
    script = (
        "frappe.db.set_value('Sales Order','" + so + "','custom_cod_amount'," + str(cod_amt) + ",update_modified=False)\n"
        "frappe.db.set_value('Sales Order','" + so + "','custom_prepaid_amount'," + str(prepaid) + ",update_modified=False)\n"
        "frappe.db.commit()\n"
        "v = frappe.db.get_value('Sales Order','" + so + "',['custom_cod_amount','custom_prepaid_amount'],as_dict=True)\n"
        "frappe.response['message']='cod=' + str(v.custom_cod_amount) + ' prepaid=' + str(v.custom_prepaid_amount)\n"
    )
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code == 200:
        time.sleep(1)
        r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=15)
        print(f"    {r2.json().get('message', '')}")
        requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
    else:
        print(f"    FAIL: {r.status_code}")
        continue

    # Step 2: Cancel old DN
    print(f"\n  Step 2: Cancelling DN {dn}...")
    r_cancel = requests.post(f'{BASE}/api/method/frappe.client.cancel',
                             headers=H, json={'doctype': 'Delivery Note', 'name': dn}, timeout=30)
    time.sleep(2)
    r_chk = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H,
                         params={'fields': json.dumps(['docstatus'])}, timeout=15)
    ds = r_chk.json().get('data', {}).get('docstatus', 0)
    if ds == 2:
        print(f"    {dn} CANCELLED")
    else:
        print(f"    Cancel status ds={ds}")

    # Step 3: Create new DN from SO
    print(f"\n  Step 3: Creating new DN...")
    r_make = requests.post(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
                           headers=H, json={'source_name': so}, timeout=30)
    if r_make.status_code != 200:
        print(f"    make_delivery_note FAIL: {r_make.status_code}")
        continue

    new_dn_doc = r_make.json().get('message', {})

    # Copy shopify fields
    r_so_full = requests.get(f'{BASE}/api/resource/Sales Order/{so}', headers=H,
        params={'fields': json.dumps(['shopify_order_id','shopify_order_number','shipping_address_name','customer_address'])}, timeout=15)
    so_d = r_so_full.json().get('data', {})
    new_dn_doc['shopify_order_id'] = so_d.get('shopify_order_id') or ''
    new_dn_doc['shopify_order_number'] = so_d.get('shopify_order_number') or sol
    new_dn_doc['shipping_address_name'] = so_d.get('shipping_address_name') or new_dn_doc.get('shipping_address_name', '')
    new_dn_doc['customer_address'] = so_d.get('customer_address') or new_dn_doc.get('customer_address', '')

    r_ins = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=new_dn_doc, timeout=30)
    if r_ins.status_code != 200:
        print(f"    DN insert FAIL: {r_ins.status_code} {r_ins.text[:200]}")
        continue

    new_dn = r_ins.json().get('data', {}).get('name', '')
    print(f"    New DN: {new_dn}")

    # Step 4: Submit new DN (triggers Clickpost with correct COD amount)
    print(f"\n  Step 4: Submitting {new_dn}...")
    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}',
                         headers=H, json={'docstatus': 1}, timeout=60)
    time.sleep(4)

    r_v = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
                       params={'fields': json.dumps(['docstatus','awb_number','courier_partner','grand_total'])}, timeout=15)
    vd = r_v.json().get('data', {})
    awb = vd.get('awb_number') or ''
    cp = vd.get('courier_partner') or ''
    ds = vd.get('docstatus', 0)

    if ds == 1 and awb:
        print(f"    OK: AWB={awb} {cp}")
    elif ds == 1:
        print(f"    SUBMITTED no AWB — check error log")
        # Check error
        time.sleep(1)
        r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
            params={'filters': json.dumps([['error','like',f'%{new_dn}%']]),
                    'fields': json.dumps(['error']),
                    'order_by': 'creation desc', 'limit_page_length': 1}, timeout=15)
        errs = r_err.json().get('data', [])
        if errs:
            err = str(errs[0].get('error',''))
            for line in err.split('\n'):
                if any(k in line.lower() for k in ['clickpost','serviceable','cod','order_type']):
                    print(f"    ERR: {line.strip()[:150]}")
                    break
    else:
        msg = ''
        try:
            msgs = r_sub.json().get('_server_messages', '')
            if msgs:
                for p in json.loads(msgs):
                    inner = json.loads(p) if isinstance(p, str) else p
                    m = inner.get('message', str(inner))
                    if 'Item Price' not in m:
                        msg = m[:120]
                        break
        except:
            msg = str(r_sub.status_code)
        print(f"    FAIL ds={ds}: {msg[:100]}")

    time.sleep(1)
