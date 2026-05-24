import os, requests, json, time, sys, traceback
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {
    'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}',
    'Content-Type': 'application/json'
}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

# Get Shopify token from Atlas
print("=== Getting Shopify token from Atlas ===")
r = requests.get(f'{BASE}/api/method/frappe.client.get_password',
    params={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'},
    headers=H)
SHOPIFY_TOKEN = r.json()['message']
SHOPIFY_STORE = 'https://dev-solara.myshopify.com'
SHOPIFY_API = '2024-01'
SH = {'X-Shopify-Access-Token': SHOPIFY_TOKEN, 'Content-Type': 'application/json'}
print(f"Shopify token obtained: {SHOPIFY_TOKEN[:8]}...")

ORDERS = [
    {
        'number': 'SOL1209834',
        'items': ['SOL-AF-501-SIL-BASKET-P6-SPY-101', 'SOL-CI-PNY-101', 'SOL-CI-KD-103-DT-102-FP-102', 'SOL-CKW-WSPA-101']
    },
    {
        'number': 'SOL1209894',
        'items': ['SOL-INS-WB-305', 'SOL-INS-WB-301']
    },
    {
        'number': 'SOL1209976',
        'items': ['SOL-AF-PP-101', 'SOL-AF-SIL-BASKET-P6-SPY-101-AF-PP-101', 'SOL-JUC-BAG-121', 'SOL-AFO-501-JUC-121', 'SOL-AF-501-CVR-BAG']
    }
]

WAREHOUSE = 'Main Warehouse - WTBBPL'
COMPANY = 'Win The Buy Box Private Limited'
PICKUP = {
    'name': 'WIN THE BUY BOX PVT LTD',
    'phone': '9573652101',
    'address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
    'city': 'Hyderabad',
    'state': 'Telangana',
    'pin': '501218',
    'email': 'hydwh@solara.in'
}

results = []

def get_shopify_order(order_number):
    """Step 0: Get Shopify order details"""
    print(f"\n--- Step 0: Getting Shopify order {order_number} ---")
    # Shopify uses the numeric part for 'name' search
    r = requests.get(f'{SHOPIFY_STORE}/admin/api/{SHOPIFY_API}/orders.json',
        params={'name': order_number, 'status': 'any'}, headers=SH)
    r.raise_for_status()
    orders = r.json().get('orders', [])
    if not orders:
        raise Exception(f"Shopify order {order_number} not found")
    order = orders[0]
    print(f"  Found Shopify order #{order['order_number']} - {order['name']} - {order.get('financial_status')}")
    print(f"  Customer: {order.get('shipping_address', {}).get('name', 'N/A')}")
    print(f"  Total: {order['total_price']}")
    print(f"  Line items: {len(order.get('line_items', []))}")

    # Payment detection
    financial_status = order.get('financial_status', '')
    total_price = float(order['total_price'])
    cod_amount = 0

    if financial_status == 'paid':
        payment_type = 'PREPAID'
    elif financial_status == 'partially_paid':
        payment_type = 'PPCOD'
        # Get transactions
        tr = requests.get(f'{SHOPIFY_STORE}/admin/api/{SHOPIFY_API}/orders/{order["id"]}/transactions.json', headers=SH)
        tr.raise_for_status()
        txns = tr.json().get('transactions', [])
        captured = sum(float(t.get('amount', 0)) for t in txns if t.get('kind') == 'capture' and t.get('status') == 'success')
        cod_amount = round(total_price - captured, 2)
    elif financial_status == 'pending':
        payment_type = 'COD'
        cod_amount = total_price
    else:
        payment_type = 'PREPAID'

    print(f"  Payment: {payment_type}" + (f" (COD amount: {cod_amount})" if cod_amount > 0 else ""))

    return order, payment_type, cod_amount

def find_or_create_customer(customer_name):
    """Step 1: Find or create customer"""
    print(f"\n--- Step 1: Finding/creating customer '{customer_name}' ---")
    r = requests.get(f'{BASE}/api/resource/Customer',
        params={'filters': json.dumps([['customer_name', '=', customer_name]]), 'fields': json.dumps(['name'])},
        headers=H)
    data = r.json().get('data', [])
    if data:
        cid = data[0]['name']
        print(f"  Found existing customer: {cid}")
        return cid

    # Create
    r = requests.post(f'{BASE}/api/resource/Customer', headers=H, json={
        'customer_name': customer_name,
        'customer_type': 'Individual',
        'customer_group': 'Individual',
        'territory': 'India'
    })
    r.raise_for_status()
    cid = r.json()['data']['name']
    print(f"  Created customer: {cid}")
    return cid

def create_address(customer_id, customer_name, shipping_addr, order_number, email):
    """Step 2: Create address from Shopify shipping_address"""
    print(f"\n--- Step 2: Creating address for {order_number} ---")
    addr_title = f"{customer_name}-{order_number}"

    # Check if already exists
    r = requests.get(f'{BASE}/api/resource/Address',
        params={'filters': json.dumps([['address_title', '=', addr_title]]), 'fields': json.dumps(['name'])},
        headers=H)
    existing = r.json().get('data', [])
    if existing:
        print(f"  Address already exists: {existing[0]['name']}")
        return existing[0]['name']

    phone = shipping_addr.get('phone', '') or ''
    # Clean phone - remove non-digits, take last 10
    phone_digits = ''.join(c for c in phone if c.isdigit())
    if len(phone_digits) > 10:
        phone_digits = phone_digits[-10:]

    payload = {
        'address_title': addr_title,
        'address_type': 'Shipping',
        'address_line1': shipping_addr.get('address1', '') or 'N/A',
        'address_line2': shipping_addr.get('address2', '') or '',
        'city': shipping_addr.get('city', '') or 'N/A',
        'state': shipping_addr.get('province', '') or '',
        'pincode': shipping_addr.get('zip', '') or '',
        'country': 'India',
        'phone': phone_digits or '0000000000',
        'email_id': email or 'noreply@solara.in',
        'links': [{'link_doctype': 'Customer', 'link_name': customer_id}]
    }
    r = requests.post(f'{BASE}/api/resource/Address', headers=H, json=payload)
    r.raise_for_status()
    addr_name = r.json()['data']['name']
    print(f"  Created address: {addr_name} (PIN: {shipping_addr.get('zip', 'N/A')})")
    return addr_name

def check_pincode_serviceability(pincode, payment_type, cod_amount=0):
    """Check if pincode is serviceable via Clickpost"""
    order_type = 'PREPAID' if payment_type == 'PREPAID' else 'COD'
    cod_val = 0 if payment_type == 'PREPAID' else (cod_amount or 1)
    url = f'https://www.clickpost.in/api/v1/recommendation_api/?key={CP_KEY}&pickup_pincode=501218&drop_pincode={pincode}&order_type={order_type}&cod_value={cod_val}'
    r = requests.get(url)
    data = r.json()
    # API may return dict or list
    if isinstance(data, dict):
        pref = data.get('result', {})
        if isinstance(pref, dict):
            pref = pref.get('preference_array', [])
        elif isinstance(pref, list):
            pass
        else:
            pref = []
    elif isinstance(data, list):
        pref = data
    else:
        pref = []
    if not pref:
        print(f"  WARNING: Pincode {pincode} is NOT serviceable! Response: {str(data)[:200]}")
        return False
    print(f"  Pincode {pincode} serviceable - {len(pref)} courier(s) available")
    return True

def check_and_fix_stock(item_codes):
    """Step 3: Check stock and create Material Receipt if needed"""
    print(f"\n--- Step 3: Checking stock ---")
    stock_entries_created = []

    for item_code in item_codes:
        # Check if stock item
        r = requests.get(f'{BASE}/api/resource/Item/{item_code}', params={'fields': json.dumps(['is_stock_item', 'item_name'])}, headers=H)
        if r.status_code != 200:
            print(f"  ERROR: Item {item_code} not found on Atlas!")
            continue
        item_data = r.json()['data']
        is_stock = item_data.get('is_stock_item', 1)

        if not is_stock:
            print(f"  {item_code} - Product Bundle (not stock item), skip stock check")
            continue

        # Check bin
        r = requests.get(f'{BASE}/api/resource/Bin',
            params={
                'filters': json.dumps([['item_code', '=', item_code], ['warehouse', '=', WAREHOUSE]]),
                'fields': json.dumps(['actual_qty', 'reserved_qty'])
            }, headers=H)
        bins = r.json().get('data', [])

        if bins:
            actual = bins[0].get('actual_qty', 0)
            reserved = bins[0].get('reserved_qty', 0)
            available = actual - reserved
            print(f"  {item_code} - actual:{actual} reserved:{reserved} available:{available}")
            if available >= 1:
                continue
            needed = max(1 - int(available), 1)
        else:
            print(f"  {item_code} - No bin record, need stock")
            needed = 1

        # Get valuation rate
        r = requests.get(f'{BASE}/api/resource/Stock Ledger Entry',
            params={
                'filters': json.dumps([['item_code', '=', item_code], ['warehouse', '=', WAREHOUSE]]),
                'fields': json.dumps(['valuation_rate']),
                'order_by': 'posting_date desc,posting_time desc',
                'limit_page_length': 1
            }, headers=H)
        sle = r.json().get('data', [])
        val_rate = sle[0]['valuation_rate'] if sle and sle[0].get('valuation_rate') else 1

        print(f"  Creating Material Receipt for {item_code} x{needed} @ Rs {val_rate}")
        payload = {
            'stock_entry_type': 'Material Receipt',
            'items': [{
                'item_code': item_code,
                'qty': needed,
                't_warehouse': WAREHOUSE,
                'basic_rate': val_rate,
                'expense_account': 'Stock Adjustment - WTBBPL'
            }]
        }
        r = requests.post(f'{BASE}/api/resource/Stock Entry', headers=H, json=payload)
        r.raise_for_status()
        se_name = r.json()['data']['name']

        # Submit
        r = requests.put(f'{BASE}/api/resource/Stock Entry/{se_name}', headers=H, json={'docstatus': 1})
        r.raise_for_status()
        print(f"  Submitted Stock Entry: {se_name}")
        stock_entries_created.append(se_name)

    return stock_entries_created

def create_sales_order(customer_id, addr_name, order_number, shopify_order, items_codes, payment_type, cod_amount):
    """Step 4: Create Sales Order"""
    print(f"\n--- Step 4: Creating Sales Order for {order_number} ---")

    # Check if SO already exists
    r = requests.get(f'{BASE}/api/resource/Sales Order',
        params={
            'filters': json.dumps([['shopify_order_number', '=', order_number], ['docstatus', '!=', 2]]),
            'fields': json.dumps(['name', 'docstatus'])
        }, headers=H)
    existing = r.json().get('data', [])
    if existing:
        print(f"  SO already exists: {existing[0]['name']} (docstatus={existing[0]['docstatus']})")
        return existing[0]['name']

    # Build items from Shopify line items mapped to our item codes
    shopify_items = shopify_order.get('line_items', [])
    so_items = []

    # Map shopify line items to our codes by position
    for i, item_code in enumerate(items_codes):
        if i < len(shopify_items):
            si = shopify_items[i]
            rate = float(si.get('price', 0))
            qty = int(si.get('quantity', 1))
        else:
            rate = 0
            qty = 1
        so_items.append({
            'item_code': item_code,
            'qty': qty,
            'rate': rate,
            'warehouse': WAREHOUSE
        })

    # Get shopify_order_id from the Shopify order
    shopify_order_id = str(shopify_order['id'])

    # For D2C Shopify orders: always use Unregistered, no customer GSTIN
    # All 3 orders are interstate from Telangana, use IGST inclusive
    # NOTE: Do NOT set shopify_order_id here — the "Force Shopify D2C Customer" server script
    # fires on Before Insert when shopify_order_id is present, which can override gst_category.
    # We set shopify_order_id AFTER insert, before submit.
    payload = {
        'customer': customer_id,
        'company': COMPANY,
        'delivery_date': '2026-05-23',
        'shipping_address_name': addr_name,
        'customer_address': addr_name,
        'shopify_order_number': order_number,
        'custom_order_type': 'Prepaid' if payment_type == 'PREPAID' else ('COD' if payment_type == 'COD' else 'PPCOD'),
        'items': so_items,
        'taxes_and_charges': 'Shopify IGST 18% Inclusive - WTBBPL',
        'gst_category': 'Unregistered',
        'customer_gstin': '',
    }

    if payment_type in ('COD', 'PPCOD') and cod_amount > 0:
        payload['custom_cod_amount'] = cod_amount

    r = requests.post(f'{BASE}/api/resource/Sales Order', headers=H, json=payload)
    if r.status_code != 200:
        print(f"  ERROR creating SO: {r.status_code} - {r.text[:800]}")
        r.raise_for_status()

    so_name = r.json()['data']['name']
    print(f"  Created SO: {so_name}")

    # Set shopify_order_id after creation (avoid Before Insert server script overriding gst_category)
    r = requests.put(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H,
        json={'shopify_order_id': shopify_order_id})
    if r.status_code != 200:
        print(f"  WARNING: Could not set shopify_order_id: {r.status_code}")

    # Submit
    r = requests.put(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, json={'docstatus': 1})
    if r.status_code != 200:
        print(f"  ERROR submitting SO: {r.status_code} - {r.text[:800]}")
        r.raise_for_status()
    print(f"  Submitted SO: {so_name}")

    return so_name

def create_delivery_note(so_name, addr_name, payment_type, cod_amount, shopify_order_id, order_number):
    """Step 5: Create DN from SO"""
    print(f"\n--- Step 5: Creating DN from {so_name} ---")

    # Check if DN already exists
    r = requests.get(f'{BASE}/api/resource/Delivery Note',
        params={
            'filters': json.dumps([['against_sales_order', '=', so_name], ['docstatus', '!=', 2]]),
            'fields': json.dumps(['name', 'docstatus'])
        }, headers=H)
    # Try alternate filter
    if not r.json().get('data'):
        r = requests.get(f'{BASE}/api/resource/Delivery Note',
            params={
                'filters': json.dumps([['shopify_order_number', '=', order_number], ['docstatus', '!=', 2]]),
                'fields': json.dumps(['name', 'docstatus'])
            }, headers=H)
    existing = r.json().get('data', [])
    if existing:
        print(f"  DN already exists: {existing[0]['name']} (docstatus={existing[0]['docstatus']})")
        return existing[0]['name']

    # Make DN from SO
    r = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
        params={'source_name': so_name}, headers=H)

    if r.status_code == 200:
        dn_doc = r.json().get('message', {})
    else:
        print(f"  make_delivery_note failed ({r.status_code}), creating manually")
        # Get SO details
        r2 = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H)
        so_data = r2.json()['data']
        dn_doc = {
            'customer': so_data['customer'],
            'company': COMPANY,
            'items': []
        }
        for item in so_data.get('items', []):
            dn_doc['items'].append({
                'item_code': item['item_code'],
                'qty': item['qty'],
                'rate': item['rate'],
                'warehouse': WAREHOUSE,
                'against_sales_order': so_name,
                'so_detail': item['name']
            })

    # Set required fields
    dn_doc['shipping_address_name'] = addr_name
    dn_doc['customer_address'] = addr_name
    dn_doc['shopify_order_id'] = shopify_order_id
    dn_doc['shopify_order_number'] = order_number

    # Clear taxes
    dn_doc['taxes'] = []
    if 'items' in dn_doc:
        for item in dn_doc['items']:
            item.pop('item_tax_template', None)
            item.pop('item_tax_rate', None)

    # Set COD amount before submit
    if payment_type in ('COD', 'PPCOD') and cod_amount > 0:
        dn_doc['custom_cod_amount'] = cod_amount

    # Remove fields that cause issues
    for field in ['name', 'amended_from', 'docstatus', 'creation', 'modified', 'owner', 'modified_by']:
        dn_doc.pop(field, None)

    r = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_doc)
    if r.status_code != 200:
        print(f"  ERROR creating DN: {r.status_code} - {r.text[:500]}")
        r.raise_for_status()

    dn_name = r.json()['data']['name']
    print(f"  Created DN: {dn_name}")

    # Submit
    r = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, json={'docstatus': 1})
    if r.status_code != 200:
        print(f"  ERROR submitting DN: {r.status_code} - {r.text[:500]}")
        r.raise_for_status()
    print(f"  Submitted DN: {dn_name}")

    return dn_name

def check_awb(dn_name):
    """Step 6: Check auto-AWB"""
    print(f"\n--- Step 6: Checking AWB on {dn_name} ---")
    time.sleep(4)
    r = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}',
        params={'fields': json.dumps(['awb_number', 'tracking_url'])}, headers=H)
    data = r.json().get('data', {})
    awb = data.get('awb_number', '')
    tracking = data.get('tracking_url', '')
    if awb:
        print(f"  Auto-AWB found: {awb}")
        # Determine courier from tracking URL
        courier = 'Delhivery' if 'delhivery' in (tracking or '').lower() else 'Bluedart' if 'bluedart' in (tracking or '').lower() else 'Unknown'
        return awb, courier
    print(f"  No auto-AWB yet")
    return None, None

def manual_clickpost(so_name, dn_name, customer_name, phone, addr, payment_type, cod_amount, total_price):
    """Step 7: Manual Clickpost AWB creation"""
    print(f"\n--- Step 7: Manual Clickpost for {dn_name} ---")

    drop_pin = addr.get('zip', '')
    drop_city = addr.get('city', '')
    drop_state = addr.get('province', '')
    drop_addr = f"{addr.get('address1', '')} {addr.get('address2', '')}".strip()
    drop_phone = addr.get('phone', '')
    phone_digits = ''.join(c for c in (drop_phone or '') if c.isdigit())
    if len(phone_digits) > 10:
        phone_digits = phone_digits[-10:]

    order_type = 'PREPAID' if payment_type == 'PREPAID' else 'COD'
    cod_val = 0 if payment_type == 'PREPAID' else (cod_amount or float(total_price))
    invoice_val = max(float(total_price), 1.0)

    for cp_id, courier_name in [(4, 'Delhivery'), (5, 'Bluedart')]:
        print(f"  Trying {courier_name} (cp_id={cp_id})...")
        payload = {
            "pickup_info": {
                "pickup_name": PICKUP['name'],
                "pickup_phone": PICKUP['phone'],
                "pickup_address": PICKUP['address'],
                "pickup_city": PICKUP['city'],
                "pickup_state": PICKUP['state'],
                "pickup_pincode": PICKUP['pin'],
                "email": PICKUP['email'],
                "pickup_time": "2026-05-23T18:00:00+05:30"
            },
            "drop_info": {
                "drop_name": customer_name,
                "drop_phone": phone_digits or '0000000000',
                "drop_address": drop_addr or 'N/A',
                "drop_city": drop_city or 'N/A',
                "drop_state": drop_state or '',
                "drop_pincode": drop_pin,
                "drop_email": "noreply@solara.in"
            },
            "return_info": {
                "return_name": PICKUP['name'],
                "return_phone": PICKUP['phone'],
                "return_address": PICKUP['address'],
                "return_city": PICKUP['city'],
                "return_state": PICKUP['state'],
                "return_pincode": PICKUP['pin'],
                "return_email": PICKUP['email']
            },
            "order_info": {
                "reference_number": so_name,
                "order_type": order_type,
                "invoice_value": invoice_val,
                "cod_value": cod_val,
                "weight": 500,
                "length": 30,
                "breadth": 20,
                "height": 15,
                "items": [{"sku": "SOLARA", "description": "Solara Products", "quantity": 1, "price": invoice_val}]
            },
            "additional": {
                "delivery_type": "FORWARD",
                "async": False,
                "label": True
            },
            "cp_id": cp_id
        }

        r = requests.post(
            f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
            json=payload
        )
        resp = r.json()

        if resp.get('meta', {}).get('status') == 200:
            awb = resp.get('result', {}).get('waybill', '')
            print(f"  SUCCESS: AWB {awb} via {courier_name}")

            # Save AWB to DN
            try:
                tracking_url = f'https://www.delhivery.com/track/package/{awb}' if courier_name == 'Delhivery' else f'https://www.bluedart.com/tracking/{awb}'
                r2 = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H,
                    json={'awb_number': awb, 'tracking_url': tracking_url})
                if r2.status_code == 200:
                    print(f"  Saved AWB to DN")
                else:
                    print(f"  Could not save AWB to DN: {r2.status_code} - {r2.text[:200]}")
            except Exception as e:
                print(f"  Could not save AWB to DN: {e}")

            return awb, courier_name
        else:
            print(f"  Failed: {resp.get('meta', {}).get('message', resp)}")

    return None, None

def sync_shopify_fulfillment(shopify_order, awb, courier_name):
    """Step 8: Sync fulfillment to Shopify"""
    order_id = shopify_order['id']
    order_number = shopify_order['name']
    print(f"\n--- Step 8: Syncing to Shopify {order_number} ---")

    fulfillment_status = shopify_order.get('fulfillment_status', '')

    if courier_name == 'Delhivery':
        tracking_company = 'Delhivery'
        tracking_url = f'https://www.delhivery.com/track/package/{awb}'
    else:
        tracking_company = 'Bluedart'
        tracking_url = f'https://www.bluedart.com/tracking/{awb}'

    # Strip security_key
    if '&security_key=' in tracking_url:
        tracking_url = tracking_url.split('&security_key=')[0]

    if fulfillment_status == 'fulfilled':
        # Update tracking on last fulfillment
        print(f"  Already fulfilled, updating tracking...")
        fulfillments = shopify_order.get('fulfillments', [])
        if fulfillments:
            ff_id = fulfillments[-1]['id']
            r = requests.post(f'{SHOPIFY_STORE}/admin/api/{SHOPIFY_API}/fulfillments/{ff_id}/update_tracking.json',
                headers=SH, json={
                    'fulfillment': {
                        'tracking_info': {
                            'company': tracking_company,
                            'number': awb,
                            'url': tracking_url
                        },
                        'notify_customer': True
                    }
                })
            if r.status_code == 200:
                print(f"  Tracking updated on Shopify")
                return True
            else:
                print(f"  Failed to update tracking: {r.status_code} - {r.text[:300]}")
                return False
    else:
        # Create fulfillment
        print(f"  Creating fulfillment...")
        # Get fulfillment orders
        r = requests.get(f'{SHOPIFY_STORE}/admin/api/{SHOPIFY_API}/orders/{order_id}/fulfillment_orders.json', headers=SH)
        r.raise_for_status()
        fos = r.json().get('fulfillment_orders', [])

        if not fos:
            print(f"  No fulfillment orders found")
            return False

        line_items_by_fo = []
        for fo in fos:
            if fo.get('status') in ('open', 'in_progress'):
                items = [{'id': li['id'], 'quantity': li['quantity']} for li in fo.get('line_items', [])]
                if items:
                    line_items_by_fo.append({
                        'fulfillment_order_id': fo['id'],
                        'fulfillment_order_line_items': items
                    })

        if not line_items_by_fo:
            print(f"  No open fulfillment order line items")
            return False

        payload = {
            'fulfillment': {
                'line_items_by_fulfillment_order': line_items_by_fo,
                'tracking_info': {
                    'company': tracking_company,
                    'number': awb,
                    'url': tracking_url
                },
                'notify_customer': True
            }
        }

        r = requests.post(f'{SHOPIFY_STORE}/admin/api/{SHOPIFY_API}/fulfillments.json', headers=SH, json=payload)
        if r.status_code in (200, 201):
            print(f"  Fulfillment created on Shopify")
            return True
        else:
            print(f"  Failed to create fulfillment: {r.status_code} - {r.text[:300]}")
            return False

# ============================================================
# MAIN PROCESSING
# ============================================================

for order_info in ORDERS:
    order_number = order_info['number']
    item_codes = order_info['items']

    print(f"\n{'='*60}")
    print(f"PROCESSING ORDER: {order_number}")
    print(f"{'='*60}")

    result = {
        'order': order_number,
        'customer': '',
        'so': '',
        'dn': '',
        'awb': '',
        'courier': '',
        'shopify_sync': False,
        'error': ''
    }

    try:
        # Step 0: Get Shopify order
        shopify_order, payment_type, cod_amount = get_shopify_order(order_number)
        shipping_addr = shopify_order.get('shipping_address', {})
        customer_name = shipping_addr.get('name', '') or f"{shopify_order.get('customer', {}).get('first_name', '')} {shopify_order.get('customer', {}).get('last_name', '')}".strip()
        email = shopify_order.get('email', '') or shopify_order.get('contact_email', '') or 'noreply@solara.in'
        result['customer'] = customer_name

        # Check pincode serviceability
        pincode = shipping_addr.get('zip', '')
        if not check_pincode_serviceability(pincode, payment_type, cod_amount):
            result['error'] = f'Pincode {pincode} NOT serviceable'
            results.append(result)
            print(f"\n  SKIPPING {order_number} - pincode not serviceable!")
            continue

        # Step 1: Customer
        customer_id = find_or_create_customer(customer_name)

        # Step 2: Address
        addr_name = create_address(customer_id, customer_name, shipping_addr, order_number, email)

        # Step 3: Stock
        stock_entries = check_and_fix_stock(item_codes)

        # Step 4: Sales Order
        so_name = create_sales_order(customer_id, addr_name, order_number, shopify_order, item_codes, payment_type, cod_amount)
        result['so'] = so_name

        # Step 5: Delivery Note
        shopify_order_id = str(shopify_order['id'])
        dn_name = create_delivery_note(so_name, addr_name, payment_type, cod_amount, shopify_order_id, order_number)
        result['dn'] = dn_name

        # Step 6: Check auto-AWB
        awb, courier = check_awb(dn_name)

        # Step 7: Manual Clickpost if needed
        if not awb:
            awb, courier = manual_clickpost(so_name, dn_name, customer_name,
                shipping_addr.get('phone', ''), shipping_addr,
                payment_type, cod_amount, shopify_order['total_price'])

        result['awb'] = awb or ''
        result['courier'] = courier or ''

        # Step 8: Shopify sync
        if awb:
            synced = sync_shopify_fulfillment(shopify_order, awb, courier)
            result['shopify_sync'] = synced
        else:
            print(f"\n  No AWB obtained, skipping Shopify sync")

    except Exception as e:
        result['error'] = str(e)
        print(f"\n  ERROR processing {order_number}: {e}")
        traceback.print_exc()

    results.append(result)

# ============================================================
# SUMMARY
# ============================================================
print(f"\n\n{'='*100}")
print("FINAL SUMMARY")
print(f"{'='*100}")
print(f"{'Order':<15} {'Customer':<25} {'SO':<18} {'DN':<18} {'AWB':<20} {'Courier':<12} {'Shopify':<10} {'Error'}")
print(f"{'-'*15} {'-'*25} {'-'*18} {'-'*18} {'-'*20} {'-'*12} {'-'*10} {'-'*20}")
for r in results:
    shopify_str = 'OK' if r['shopify_sync'] else 'FAIL'
    print(f"{r['order']:<15} {r['customer'][:24]:<25} {r['so']:<18} {r['dn']:<18} {r['awb']:<20} {r['courier']:<12} {shopify_str:<10} {r.get('error', '')}")
print(f"{'='*100}")
