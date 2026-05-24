import requests, json, time, sys
from dotenv import dotenv_values

env = dotenv_values('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
s = requests.Session()
s.headers.update({
    'Authorization': f'token {env["ERPNEXT_API_KEY"]}:{env["ERPNEXT_API_SECRET"]}',
    'Content-Type': 'application/json'
})
BASE = env['ERPNEXT_URL']

# All 285 SOs that need DNs (excluding the one we just did: SHP27-00671)
# Re-fetch the full list from Atlas
orders = """SOL1194557 SOL1194555 SOL1194554 SOL1194553 SOL1194551 SOL1194549 SOL1194548 SOL1194546 SOL1194544 SOL1194543
SOL1194542 SOL1194541 SOL1194539 SOL1194537 SOL1194536 SOL1194535 SOL1194534 SOL1194533 SOL1194530 SOL1194529
SOL1194528 SOL1194527 SOL1194525 SOL1194523 SOL1194522 SOL1194519 SOL1194517 SOL1194516 SOL1194515 SOL1194514
SOL1194513 SOL1194512 SOL1194511 SOL1194510 SOL1194509 SOL1194508 SOL1194507 SOL1194506 SOL1194505 SOL1194502
SOL1194501 SOL1194500 SOL1194498 SOL1194496 SOL1194495 SOL1194493 SOL1194491 SOL1194490 SOL1194489 SOL1194488
SOL1194487 SOL1194483 SOL1194482 SOL1194477 SOL1194476 SOL1194475 SOL1194474 SOL1194473 SOL1194472 SOL1194471
SOL1194470 SOL1194469 SOL1194467 SOL1194466 SOL1194465 SOL1194464 SOL1194463 SOL1194461 SOL1194460 SOL1194457
SOL1194456 SOL1194455 SOL1194454 SOL1194453 SOL1194451 SOL1194450 SOL1194449 SOL1194447 SOL1194446 SOL1194445
SOL1194443 SOL1194442 SOL1194440 SOL1194439 SOL1194437 SOL1194436 SOL1194434 SOL1194433 SOL1194431 SOL1194429
SOL1194426 SOL1194424 SOL1194423 SOL1194420 SOL1194419 SOL1194418 SOL1194415 SOL1194413 SOL1194412 SOL1194411
SOL1194410 SOL1194407 SOL1194406 SOL1194404 SOL1194401 SOL1194399 SOL1194397 SOL1194396 SOL1194395 SOL1194393
SOL1194392 SOL1194390 SOL1194388 SOL1194385 SOL1194384 SOL1194382 SOL1194381 SOL1194379 SOL1194378 SOL1194376
SOL1194375 SOL1194374 SOL1194373 SOL1194372 SOL1194369 SOL1194367 SOL1194366 SOL1194365 SOL1194364 SOL1194363
SOL1194360 SOL1194359 SOL1194356 SOL1194355 SOL1194353 SOL1194350 SOL1194346 SOL1194345 SOL1194343 SOL1194342
SOL1194341 SOL1194340 SOL1194338 SOL1194336 SOL1194335 SOL1194334 SOL1194333 SOL1194330 SOL1194329 SOL1194328
SOL1194326 SOL1194325 SOL1194324 SOL1194323 SOL1194321 SOL1194320 SOL1194319 SOL1194317 SOL1194314 SOL1194313
SOL1194312 SOL1194309 SOL1194308 SOL1194307 SOL1194306 SOL1194305 SOL1194304 SOL1194303 SOL1194302 SOL1194298
SOL1194296 SOL1194295 SOL1194293 SOL1194290 SOL1194289 SOL1194288 SOL1194287 SOL1194286 SOL1194285 SOL1194284
SOL1194281 SOL1194280 SOL1194279 SOL1194278 SOL1194276 SOL1194275 SOL1194272 SOL1194271 SOL1194269 SOL1194268
SOL1194267 SOL1194266 SOL1194265 SOL1194264 SOL1194263 SOL1194262 SOL1194261 SOL1194258 SOL1194257 SOL1194256
SOL1194255 SOL1194254 SOL1194253 SOL1194250 SOL1194249 SOL1194248 SOL1194247 SOL1194245 SOL1194244 SOL1194243
SOL1194240 SOL1194239 SOL1194237 SOL1194236 SOL1194235 SOL1194234 SOL1194233 SOL1194231 SOL1194229 SOL1194228
SOL1194226 SOL1194225 SOL1194224 SOL1194221 SOL1194218 SOL1194217 SOL1194213 SOL1194212 SOL1194211 SOL1194210
SOL1194206 SOL1194204 SOL1194202 SOL1194201 SOL1194197 SOL1194196 SOL1194193 SOL1194192 SOL1194190 SOL1194189
SOL1194188 SOL1194187 SOL1194186 SOL1194184 SOL1194183 SOL1194182 SOL1194181 SOL1194180 SOL1194179 SOL1194178
SOL1194177 SOL1194176 SOL1194175 SOL1194174 SOL1194173 SOL1194172 SOL1194168 SOL1194167 SOL1194166 SOL1194164
SOL1194163 SOL1194161 SOL1194160 SOL1194159 SOL1194158 SOL1194157 SOL1194155 SOL1194154 SOL1194152 SOL1194151
SOL1194150 SOL1194149 SOL1194148 SOL1194147 SOL1194146 SOL1194145 SOL1194144 SOL1194143 SOL1194142 SOL1194141
SOL1194140 SOL1194139 SOL1194138 SOL1194137 SOL1194136 SOL1194135 SOL1194134 SOL1194133 SOL1194131 SOL1194130
SOL1194128 SOL1194126 SOL1194124 SOL1194123 SOL1194122 SOL1194114 SOL1194106 SOL1194057 SOL1194052""".split()

# Step 1: Get SO names for all orders (batch)
print(f"Step 1: Looking up {len(orders)} Shopify orders...")
so_map = {}  # shopify_order -> so_name
batch_size = 20
for i in range(0, len(orders), batch_size):
    batch = orders[i:i+batch_size]
    r = s.get(f'{BASE}/api/resource/Sales Order', params={
        'filters': json.dumps([['custom_shopify_order_number','in',batch]]),
        'fields': json.dumps(['name','status','docstatus','custom_shopify_order_number']),
        'limit_page_length': batch_size
    })
    for so in r.json().get('data', []):
        # Only process submitted SOs with "To Deliver" status
        if so['docstatus'] == 1 and 'To Deliver' in so.get('status', ''):
            so_map[so['custom_shopify_order_number']] = so['name']
    time.sleep(0.2)

print(f"Found {len(so_map)} submitted SOs ready for DN creation")

# Step 2: Check which SOs already have DNs
print("Step 2: Checking for existing DNs...")
so_with_dn = set()
for so_name in so_map.values():
    r = s.get(f'{BASE}/api/resource/Delivery Note', params={
        'filters': json.dumps([['Delivery Note Item','against_sales_order','=',so_name],['docstatus','in',[0,1]]]),
        'fields': json.dumps(['name']),
        'limit_page_length': 1
    })
    if r.json().get('data', []):
        so_with_dn.add(so_name)
    time.sleep(0.1)

# Filter out SOs that already have DNs
so_to_process = {k: v for k, v in so_map.items() if v not in so_with_dn}
print(f"SOs needing DN: {len(so_to_process)} (skipping {len(so_with_dn)} with existing DN)")

# Step 3: Create DN for each SO, save, and submit
results = {
    'success': [],      # (order_id, so_name, dn_name, awb)
    'created_no_awb': [],  # (order_id, so_name, dn_name)
    'submit_failed': [],   # (order_id, so_name, dn_name, error)
    'create_failed': [],   # (order_id, so_name, error)
    'skipped': [],         # (order_id, reason)
}

total = len(so_to_process)
print(f"\nStep 3: Creating and submitting {total} DNs...\n")

for idx, (order_id, so_name) in enumerate(so_to_process.items(), 1):
    sys.stdout.write(f"[{idx}/{total}] {order_id} ({so_name})... ")
    sys.stdout.flush()

    try:
        # Create DN from SO
        r = s.post(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note', json={
            'source_name': so_name
        })
        if r.status_code != 200:
            err = r.text[:200]
            print(f"MAKE FAILED: {err}")
            results['create_failed'].append((order_id, so_name, err))
            time.sleep(0.5)
            continue

        dn_data = r.json().get('message', {})

        # Save DN
        r2 = s.post(f'{BASE}/api/resource/Delivery Note', json=dn_data)
        if r2.status_code != 200:
            err = r2.text[:200]
            print(f"SAVE FAILED: {err}")
            results['create_failed'].append((order_id, so_name, err))
            time.sleep(0.5)
            continue

        dn_name = r2.json()['data']['name']

        # Submit DN
        r3 = s.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', json={'docstatus': 1})
        if r3.status_code != 200:
            err = r3.text[:200]
            print(f"SUBMIT FAILED ({dn_name}): {err}")
            results['submit_failed'].append((order_id, so_name, dn_name, err))
            time.sleep(0.5)
            continue

        # Check AWB (brief wait)
        time.sleep(1)
        r4 = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
            'fields': json.dumps(['shipment_status','awb_number'])
        })
        d = r4.json()['data']
        awb = d.get('awb_number', '') or ''
        ship = d.get('shipment_status', '') or ''

        if awb:
            print(f"OK -> {dn_name} | AWB: {awb}")
            results['success'].append((order_id, so_name, dn_name, awb))
        else:
            print(f"OK -> {dn_name} | shipment: {ship} (no AWB yet)")
            results['created_no_awb'].append((order_id, so_name, dn_name))

    except Exception as e:
        print(f"EXCEPTION: {e}")
        results['create_failed'].append((order_id, so_name, str(e)))

    # Rate limit - every 10 orders, pause a bit more
    if idx % 10 == 0:
        time.sleep(2)
    else:
        time.sleep(0.5)

# Step 4: Re-check pending AWBs
if results['created_no_awb']:
    print(f"\nStep 4: Re-checking {len(results['created_no_awb'])} DNs for AWB (waiting 15s)...")
    time.sleep(15)
    still_pending = []
    for order_id, so_name, dn_name in results['created_no_awb']:
        r = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
            'fields': json.dumps(['shipment_status','awb_number'])
        })
        d = r.json()['data']
        awb = d.get('awb_number', '') or ''
        if awb:
            results['success'].append((order_id, so_name, dn_name, awb))
        else:
            still_pending.append((order_id, so_name, dn_name, d.get('shipment_status','')))
        time.sleep(0.1)
    results['created_no_awb'] = still_pending

# Summary
print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"Total SOs processed:    {total}")
print(f"DN created + AWB:       {len(results['success'])}")
print(f"DN created, no AWB:     {len(results['created_no_awb'])}")
print(f"Submit failed:          {len(results['submit_failed'])}")
print(f"Create failed:          {len(results['create_failed'])}")

if results['submit_failed']:
    print("\nSubmit failures:")
    for oid, so, dn, err in results['submit_failed']:
        print(f"  {oid} ({so}) -> {dn}: {err[:100]}")

if results['create_failed']:
    print("\nCreate failures:")
    for oid, so, err in results['create_failed']:
        print(f"  {oid} ({so}): {err[:100]}")

if results['created_no_awb']:
    print("\nDNs without AWB (check manually):")
    for oid, so, dn, ship in results['created_no_awb']:
        print(f"  {oid} ({so}) -> {dn} | shipment: {ship}")

print(f"\nDone!")
