import requests, json, time
from dotenv import dotenv_values

env = dotenv_values('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
s = requests.Session()
s.headers.update({
    'Authorization': f'token {env["ERPNEXT_API_KEY"]}:{env["ERPNEXT_API_SECRET"]}',
    'Content-Type': 'application/json'
})
BASE = env['ERPNEXT_URL']
TIMEOUT = 30

orders = """SOL1194558 SOL1194556 SOL1194552 SOL1194550 SOL1194545 SOL1194540 SOL1194494 SOL1194481 SOL1194480 SOL1194459
SOL1194432 SOL1194430 SOL1194416 SOL1194409 SOL1194405 SOL1194394 SOL1194389 SOL1194386 SOL1194368 SOL1194361
SOL1194354 SOL1194352 SOL1194351 SOL1194348 SOL1194347 SOL1194327 SOL1194315 SOL1194291 SOL1194246 SOL1194242
SOL1194222 SOL1194215 SOL1194214 SOL1194209 SOL1194208 SOL1194207 SOL1194205 SOL1194203 SOL1194199 SOL1194198
SOL1194195 SOL1194194 SOL1194185 SOL1194171 SOL1194170 SOL1194169 SOL1194162 SOL1194156 SOL1194127""".split()

print(f"Step 1: Looking up {len(orders)} orders...", flush=True)

# Batch lookup SOs
all_sos = {}
for i in range(0, len(orders), 20):
    batch = orders[i:i+20]
    r = s.get(f"{BASE}/api/resource/Sales Order", params={
        "filters": json.dumps([["custom_shopify_order_number","in",batch]]),
        "fields": json.dumps(["name","status","docstatus","custom_shopify_order_number","shopify_order_id"]),
        "limit_page_length": 100
    }, timeout=TIMEOUT)
    for so in r.json().get("data", []):
        oid = so["custom_shopify_order_number"]
        if oid not in all_sos:
            all_sos[oid] = []
        all_sos[oid].append(so)
    time.sleep(0.2)

# Pick best SO per order (submitted preferred)
so_map = {}
for oid, so_list in all_sos.items():
    priority = {1: 3, 0: 2, 2: 1}
    best = None
    for so in so_list:
        if best is None:
            best = so
        elif priority.get(so["docstatus"], 0) > priority.get(best["docstatus"], 0):
            best = so
        elif so["docstatus"] == best["docstatus"] and so["name"] > best["name"]:
            best = so
    so_map[oid] = best

print(f"Found {len(so_map)} SOs", flush=True)

# Process each order
success = []
failed = []
no_awb = []

print(f"\nStep 2: Creating DNs...\n", flush=True)

for idx, oid in enumerate(orders, 1):
    so = so_map.get(oid)
    if not so:
        print(f"[{idx}/49] {oid} - NO SO FOUND", flush=True)
        failed.append((oid, "", "No SO"))
        continue

    so_name = so["name"]
    shopify_id = so.get("shopify_order_id", "") or ""

    # If SO not submitted, skip
    if so["docstatus"] != 1:
        print(f"[{idx}/49] {oid} | {so_name} - SO not submitted (docstatus={so['docstatus']})", flush=True)
        failed.append((oid, so_name, f"SO docstatus={so['docstatus']}"))
        continue

    print(f"[{idx}/49] {oid} | {so_name}... ", end="", flush=True)

    try:
        # Create DN from SO
        r1 = s.post(f"{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note",
                     json={"source_name": so_name}, timeout=TIMEOUT)
        if r1.status_code != 200:
            print(f"make_dn FAILED: {r1.status_code}", flush=True)
            failed.append((oid, so_name, f"make_dn: {r1.status_code}"))
            time.sleep(1)
            continue

        dn_data = r1.json().get("message", {})

        # Set shopify fields for Clickpost
        if shopify_id:
            dn_data["shopify_order_id"] = shopify_id
            dn_data["shopify_order_number"] = oid

        # Save DN
        r2 = s.post(f"{BASE}/api/resource/Delivery Note", json=dn_data, timeout=TIMEOUT)
        if r2.status_code != 200:
            err = r2.text[:150]
            print(f"save FAILED: {err}", flush=True)
            # Check server-side draft
            rc = s.get(f"{BASE}/api/resource/Delivery Note", params={
                "filters": json.dumps([["Delivery Note Item","against_sales_order","=",so_name],["docstatus","=",0]]),
                "fields": json.dumps(["name"]),
                "limit_page_length": 1
            })
            drafts = rc.json().get("data", [])
            if drafts:
                dn_name = drafts[0]["name"]
                if shopify_id:
                    s.put(f"{BASE}/api/resource/Delivery Note/{dn_name}",
                          json={"shopify_order_id": shopify_id, "shopify_order_number": oid})
                r3 = s.put(f"{BASE}/api/resource/Delivery Note/{dn_name}", json={"docstatus": 1}, timeout=TIMEOUT)
                if r3.status_code == 200:
                    time.sleep(2)
                    r4 = s.get(f"{BASE}/api/resource/Delivery Note/{dn_name}", params={
                        "fields": json.dumps(["shipment_status","awb_number","courier_partner"])
                    })
                    d4 = r4.json()["data"]
                    awb = d4.get("awb_number", "") or ""
                    if awb:
                        print(f"-> {dn_name} | AWB: {awb} | {d4.get('courier_partner','')}", flush=True)
                        success.append((oid, so_name, dn_name, awb))
                    else:
                        print(f"-> {dn_name} | {d4.get('shipment_status','')} (no AWB)", flush=True)
                        no_awb.append((oid, so_name, dn_name, d4.get("shipment_status", "")))
                else:
                    print(f"submit draft FAILED: {r3.text[:120]}", flush=True)
                    failed.append((oid, so_name, f"submit draft {dn_name}: {r3.text[:80]}"))
            else:
                failed.append((oid, so_name, f"save: {err[:80]}"))
            time.sleep(1)
            continue

        dn_name = r2.json()["data"]["name"]

        # Submit DN
        r3 = s.put(f"{BASE}/api/resource/Delivery Note/{dn_name}", json={"docstatus": 1}, timeout=TIMEOUT)
        if r3.status_code != 200:
            err = r3.text[:150]
            print(f"-> {dn_name} submit FAILED: {err}", flush=True)
            failed.append((oid, so_name, f"submit {dn_name}: {err[:80]}"))
            time.sleep(1)
            continue

        # Check AWB
        time.sleep(2)
        r4 = s.get(f"{BASE}/api/resource/Delivery Note/{dn_name}", params={
            "fields": json.dumps(["shipment_status","awb_number","courier_partner"])
        })
        d4 = r4.json()["data"]
        awb = d4.get("awb_number", "") or ""
        ship = d4.get("shipment_status", "") or ""
        courier = d4.get("courier_partner", "") or ""

        if awb:
            print(f"-> {dn_name} | AWB: {awb} | {courier}", flush=True)
            success.append((oid, so_name, dn_name, awb))
        else:
            print(f"-> {dn_name} | {ship} (no AWB)", flush=True)
            no_awb.append((oid, so_name, dn_name, ship))

    except requests.exceptions.Timeout:
        print("TIMEOUT", flush=True)
        failed.append((oid, so_name, "timeout"))
        time.sleep(2)
    except Exception as e:
        print(f"ERR: {e}", flush=True)
        failed.append((oid, so_name, str(e)[:100]))
        time.sleep(1)

    if idx % 10 == 0:
        time.sleep(2)
    else:
        time.sleep(0.5)

# Re-check pending AWBs
if no_awb:
    print(f"\nStep 3: Re-checking {len(no_awb)} pending AWBs (15s wait)...", flush=True)
    time.sleep(15)
    still_pending = []
    for oid, so_name, dn_name, _ in no_awb:
        try:
            r = s.get(f"{BASE}/api/resource/Delivery Note/{dn_name}", params={
                "fields": json.dumps(["shipment_status","awb_number","courier_partner"])
            })
            d = r.json()["data"]
            awb = d.get("awb_number", "") or ""
            if awb:
                print(f"  {oid} -> {dn_name} | AWB: {awb}", flush=True)
                success.append((oid, so_name, dn_name, awb))
            else:
                still_pending.append((oid, so_name, dn_name, d.get("shipment_status", "")))
        except:
            still_pending.append((oid, so_name, dn_name, "?"))
    no_awb = still_pending

# Summary
print(f"\n{'='*70}", flush=True)
print(f"DONE — 49 Orders", flush=True)
print(f"{'='*70}", flush=True)
print(f"Success (AWB):  {len(success)}", flush=True)
print(f"No AWB:         {len(no_awb)}", flush=True)
print(f"Failed:         {len(failed)}", flush=True)

if failed:
    print(f"\nFailures:", flush=True)
    for oid, so, err in failed:
        print(f"  {oid} ({so}): {err}", flush=True)

if no_awb:
    print(f"\nNo AWB:", flush=True)
    for oid, so, dn, ship in no_awb:
        print(f"  {oid} -> {dn} ({ship})", flush=True)
