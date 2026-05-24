import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

awbs = [
    ('REP-2627-SHP-00202', 'Gopi .', '29044411144345'),
    ('SOL1201901', 'Suhas Kulkarni', '29044411170901'),
    ('SOL1196443', 'Bhawna Panjwani', '29044411169442'),
    ('REP-2627-SHP-00271', 'Mohammed Arshad', '29044411144360'),
    ('SOL1198284', 'Teresa Moktan', '29044411127825'),
    ('SOL1201623', 'Monica Chahal', '29044411158636'),
]

print(f'{"Order":<24} {"Customer":<22} {"AWB":<20} {"CP Status":<18} {"Latest Scan":<40} {"RTO?":<6}')
print("=" * 140)

for sol, cust, awb in awbs:
    cp_status = ''
    latest = ''
    rto = ''

    try:
        r = requests.get(f'https://www.clickpost.in/api/v1/tracking/',
            params={'username': 'solara', 'key': CP_KEY, 'waybill': awb}, timeout=15)

        # Check if response is JSON
        ct = r.headers.get('content-type', '')
        if 'json' in ct:
            data = r.json()
            if data.get('meta', {}).get('success'):
                result = data.get('result', {})
                cp_status = result.get('latest_status', '')
                rto = 'YES' if result.get('rto_initiated', False) else 'No'

                scans = result.get('scans', [])
                if scans:
                    last_scan = scans[-1]
                    latest = f'{last_scan.get("status","")} | {last_scan.get("timestamp","")[:16]} | {last_scan.get("location","")}'
            else:
                cp_status = data.get('meta', {}).get('message', 'FAIL')[:40]
        else:
            # v1 returning HTML, try v3
            cp_status = 'v1=HTML'
    except Exception as e:
        cp_status = f'ERR: {str(e)[:30]}'

    # If v1 failed, try Clickpost v3 track
    if cp_status == 'v1=HTML':
        try:
            r2 = requests.post('https://www.clickpost.in/api/v3/track-order/',
                params={'username': 'solara', 'key': CP_KEY},
                json={'waybill': awb}, headers={'Content-Type': 'application/json'}, timeout=15)
            ct2 = r2.headers.get('content-type', '')
            if 'json' in ct2:
                data2 = r2.json()
                if data2.get('meta', {}).get('success'):
                    result2 = data2.get('result', {})
                    cp_status = result2.get('latest_status', '')
                    rto = 'YES' if result2.get('rto_initiated', False) else 'No'
                    scans2 = result2.get('scans', [])
                    if scans2:
                        last_scan2 = scans2[-1]
                        latest = f'{last_scan2.get("status","")} | {last_scan2.get("timestamp","")[:16]} | {last_scan2.get("location","")}'
                else:
                    cp_status = 'v3: ' + str(data2.get('meta', {}).get('message', ''))[:30]
            else:
                cp_status = 'v3=non-JSON'
        except Exception as e2:
            cp_status = f'v3 ERR: {str(e2)[:30]}'

    # If both failed, try Clickpost status API
    if 'HTML' in cp_status or 'ERR' in cp_status or 'non-JSON' in cp_status:
        try:
            r3 = requests.get(f'https://www.clickpost.in/api/v1/order-status/',
                params={'username': 'solara', 'key': CP_KEY, 'waybill': awb}, timeout=15)
            ct3 = r3.headers.get('content-type', '')
            if 'json' in ct3:
                data3 = r3.json()
                cp_status = str(data3)[:60]
            else:
                cp_status = 'All APIs failed (HTML)'
        except:
            pass

    print(f'{sol:<24} {cust:<22} {awb:<20} {cp_status:<18} {latest:<40} {rto:<6}')
    time.sleep(0.5)
