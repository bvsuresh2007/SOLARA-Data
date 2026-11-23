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

# Try Clickpost polling API (different from tracking)
print("Trying Clickpost polling API...")
for sol, cust, awb in awbs:
    try:
        r = requests.post('https://www.clickpost.in/api/v1/pull-status/',
            params={'username': 'solara', 'key': CP_KEY},
            json={'waybill': awb, 'cp_id': 4},
            headers={'Content-Type': 'application/json'}, timeout=15)
        ct = r.headers.get('content-type', '')
        if 'json' in ct:
            data = r.json()
            meta = data.get('meta', {})
            if meta.get('success'):
                result = data.get('result', {})
                status = result.get('latest_status', {})
                remark = status.get('remark', '')
                status_code = status.get('clickpost_status_code', '')
                status_desc = status.get('clickpost_status_description', '')
                timestamp = status.get('timestamp', '')
                location = status.get('location', '')
                rto = result.get('rto_initiated', False)
                print(f'{sol:<24} {cust:<22} {awb} | {status_desc} | {remark[:50]} | {timestamp[:16]} | {location} | RTO={rto}')
            else:
                print(f'{sol:<24} {cust:<22} {awb} | FAIL: {meta.get("message","")[:60]}')
        else:
            print(f'{sol:<24} {cust:<22} {awb} | non-JSON response')
    except Exception as e:
        print(f'{sol:<24} {cust:<22} {awb} | ERR: {e}')
    time.sleep(0.5)

# Also try Clickpost v2 tracking
print(f'\n\nTrying Clickpost v2 tracking...')
for sol, cust, awb in awbs:
    try:
        r = requests.get(f'https://www.clickpost.in/api/v2/track-order/',
            params={'username': 'solara', 'key': CP_KEY, 'waybill': awb, 'cp_id': 4},
            timeout=15)
        ct = r.headers.get('content-type', '')
        if 'json' in ct:
            data = r.json()
            meta = data.get('meta', {})
            if meta.get('success'):
                result = data.get('result', {})
                latest = result.get('latest_status', {})
                desc = latest.get('clickpost_status_description', '')
                remark = latest.get('remark', '')
                ts = latest.get('timestamp', '')
                loc = latest.get('location', '')
                rto = result.get('rto_initiated', False)
                print(f'{sol:<24} {cust:<22} {awb} | {desc} | {remark[:50]} | {ts[:16]} | RTO={rto}')
            else:
                print(f'{sol:<24} {cust:<22} {awb} | FAIL: {meta.get("message","")[:60]}')
        else:
            # Show first 200 chars
            print(f'{sol:<24} {cust:<22} {awb} | non-JSON: {r.text[:100]}')
    except Exception as e:
        print(f'{sol:<24} {cust:<22} {awb} | ERR: {e}')
    time.sleep(0.5)
