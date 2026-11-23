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

# Print full v2 response for first AWB to understand structure
print("=== Full v2 response for first AWB ===")
awb = awbs[0][2]
r = requests.get(f'https://www.clickpost.in/api/v2/track-order/',
    params={'username': 'solara', 'key': CP_KEY, 'waybill': awb, 'cp_id': 4},
    timeout=15)
print(json.dumps(r.json(), indent=2)[:2000])

print(f'\n\n=== Trying Clickpost order details API ===')
for sol, cust, awb in awbs:
    try:
        # Try get order details from clickpost
        r = requests.get(f'https://www.clickpost.in/api/v1/order-details/',
            params={'username': 'solara', 'key': CP_KEY, 'waybill': awb},
            timeout=15)
        ct = r.headers.get('content-type', '')
        if 'json' in ct:
            data = r.json()
            if data.get('meta', {}).get('success'):
                result = data.get('result', {})
                order_status = result.get('order_status', '')
                cp_order_type = result.get('order_type', '')
                print(f'{sol:<24} {awb} | order_status={order_status} | type={cp_order_type}')
            else:
                print(f'{sol:<24} {awb} | {data.get("meta",{}).get("message","")[:60]}')
        else:
            print(f'{sol:<24} {awb} | non-JSON')
    except Exception as e:
        print(f'{sol:<24} {awb} | ERR: {e}')
    time.sleep(0.3)

# Try Delhivery direct tracking
print(f'\n\n=== Trying Delhivery direct API ===')
# Delhivery tracking API
DEL_TOKEN = os.getenv('DELHIVERY_API_TOKEN', '')
if not DEL_TOKEN:
    print("No DELHIVERY_API_TOKEN in .env, trying public endpoint...")

for sol, cust, awb in awbs:
    try:
        # Public Delhivery tracking
        r = requests.get(f'https://www.delhivery.com/api/v1/packages/json/',
            params={'waybill': awb},
            headers={'Accept': 'application/json'},
            timeout=15)
        ct = r.headers.get('content-type', '')
        if 'json' in ct:
            data = r.json()
            shipments = data.get('ShipmentData', [])
            if shipments:
                s = shipments[0].get('Shipment', {})
                status = s.get('Status', {})
                print(f'{sol:<24} {awb} | {status.get("Status","")} | {status.get("StatusDateTime","")} | {status.get("StatusLocation","")}')
            else:
                print(f'{sol:<24} {awb} | No shipment data')
        else:
            print(f'{sol:<24} {awb} | non-JSON ({r.status_code})')
    except Exception as e:
        print(f'{sol:<24} {awb} | ERR: {e}')
    time.sleep(0.5)
