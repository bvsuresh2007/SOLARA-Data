import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

# 22 draft DNs to submit (excluding SOL1203223/SHPDN27-10614 which needs SOL-WB-113 stock)
draft_dns = [
    ('SOL1202828', 'SHPDN27-10845'),
    ('SOL1202832', 'SHPDN27-10784'),
    ('SOL1202834', 'SHPDN27-10786'),
    ('SOL1202845', 'SHPDN27-10793'),
    ('SOL1202858', 'SHPDN27-10803'),
    ('SOL1202862', 'SHPDN27-10807'),
    ('SOL1202868', 'SHPDN27-10810'),
    ('SOL1202886', 'SHPDN27-10822'),
    ('SOL1202927', 'SHPDN27-10730'),
    ('SOL1202970', 'SHPDN27-10762'),
    ('SOL1203003', 'SHPDN27-10674'),
    ('SOL1203039', 'SHPDN27-10694'),
    ('SOL1203048', 'SHPDN27-10700'),
    ('SOL1203089', 'SHPDN27-10629'),
    ('SOL1203130', 'SHPDN27-10655'),
    ('SOL1203135', 'SHPDN27-10660'),
    ('SOL1203151', 'SHPDN27-10569'),
    ('SOL1203153', 'SHPDN27-10570'),
    ('SOL1203161', 'SHPDN27-10577'),
    ('SOL1203170', 'SHPDN27-10582'),
    ('SOL1203184', 'SHPDN27-10589'),
    ('SOL1203210', 'SHPDN27-10606'),
]

results = []
for sol, dn in draft_dns:
    print(f"Submitting {dn} ({sol})...", end=' ')

    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{dn}',
                         headers=H, json={'docstatus': 1}, timeout=60)

    time.sleep(3)

    # Verify
    r_v = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H,
                       params={'fields': json.dumps(['docstatus','awb_number','courier_partner','shopify_fulfillment_id'])}, timeout=15)
    vd = r_v.json().get('data', {})
    awb = vd.get('awb_number') or ''
    cp = vd.get('courier_partner') or ''
    ds = vd.get('docstatus', 0)
    sf = vd.get('shopify_fulfillment_id') or ''

    if ds == 1 and awb:
        print(f"OK AWB={awb} {cp}")
        results.append((sol, dn, 'OK', awb, cp))
    elif ds == 1:
        # Check error log
        print(f"SUBMITTED no AWB")
        results.append((sol, dn, 'NO_AWB', '', ''))
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
        print(f"FAIL ds={ds}: {msg[:100]}")
        results.append((sol, dn, 'FAIL', '', msg[:100]))

    time.sleep(0.5)

print(f"\n\n{'='*90}")
print(f"SUMMARY: {len([r for r in results if r[2]=='OK'])}/{len(results)} OK")
print(f"{'='*90}")
for sol, dn, status, awb, extra in results:
    if status == 'OK':
        print(f"  {sol} {dn} -> AWB={awb} {extra}")
    else:
        print(f"  {sol} {dn} -> {status} {extra}")
