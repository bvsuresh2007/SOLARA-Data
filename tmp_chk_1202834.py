import os, requests, json
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

# Get Shopify token
r = requests.post(f'{BASE}/api/method/frappe.client.get_password',
                   headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
token = r.json().get('message', '')
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}

dn = 'SHPDN27-10786'
so = 'SHP27-09130'

# DN details
r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=30)
d = r_dn.json().get('data', {})
print(f"DN: {dn} | ds={d.get('docstatus')} | customer={d.get('customer_name','')}")
print(f"  shipping_address_name: {d.get('shipping_address_name','')}")
print(f"  shopify_order_id: {d.get('shopify_order_id','')}")
print(f"  shopify_order_number: {d.get('shopify_order_number','')}")

# Atlas address
addr_name = d.get('shipping_address_name', '')
if addr_name:
    r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=30)
    ad = r_a.json().get('data', {})
    print(f"\nAtlas Address ({addr_name}):")
    print(f"  line1: {ad.get('address_line1','')}")
    print(f"  line2: {ad.get('address_line2','')}")
    print(f"  city: {ad.get('city','')}")
    print(f"  state: {ad.get('state','')}")
    print(f"  pincode: {ad.get('pincode','')}")
    print(f"  phone: {ad.get('phone','')}")

# SO details
r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so}', headers=H, timeout=30)
so_d = r_so.json().get('data', {})
so_addr = so_d.get('shipping_address_name', '')
print(f"\nSO: {so} | shipping_address: {so_addr}")
print(f"  shopify_order_id: {so_d.get('shopify_order_id','')}")

# Shopify order
shopify_oid = so_d.get('shopify_order_id', '') or d.get('shopify_order_id', '')
if shopify_oid:
    r_shop = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
    order = r_shop.json().get('order', {})
    sa = order.get('shipping_address', {})
    print(f"\nShopify Shipping Address:")
    print(f"  name: {sa.get('first_name','')} {sa.get('last_name','')}")
    print(f"  address1: {sa.get('address1','')}")
    print(f"  address2: {sa.get('address2','')}")
    print(f"  city: {sa.get('city','')}")
    print(f"  province: {sa.get('province','')}")
    print(f"  zip: {sa.get('zip','')}")
    print(f"  phone: {sa.get('phone','')}")

# Check error log
r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
    params={'filters': json.dumps([['error','like',f'%{dn}%']]),
            'fields': json.dumps(['error','creation']),
            'order_by': 'creation desc', 'limit_page_length': 2}, timeout=30)
errs = r_err.json().get('data', [])
if errs:
    print(f"\nError Log:")
    for e in errs:
        err = str(e.get('error', ''))
        for line in err.split('\n'):
            if any(k in line.lower() for k in ['mismatch', 'address', 'pin', 'shopify']):
                print(f"  {line.strip()[:200]}")
