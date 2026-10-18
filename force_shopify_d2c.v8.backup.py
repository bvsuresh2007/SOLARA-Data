# v8 - Fix: Connector does not set address fields on SO
if doc.shopify_order_id:
    state_map = {"Andhra Pradesh": "37", "Arunachal Pradesh": "12", "Assam": "18", "Bihar": "10", "Chhattisgarh": "22", "Goa": "30", "Gujarat": "24", "Haryana": "06", "Himachal Pradesh": "02", "Jharkhand": "20", "Karnataka": "29", "Kerala": "32", "Madhya Pradesh": "23", "Maharashtra": "27", "Manipur": "14", "Meghalaya": "17", "Mizoram": "15", "Nagaland": "13", "Odisha": "21", "Punjab": "03", "Rajasthan": "08", "Sikkim": "11", "Tamil Nadu": "33", "Telangana": "36", "Tripura": "16", "Uttar Pradesh": "09", "Uttarakhand": "05", "West Bengal": "19", "Andaman and Nicobar Islands": "35", "Chandigarh": "04", "Dadra and Nagar Haveli and Daman and Diu": "26", "Delhi": "07", "Jammu and Kashmir": "01", "Ladakh": "38", "Lakshadweep": "31", "Puducherry": "34"}
    ship_state_code = ""
    ship_state_name = ""
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
