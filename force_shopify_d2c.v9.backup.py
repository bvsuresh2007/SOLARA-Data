# v10 - Adds PPCOD cod_amount auto-calculation from Shopify transactions
# v9 additions preserved: Source 0 (Shopify shipping_address as single source of truth)
# NEW in v10: After Source 0 Shopify API call, also fetches transactions to calculate
#   custom_cod_amount for PPCOD orders (fixes silent bug where ecommerce_integrations
#   sets custom_order_type=PPCOD but leaves custom_cod_amount=0)
if doc.shopify_order_id:
    state_map = {"Andhra Pradesh": "37", "Arunachal Pradesh": "12", "Assam": "18", "Bihar": "10", "Chhattisgarh": "22", "Goa": "30", "Gujarat": "24", "Haryana": "06", "Himachal Pradesh": "02", "Jharkhand": "20", "Karnataka": "29", "Kerala": "32", "Madhya Pradesh": "23", "Maharashtra": "27", "Manipur": "14", "Meghalaya": "17", "Mizoram": "15", "Nagaland": "13", "Odisha": "21", "Punjab": "03", "Rajasthan": "08", "Sikkim": "11", "Tamil Nadu": "33", "Telangana": "36", "Tripura": "16", "Uttar Pradesh": "09", "Uttarakhand": "05", "West Bengal": "19", "Andaman and Nicobar Islands": "35", "Chandigarh": "04", "Dadra and Nagar Haveli and Daman and Diu": "26", "Delhi": "07", "Jammu and Kashmir": "01", "Ladakh": "38", "Lakshadweep": "31", "Puducherry": "34"}
    ship_state_code = ""
    ship_state_name = ""

    # ==================== Source 0 (v9) + PPCOD cod_amount fix (v10) ====================
    addr_already_synced = False
    try:
        addr_already_synced = bool(getattr(doc.flags, "addr_synced_from_shopify", False))
    except Exception:
        addr_already_synced = False

    if not addr_already_synced and doc.customer:
        try:
            shop = frappe.get_doc("Shopify Setting")
            base_url = "https://" + shop.shopify_url + "/admin/api/2024-01"
            api_headers = {"X-Shopify-Access-Token": shop.get_password("password")}
            url = base_url + "/orders/" + str(doc.shopify_order_id) + ".json?fields=shipping_address,name,total_price,financial_status,payment_gateway_names"
            resp = frappe.make_get_request(url, headers=api_headers)
            order_obj = resp.get("order") or {}
            sa_shopify = order_obj.get("shipping_address") or {}
            sol_num_raw = order_obj.get("name") or doc.shopify_order_number or ""
            sol_clean = sol_num_raw.replace("#", "")
            sa_zip = str(sa_shopify.get("zip") or "").strip()

            if sa_zip and sol_clean:
                addr_title_v9 = doc.customer + "-" + sol_clean
                target_addr_name = frappe.db.get_value("Address", {"address_title": addr_title_v9, "address_type": "Shipping"}, "name")
                if not target_addr_name:
                    new_addr = frappe.new_doc("Address")
                    new_addr.address_title = addr_title_v9
                    new_addr.address_type = "Shipping"
                    new_addr.address_line1 = (sa_shopify.get("address1") or "NA")[:240]
                    new_addr.address_line2 = (sa_shopify.get("address2") or "")[:240]
                    new_addr.city = sa_shopify.get("city") or ""
                    new_addr.state = sa_shopify.get("province") or ""
                    new_addr.pincode = sa_zip
                    new_addr.country = "India"
                    new_addr.phone = sa_shopify.get("phone") or ""
                    new_addr.gst_category = "Unregistered"
                    addr_state_v9 = new_addr.state
                    if addr_state_v9 and addr_state_v9 in state_map:
                        new_addr.gst_state_number = state_map[addr_state_v9]
                        new_addr.gst_state = addr_state_v9
                    new_addr.append("links", {"link_doctype": "Customer", "link_name": doc.customer})
                    new_addr.flags.ignore_permissions = True
                    new_addr.insert()
                    target_addr_name = new_addr.name
                doc.shipping_address_name = target_addr_name
                doc.customer_address = target_addr_name
                doc.flags.addr_synced_from_shopify = True

            # ==================== v10: PPCOD cod_amount auto-calculation ====================
            # If order_type is PPCOD but cod_amount is 0, calculate from Shopify transactions
            order_type_val = doc.custom_order_type or ""
            cod_amt_val = float(doc.custom_cod_amount or 0)
            shopify_total = float(order_obj.get("total_price") or 0)
            shopify_gws = order_obj.get("payment_gateway_names") or []
            shopify_fin = order_obj.get("financial_status") or ""
            gw_str = ",".join(shopify_gws).lower()

            # Detect PPCOD: gateway contains ppcod/gokwik + partially_paid
            is_ppcod_shopify = ("ppcod" in gw_str) and shopify_fin == "partially_paid"

            # Auto-detect order_type if not set by connector
            if not order_type_val and is_ppcod_shopify:
                doc.custom_order_type = "PPCOD"
                order_type_val = "PPCOD"

            # Calculate cod_amount for PPCOD orders where it is 0
            if order_type_val == "PPCOD" and cod_amt_val < 1 and shopify_total > 0:
                try:
                    txn_url = base_url + "/orders/" + str(doc.shopify_order_id) + "/transactions.json"
                    txn_resp = frappe.make_get_request(txn_url, headers=api_headers)
                    txns = txn_resp.get("transactions") or []
                    captured = 0
                    for t in txns:
                        t_kind = t.get("kind") or ""
                        t_status = t.get("status") or ""
                        t_amt = float(t.get("amount") or 0)
                        if t_kind == "capture" and t_status == "success":
                            captured = captured + t_amt
                    if captured == 0:
                        for t in txns:
                            t_kind = t.get("kind") or ""
                            t_status = t.get("status") or ""
                            t_amt = float(t.get("amount") or 0)
                            if t_kind == "sale" and t_status == "success":
                                captured = captured + t_amt
                    if captured > 0 and captured < shopify_total:
                        doc.custom_cod_amount = round(shopify_total - captured, 2)
                        doc.custom_prepaid_amount = round(captured, 2)
                    elif captured == 0:
                        doc.custom_cod_amount = shopify_total
                        doc.custom_prepaid_amount = 0
                except Exception as e_v10_txn:
                    frappe.log_error("v10 PPCOD txn fetch error for " + str(doc.shopify_order_id) + ": " + str(e_v10_txn), "Force D2C PPCOD Calc Error")

            # Also handle COD detection (fin=pending, no gateway or cash-on-delivery)
            if not order_type_val and shopify_fin == "pending" and shopify_total > 0:
                doc.custom_order_type = "COD"
                doc.custom_cod_amount = shopify_total
                doc.custom_prepaid_amount = 0
            # ==================== End v10 PPCOD fix ====================

        except Exception as e_v9:
            frappe.log_error("Shopify v9 address sync error for " + str(doc.shopify_order_id) + ": " + str(e_v9), "Force D2C Address Sync Error")
    # ==================== End Source 0 ====================

    # Source 1: Shipping address on SO
    if doc.shipping_address_name:
        try:
            sa = frappe.get_doc("Address", doc.shipping_address_name)
            ship_state_code = sa.gst_state_number or ""
            ship_state_name = sa.state or ""
            if not ship_state_code and ship_state_name:
                ship_state_code = state_map.get(ship_state_name, "")
        except Exception:
            pass
    # Source 2: Customer address
    if not ship_state_code and doc.customer_address:
        try:
            ca = frappe.get_doc("Address", doc.customer_address)
            ship_state_code = ca.gst_state_number or ""
            ship_state_name = ca.state or ""
            if not ship_state_code and ship_state_name:
                ship_state_code = state_map.get(ship_state_name, "")
        except Exception:
            pass
    # Source 3: DB lookup customer addresses
    if not ship_state_code and doc.customer:
        try:
            addrs = frappe.get_all("Dynamic Link", filters={"link_doctype": "Customer", "link_name": doc.customer, "parenttype": "Address"}, fields=["parent"], limit_page_length=1)
            if addrs:
                addr = frappe.get_doc("Address", addrs[0].parent)
                ship_state_code = addr.gst_state_number or ""
                ship_state_name = addr.state or ""
                if not ship_state_code and ship_state_name:
                    ship_state_code = state_map.get(ship_state_name, "")
                if not doc.shipping_address_name:
                    doc.shipping_address_name = addrs[0].parent
                if not doc.customer_address:
                    doc.customer_address = addrs[0].parent
        except Exception:
            pass
    # Source 4: Parse from display text
    if not ship_state_code and doc.shipping_address:
        for sn, sc in state_map.items():
            if sn in (doc.shipping_address or ""):
                ship_state_code = sc
                ship_state_name = sn
                break
    # Source 5: Parse from Shopify order JSON flag
    if not ship_state_code:
        try:
            import json as json_lib
            oj = getattr(doc.flags, "shopify_order_json", "") or ""
            if oj:
                sd = json_lib.loads(oj)
                sa2 = sd.get("shipping_address", {}) or {}
                prov = sa2.get("province", "") or ""
                if prov:
                    ship_state_code = state_map.get(prov, "")
                    ship_state_name = prov
        except Exception:
            pass
    # Set place_of_supply
    if ship_state_code and ship_state_name:
        doc.place_of_supply = ship_state_code + "-" + ship_state_name
    # Company setup
    doc.company_address = "Win The Buy Box Private Limited-Billing"
    cg = frappe.db.get_value("Address", doc.company_address, "gstin") or "36AADCW0665P1ZS"
    doc.company_gstin = cg
    # Interstate check
    cs = (doc.company_gstin or "")[:2]
    ss = ship_state_code or ""
    if not ss:
        is_inter = True
    else:
        is_inter = cs != ss
    # Apply tax template
    ttn = "GST 18% Interstate - WTBBPL" if is_inter else "GST 18% Intrastate - WTBBPL"
    doc.taxes_and_charges = ttn
    doc.taxes = []
    td = frappe.get_doc("Sales Taxes and Charges Template", ttn)
    for tr in td.taxes:
        doc.append("taxes", {"charge_type": tr.charge_type, "account_head": tr.account_head, "description": tr.description, "rate": tr.rate, "included_in_print_rate": 1, "cost_center": tr.cost_center})
    # Item GST
    for item in doc.items:
        if not item.item_tax_template and item.item_code:
            its = frappe.get_all("Item Tax", filters={"parent": item.item_code, "parenttype": "Item"}, fields=["item_tax_template"], limit_page_length=1)
            if its:
                item.item_tax_template = its[0].item_tax_template
        if item.item_tax_template:
            item.gst_treatment = "Taxable"
            ttd = frappe.get_all("Item Tax Template Detail", filters={"parent": item.item_tax_template}, fields=["tax_type", "tax_rate"])
            if ttd:
                parts = ["\"" + str(t.tax_type) + "\": " + str(t.tax_rate) for t in ttd]
                item.item_tax_rate = "{" + ", ".join(parts) + "}"
        else:
            item.gst_treatment = "Nil-Rated"
            if is_inter:
                item.item_tax_rate = "{\"Output Tax IGST - WTBBPL\": 0}"
            else:
                item.item_tax_rate = "{\"Output Tax CGST - WTBBPL\": 0, \"Output Tax SGST - WTBBPL\": 0}"
    doc.gst_category = "Unregistered"
