import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

r2 = requests.post(f'{BASE}/api/method/frappe.client.get_password',
    headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
token = r2.json().get('message', '')
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}

orders = 'SOL1200450 SOL1201081 SOL1201217 SOL1202422 SOL1204428 SOL1204033 SOL1201473 SOL1201544 SOL1201638 SOL1201706 SOL1201965 SOL1201991 SOL1202032 SOL1202163 SOL1202264 SOL1202425 SOL1202432 SOL1202463 SOL1202526 SOL1202788 SOL1202958 SOL1203188 SOL1203242 SOL1203343 SOL1203839 SOL1203884 SOL1204603 SOL1202791 SOL1203676 SOL1204017 SOL1201460 SOL1202200 SOL1204268 SOL1202033 SOL1202219 SOL1202664 SOL1202753 SOL1202827 SOL1202930 SOL1203044 SOL1203337 SOL1203802 SOL1204204 SOL1204601 SOL1201632 SOL1201694 SOL1201713 SOL1202356 SOL1203497'.split()

results = []

for sol in orders:
    print(f'\n--- {sol} ---')

    # Find SO via custom_shopify_order_number
    r = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['custom_shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','customer_name','grand_total','custom_order_type','custom_cod_amount','shipping_address_name','shopify_order_id']),
                'limit_page_length': 5}, timeout=15)
    sos = r.json().get('data', [])

    if not sos:
        # Not on Atlas - check Shopify
        r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders.json',
            headers=SHOP_H, params={'name': sol, 'status': 'any'}, timeout=15)
        sh_orders = r_sh.json().get('orders', [])
        if sh_orders:
            sh = sh_orders[0]
            sa = sh.get('shipping_address') or {}
            fin = sh.get('financial_status', '')
            ful = sh.get('fulfillment_status', '') or 'unfulfilled'
            cancel = sh.get('cancelled_at', '')
            total = sh.get('total_price', '')
            gw = ', '.join(sh.get('payment_gateway_names', []))
            sh_items = [li.get('sku', '') or li.get('title', '')[:30] for li in sh.get('line_items', [])]
            pin = sa.get('zip', '')
            city_sh = sa.get('city', '')
            state_sh = sa.get('province', '')

            svc = ''
            if pin and not cancel:
                try:
                    r_svc = requests.get('https://www.clickpost.in/api/v1/recommendation_api/',
                        params={'key': CP_KEY, 'pickup_pincode': '501218', 'drop_pincode': pin,
                                'order_type': 'PREPAID', 'cod_value': 0}, timeout=10)
                    pref = r_svc.json().get('result', {}).get('preference_array', [])
                    svc = 'serviceable' if pref else 'NOT_SERVICEABLE'
                except:
                    svc = 'check_failed'

            status = 'NOT_ON_ATLAS'
            if cancel:
                status = 'SHOPIFY_CANCELLED'

            print(f'  SHOPIFY ONLY: fin={fin} ful={ful} total=Rs{total} gw={gw}')
            print(f'  PIN={pin} {city_sh} {state_sh} | {svc}')
            print(f'  Items: {sh_items}')
            if cancel:
                print(f'  CANCELLED on Shopify')

            results.append({
                'sol': sol, 'status': status, 'pin': pin, 'svc': svc,
                'fin': fin, 'ful': ful, 'total': total, 'cancel': bool(cancel),
                'gw': gw, 'items': sh_items, 'issues': [status],
            })
        else:
            print(f'  NOT FOUND on Shopify either')
            results.append({'sol': sol, 'status': 'NOT_FOUND', 'issues': ['NOT_FOUND']})
        time.sleep(0.2)
        continue

    so = sos[0]
    so_name = so['name']
    so_ds = so.get('docstatus', 0)
    shopify_oid = so.get('shopify_order_id', '')
    addr_name = so.get('shipping_address_name', '')

    if so_ds == 2:
        # Check Shopify status
        sh_cancel = False
        sh_fin = ''
        if shopify_oid:
            try:
                r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
                sh = r_sh.json().get('order', {})
                sh_fin = sh.get('financial_status', '')
                sh_cancel = bool(sh.get('cancelled_at', ''))
            except:
                pass
        print(f'  SO {so_name} CANCELLED | Shopify fin={sh_fin} cancel={sh_cancel}')
        results.append({'sol': sol, 'status': 'SO_CANCELLED', 'so': so_name, 'issues': ['SO_CANCELLED'], 'sh_cancel': sh_cancel})
        continue

    # Get full SO with items
    r_so_full = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full = r_so_full.json().get('data', {})
    items = so_full.get('items', [])
    item_codes = [it.get('item_code', '') for it in items]
    ghost_skus = any(not ic for ic in item_codes)
    item_codes_clean = [ic for ic in item_codes if ic]

    # Get address details
    pin = ''
    city = ''
    state = ''
    phone = ''
    if addr_name:
        try:
            r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H,
                params={'fields': json.dumps(['pincode', 'city', 'state', 'phone'])}, timeout=10)
            ad = r_a.json().get('data', {})
            pin = str(ad.get('pincode', '') or '')
            city = str(ad.get('city', '') or '')
            state = str(ad.get('state', '') or '')
            phone = str(ad.get('phone', '') or '')
        except:
            pass

    # Get Shopify shipping address for comparison
    sh_pin = ''
    sh_fin = ''
    sh_ful = ''
    sh_cancel = False
    sh_gw = ''
    sh_addr1 = ''
    if shopify_oid:
        try:
            r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
            sh = r_sh.json().get('order', {})
            sa = sh.get('shipping_address') or {}
            sh_pin = sa.get('zip', '')
            sh_addr1 = sa.get('address1', '')
            sh_fin = sh.get('financial_status', '')
            sh_ful = sh.get('fulfillment_status', '') or 'unfulfilled'
            sh_cancel = bool(sh.get('cancelled_at', ''))
            sh_gw = ', '.join(sh.get('payment_gateway_names', []))
        except:
            pass

    # PIN mismatch check
    pin_mismatch = False
    if pin and sh_pin and str(pin).strip() != str(sh_pin).strip():
        pin_mismatch = True

    # Get DNs
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['custom_shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','awb_number','courier_partner','posting_date']),
                'limit_page_length': 20}, timeout=15)
    all_dns = r_dn.json().get('data', [])
    if not all_dns:
        r_dn2 = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
            params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                    'fields': json.dumps(['name','docstatus','awb_number','courier_partner','posting_date']),
                    'limit_page_length': 20}, timeout=15)
        all_dns = r_dn2.json().get('data', [])

    active_dns = [d for d in all_dns if d.get('docstatus') != 2]
    cancelled_dns = [d for d in all_dns if d.get('docstatus') == 2]
    draft_dns = [d for d in all_dns if d.get('docstatus') == 0]
    submitted_dns = [d for d in all_dns if d.get('docstatus') == 1]
    has_awb = any(d.get('awb_number') for d in active_dns)

    # Check serviceability
    svc = ''
    svc_couriers = []
    check_pin = sh_pin or pin
    if check_pin:
        try:
            otype_cp = 'COD' if so.get('custom_order_type', '') in ('COD', 'PPCOD') else 'PREPAID'
            cod_v = float(so.get('custom_cod_amount', 0) or 0) if otype_cp == 'COD' else 0
            r_svc = requests.get('https://www.clickpost.in/api/v1/recommendation_api/',
                params={'key': CP_KEY, 'pickup_pincode': '501218', 'drop_pincode': check_pin,
                        'order_type': otype_cp, 'cod_value': cod_v}, timeout=10)
            pref = r_svc.json().get('result', {}).get('preference_array', [])
            svc = 'serviceable' if pref else 'NOT_SERVICEABLE'
            svc_couriers = [p.get('courier_name', '') for p in pref[:3]]
        except:
            svc = 'check_failed'

    # Check stock
    stock_issues = []
    for ic in item_codes_clean:
        r_bin = requests.get(f'{BASE}/api/resource/Bin', headers=H,
            params={'filters': json.dumps([['item_code','=',ic],['warehouse','=','Main Warehouse - WTBBPL']]),
                    'fields': json.dumps(['actual_qty','reserved_qty']),
                    'limit_page_length': 1}, timeout=10)
        bins = r_bin.json().get('data', [])
        if bins:
            aq = float(bins[0].get('actual_qty', 0))
            rq = float(bins[0].get('reserved_qty', 0))
            avail = aq - rq
            if avail < 0:
                stock_issues.append(f'{ic}(avail={avail:.0f})')
        else:
            # Check if item is a bundle
            r_bun = requests.get(f'{BASE}/api/resource/Product Bundle', headers=H,
                params={'filters': json.dumps([['new_item_code','=',ic]]),
                        'fields': json.dumps(['name']),
                        'limit_page_length': 1}, timeout=10)
            is_bundle = len(r_bun.json().get('data', [])) > 0
            if not is_bundle:
                stock_issues.append(f'{ic}(no_bin)')

    # Check error logs
    error_msg = ''
    for dn in submitted_dns[:1]:
        dn_name = dn['name']
        r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
            params={'filters': json.dumps([['error','like',f'%{dn_name}%']]),
                    'fields': json.dumps(['error','creation']),
                    'limit_page_length': 1, 'order_by': 'creation desc'}, timeout=10)
        errs = r_err.json().get('data', [])
        if errs:
            error_msg = errs[0].get('error', '')[:200]

    # Determine issues
    issues = []
    if ghost_skus:
        issues.append('GHOST_SKU')
    if not addr_name:
        issues.append('NO_ADDRESS')
    if pin_mismatch:
        issues.append(f'PIN_MISMATCH(atlas={pin},shopify={sh_pin})')
    if svc == 'NOT_SERVICEABLE':
        issues.append('NOT_SERVICEABLE')
    if not active_dns and so_ds == 1:
        issues.append('NO_DN')
    if draft_dns and not submitted_dns:
        issues.append('DN_DRAFT_ONLY')
    if submitted_dns and not has_awb:
        issues.append('SUBMITTED_NO_AWB')
    if stock_issues:
        issues.append(f'STOCK({",".join(stock_issues)})')
    if sh_cancel:
        issues.append('SHOPIFY_CANCELLED')
    if error_msg:
        issues.append('HAS_ERROR_LOG')

    dn_list = []
    for d in active_dns:
        dds = {0: 'Draft', 1: 'Submitted'}.get(d.get('docstatus', 0), '?')
        dn_list.append(f'{d["name"]}({dds})')

    print(f'  SO={so_name} ds={so_ds} type={so.get("custom_order_type","")} Rs{so.get("grand_total",0)} cod={so.get("custom_cod_amount",0)}')
    print(f'  Atlas PIN={pin} {city} {state} | Shopify PIN={sh_pin}')
    print(f'  Mismatch={pin_mismatch} | {svc} couriers={svc_couriers}')
    print(f'  Items: {item_codes_clean} ghost={ghost_skus}')
    print(f'  DNs active: {dn_list} | cancelled={len(cancelled_dns)}')
    print(f'  Shopify: fin={sh_fin} ful={sh_ful} gw={sh_gw} cancel={sh_cancel}')
    if stock_issues:
        print(f'  Stock: {stock_issues}')
    if error_msg:
        print(f'  Error: {error_msg[:150]}')
    print(f'  >> ISSUES: {issues}')

    results.append({
        'sol': sol, 'so': so_name, 'so_ds': so_ds, 'type': so.get('custom_order_type', ''),
        'total': so.get('grand_total', 0), 'cod': so.get('custom_cod_amount', 0),
        'pin': pin, 'sh_pin': sh_pin, 'city': city, 'state': state,
        'svc': svc, 'svc_couriers': svc_couriers, 'phone': phone,
        'items': item_codes_clean, 'ghost': ghost_skus,
        'dns': dn_list, 'draft_dns': len(draft_dns), 'submitted_dns': len(submitted_dns),
        'cancelled_dns': len(cancelled_dns), 'has_awb': has_awb,
        'pin_mismatch': pin_mismatch, 'addr_name': addr_name,
        'sh_fin': sh_fin, 'sh_ful': sh_ful, 'sh_gw': sh_gw, 'sh_cancel': sh_cancel,
        'stock_issues': stock_issues, 'error': error_msg, 'issues': issues,
        'status': ','.join(issues) if issues else 'OK', 'shopify_oid': shopify_oid,
    })

    time.sleep(0.2)

# =============================================
# GROUPING SUMMARY
# =============================================
print(f'\n\n{"="*80}')
print(f'INVESTIGATION COMPLETE — {len(orders)} orders')
print(f'{"="*80}')

# Group by primary issue
group_map = {}
for r in results:
    issues = r.get('issues', [])
    if 'SO_CANCELLED' in issues:
        grp = 'SO_CANCELLED'
    elif 'SHOPIFY_CANCELLED' in issues:
        grp = 'SHOPIFY_CANCELLED'
    elif 'NOT_ON_ATLAS' in issues:
        grp = 'NOT_ON_ATLAS'
    elif 'NOT_FOUND' in issues:
        grp = 'NOT_FOUND'
    elif 'NOT_SERVICEABLE' in issues:
        grp = 'NOT_SERVICEABLE'
    elif 'GHOST_SKU' in issues:
        grp = 'GHOST_SKU'
    elif any('PIN_MISMATCH' in i for i in issues):
        grp = 'PIN_MISMATCH'
    elif any('STOCK' in i for i in issues):
        grp = 'STOCK_ISSUE'
    elif 'NO_DN' in issues:
        grp = 'NO_DN'
    elif 'DN_DRAFT_ONLY' in issues:
        grp = 'DN_DRAFT'
    elif 'SUBMITTED_NO_AWB' in issues:
        grp = 'SUBMITTED_NO_AWB'
    elif 'NO_ADDRESS' in issues:
        grp = 'NO_ADDRESS'
    else:
        grp = 'OTHER'

    group_map.setdefault(grp, []).append(r)

for grp, items in sorted(group_map.items(), key=lambda x: -len(x[1])):
    print(f'\n{"="*60}')
    print(f'GROUP: {grp} — {len(items)} orders')
    print(f'{"="*60}')
    for r in items:
        sol = r['sol']
        so = r.get('so', '-')
        pin = r.get('sh_pin', '') or r.get('pin', '')
        total = r.get('total', '')
        otype = r.get('type', '')
        issues_str = ', '.join(r.get('issues', []))
        dns_str = ', '.join(r.get('dns', [])) if r.get('dns') else 'none'
        svc = r.get('svc', '')
        items_str = ', '.join(r.get('items', []))
        print(f'  {sol} | SO={so} | {otype} Rs{total} | PIN={pin} {svc}')
        print(f'    Items: {items_str}')
        print(f'    DNs: {dns_str}')
        print(f'    Issues: {issues_str}')
