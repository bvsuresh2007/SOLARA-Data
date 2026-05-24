import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

r = requests.post(f'{BASE}/api/method/frappe.client.get_password',
                   headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
token = r.json().get('message', '')
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}

shipped = [
    ('SOL1203003', 'SHPDN27-10674', '29044411187060', 'Delhivery'),
    ('SOL1203039', 'SHPDN27-10694', '29044411187071', 'Delhivery'),
    ('SOL1202832', 'SHPDN27-10784', '29044411189543', 'Delhivery'),
    ('SOL1202862', 'SHPDN27-10807', '29044411189591', 'Delhivery'),
    ('SOL1202886', 'SHPDN27-10822', '29044411189624', 'Delhivery'),
    ('SOL1202927', 'SHPDN27-10730', '29044411189646', 'Delhivery'),
    ('SOL1202970', 'SHPDN27-10762', '29044411189661', 'Delhivery'),
    ('SOL1203151', 'SHPDN27-10569', '29044411189720', 'Delhivery'),
    ('SOL1203153', 'SHPDN27-10570', '29044411189742', 'Delhivery'),
    ('SOL1203161', 'SHPDN27-10577', '29044411189775', 'Delhivery'),
    ('SOL1203170', 'SHPDN27-10582', '29044411189790', 'Delhivery'),
    ('SOL1203184', 'SHPDN27-10589', '29044411189812', 'Delhivery'),
    ('SOL1203210', 'SHPDN27-10606', '29044411189823', 'Delhivery'),
    ('SOL1202828', 'SHPDN27-10845', '29044411190512', 'Delhivery'),
    ('SOL1202845', 'SHPDN27-10793', '29044411190523', 'Delhivery'),
    ('SOL1202858', 'SHPDN27-10803', '29044411190534', 'Delhivery'),
    ('SOL1202868', 'SHPDN27-10810', '29044411190545', 'Delhivery'),
    ('SOL1203048', 'SHPDN27-10700', '29044411190556', 'Delhivery'),
    ('SOL1203089', 'SHPDN27-10629', '29044411190560', 'Delhivery'),
    ('SOL1203130', 'SHPDN27-10655', '29044411190571', 'Delhivery'),
    ('SOL1203135', 'SHPDN27-10660', '29044411190582', 'Delhivery'),
    ('SOL1202946', 'SHPDN27-11243', '29044411190770', 'Delhivery'),
    ('SOL1202977', 'SHPDN27-11244', '29044411190781', 'Delhivery'),
    ('SOL1202834', 'SHPDN27-10786', '29044411190792', 'Delhivery'),
    ('SOL1202824', 'SHPDN27-10780', '50938446974', 'Bluedart'),
    ('SOL1202897', 'SHPDN27-10831', '50938446985', 'Bluedart'),
    ('SOL1202968', 'SHPDN27-10861', '50938446996', 'Bluedart'),
    ('SOL1202978', 'SHPDN27-10765', '50938447324', 'Bluedart'),
    # SOL1203223 skipped (SOL-WB-113 stock issue)
]

print(f"{'SOL':<13} {'DN':<16} {'AWB':<14} {'CP':<10} {'Shopify Pay':<18} {'Atlas Type':<12} {'COD Amt':>8} {'Label':>6} {'Ful Sync':>9}")
print("-" * 120)

issues = []
for sol, dn, awb, cp in shipped:
    # Atlas SO
    try:
        r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
            params={'filters': json.dumps([['shopify_order_number','=',sol],['docstatus','=',1]]),
                    'fields': json.dumps(['name','shopify_order_id','custom_order_type','custom_cod_amount','custom_prepaid_amount']),
                    'limit_page_length': 1}, timeout=20)
        sos = r_so.json().get('data', [])
        so_d = sos[0] if sos else {}
    except:
        so_d = {}

    atlas_type = so_d.get('custom_order_type', '') or 'N/A'
    cod_amt = float(so_d.get('custom_cod_amount', 0) or 0)
    shopify_oid = so_d.get('shopify_order_id', '')

    # Shopify payment
    shopify_pay = ''
    shopify_ful = ''
    if shopify_oid:
        try:
            r_shop = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json',
                                  headers=SHOP_H,
                                  params={'fields': 'financial_status,payment_gateway_names,fulfillment_status,fulfillments'},
                                  timeout=15)
            order = r_shop.json().get('order', {})
            fin_status = order.get('financial_status', '')
            gateways = order.get('payment_gateway_names', [])
            shopify_pay = fin_status
            if gateways:
                shopify_pay = shopify_pay + ' (' + ','.join(gateways[:2]) + ')'

            # Check fulfillment sync
            fuls = order.get('fulfillments', [])
            if fuls:
                latest = fuls[-1]
                ful_tracking = latest.get('tracking_number', '')
                if ful_tracking == awb:
                    shopify_ful = 'OK'
                elif ful_tracking:
                    shopify_ful = 'STALE'
                else:
                    shopify_ful = 'NO_TRK'
            else:
                ful_status = order.get('fulfillment_status', '')
                if ful_status == 'fulfilled':
                    shopify_ful = 'OK?'
                else:
                    shopify_ful = 'NONE'
        except Exception as e:
            shopify_pay = 'ERR'
            shopify_ful = 'ERR'
    else:
        shopify_pay = 'NO_OID'
        shopify_ful = 'NO_OID'

    # Check label via Clickpost
    label = ''
    try:
        r_label = requests.get(f'https://www.clickpost.in/api/v1/tracking/?username=solara&key=d3464616-bbd6-4874-919a-a7e8bd14d66f&waybill={awb}',
                               headers={'Content-Type': 'application/json'}, timeout=10)
        label_resp = r_label.json()
        if label_resp.get('meta', {}).get('success'):
            label = 'YES'
        else:
            label = 'NO'
    except:
        label = '?'

    # Flag issues
    issue_flags = []
    if shopify_ful not in ('OK', 'OK?'):
        issue_flags.append(f'fulfillment={shopify_ful}')
    if 'cod' in atlas_type.lower() and cod_amt == 0:
        issue_flags.append('COD=0')
    if shopify_pay == 'NO_OID':
        issue_flags.append('no_shopify_oid')

    row = f"{sol:<13} {dn:<16} {awb:<14} {cp:<10} {shopify_pay:<18} {atlas_type:<12} {cod_amt:>8.0f} {label:>6} {shopify_ful:>9}"
    print(row)
    if issue_flags:
        issues.append((sol, dn, issue_flags))

    time.sleep(0.3)

if issues:
    print(f"\n{'='*80}")
    print(f"ISSUES FOUND ({len(issues)}):")
    for sol, dn, flags in issues:
        print(f"  {sol} {dn}: {', '.join(flags)}")
else:
    print(f"\nAll clear - no issues found")
