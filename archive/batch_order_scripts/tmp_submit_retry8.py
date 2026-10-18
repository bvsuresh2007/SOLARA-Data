import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

retry_dns = [
    ('SOL1202828', 'SHPDN27-10845'),
    ('SOL1202845', 'SHPDN27-10793'),
    ('SOL1202858', 'SHPDN27-10803'),
    ('SOL1202868', 'SHPDN27-10810'),
    ('SOL1203048', 'SHPDN27-10700'),
    ('SOL1203089', 'SHPDN27-10629'),
    ('SOL1203130', 'SHPDN27-10655'),
    ('SOL1203135', 'SHPDN27-10660'),
]

results = []
for sol, dn in retry_dns:
    print(f"Submitting {dn} ({sol})...", end=' ', flush=True)
    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{dn}',
                         headers=H, json={'docstatus': 1}, timeout=60)
    time.sleep(3)

    r_v = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H,
                       params={'fields': json.dumps(['docstatus','awb_number','courier_partner'])}, timeout=15)
    vd = r_v.json().get('data', {})
    awb = vd.get('awb_number') or ''
    cp = vd.get('courier_partner') or ''
    ds = vd.get('docstatus', 0)

    if ds == 1 and awb:
        print(f"OK AWB={awb} {cp}")
        results.append((sol, dn, 'OK', awb, cp))
    elif ds == 1:
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
                        msg = m[:120]
                        break
        except:
            msg = str(r_sub.status_code)
        print(f"FAIL: {msg[:100]}")
        results.append((sol, dn, 'FAIL', '', msg[:100]))
    time.sleep(0.5)

ok = [r for r in results if r[2] == 'OK']
print(f"\n{'='*90}")
print(f"SUMMARY: {len(ok)}/{len(results)} OK")
print(f"{'='*90}")
for sol, dn, status, awb, extra in results:
    if status == 'OK':
        print(f"  {sol} {dn} AWB={awb} {extra}")
    else:
        print(f"  {sol} {dn} {status} {extra}")
