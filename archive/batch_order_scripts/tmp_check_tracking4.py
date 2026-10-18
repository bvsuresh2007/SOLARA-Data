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

print(f'{"Order":<24} {"Customer":<22} {"AWB":<20} {"Status":<20} {"Last Scan":<55} {"Date":<18}')
print("=" * 165)

for sol, cust, awb in awbs:
    try:
        r = requests.get(f'https://www.clickpost.in/api/v2/track-order/',
            params={'username': 'solara', 'key': CP_KEY, 'waybill': awb, 'cp_id': 4},
            timeout=15)
        data = r.json()
        if data.get('meta', {}).get('success'):
            result = data.get('result', {}).get(awb, {})
            latest = result.get('latest_status', {})
            desc = latest.get('clickpost_status_description', '')
            remark = latest.get('remark', '')
            ts = latest.get('timestamp', '')
            loc = latest.get('location', '')
            bucket = latest.get('clickpost_status_bucket_description', '')
            created = latest.get('created_at', '')

            # Check if delivered
            status_code = latest.get('clickpost_status_code', 0)
            # 8=Delivered, 9=RTO, 6=OutForDelivery, 7=FailedDelivery, 10=Cancelled
            delivered = status_code == 8
            rto = status_code in (9, 10)

            flag = ''
            if delivered:
                flag = 'DELIVERED'
            elif rto:
                flag = 'RTO/CANCELLED'
            elif status_code in (2, 25):
                flag = 'PICKUP PENDING'
            elif status_code in (3, 4, 5, 6):
                flag = 'IN TRANSIT'
            elif status_code == 7:
                flag = 'FAILED DELIVERY'

            scan_info = f'{remark[:40]} @ {loc[:30]}'
            print(f'{sol:<24} {cust:<22} {awb:<20} {desc+" ("+flag+")":<20} {scan_info:<55} {ts:<18}')
        else:
            print(f'{sol:<24} {cust:<22} {awb:<20} {"API FAIL":<20}')
    except Exception as e:
        print(f'{sol:<24} {cust:<22} {awb:<20} {str(e)[:40]}')
    time.sleep(0.5)
