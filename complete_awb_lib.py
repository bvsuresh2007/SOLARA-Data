"""Shared lib: generate Clickpost AWB (multi-courier, physical SKUs, COD-aware) for a DN, + create Shopify fulfillment."""
import os, json, time, requests
from dotenv import load_dotenv
load_dotenv("C:/Users/accou/Documents/Projects/SOLARA-Data/.env")
H={'Authorization':f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}','Content-Type':'application/json'}
BASE="https://atlas.solara.in"
CPUSER=os.getenv("CLICKPOST_USER","solara"); CPKEY=os.getenv("CLICKPOST_KEY")
PICKUP=dict(pincode="501218",name="WIN THE BUY BOX PVT LTD",phone="9573652101",email="hydwh@solara.in",
            address="SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District",city="Hyderabad",state="Telangana")
WH_FULL="WIN THE BUY BOX PVT LTD, SY NO.68/1/E, Hamedullah Nagar, Shamshabad Mandal, Ranga Reddy District, Hyderabad, Telangana 501218"
UA={'User-Agent':'Mozilla/5.0','Content-Type':'application/json'}
S=requests.Session(); S.headers.update(H)
API='https://dev-solara.myshopify.com/admin/api/2024-01'

def G(p,t=60):
    for _ in range(5):
        try:
            r=S.get(f'{BASE}{p}',timeout=t)
            if r.status_code==200: return r.json().get('data')
        except: pass
        time.sleep(2)
    return None
def shtoken():
    for _ in range(8):
        try:
            r=S.post(f'{BASE}/api/method/frappe.client.get_password',data=json.dumps({"doctype":"Shopify Setting","name":"Shopify Setting","fieldname":"password"}),timeout=30)
            if r.status_code==200 and r.json().get('message'): return r.json()['message']
        except: pass
        time.sleep(3)
    return None

def gen_awb_for_dn(dn_name, ref=None):
    """Generate AWB on a submitted DN. Returns (awb,courier) or (None,reason)."""
    doc=G(f'/api/resource/Delivery Note/{dn_name}')
    if not doc: return None,'DN-read-fail'
    if doc.get('awb_number'): return doc['awb_number'],doc.get('courier_partner')  # already has
    son=doc.get('shopify_order_number') or doc.get('custom_shopify_order_number') or dn_name
    ref=ref or son
    # physical items
    packed=doc.get('packed_items',[]) or []
    bundle_parents=set(p.get('parent_item') for p in packed)
    phys=[{"item_code":p["item_code"],"item_name":p.get("item_name") or p["item_code"],"qty":int(p["qty"]),"rate":float(p.get('rate') or 0)} for p in packed]
    for it in doc.get('items',[]):
        if it['item_code'] not in bundle_parents:
            phys.append({"item_code":it['item_code'],"item_name":it.get('item_name') or it['item_code'],"qty":int(it['qty']),"rate":float(it.get('rate') or 0)})
    # drop non-physical lines (warranty / digital — anything not a SOL- stock SKU) from the shipping label
    phys=[x for x in phys if x['item_code'].startswith('SOL-')]
    if not phys: return None,'no-physical-sku'
    seller_gstin=doc.get('company_gstin') or "36AADCW0665P1ZS"
    items=[]; skus=[]; tw=0; hsn=""
    for x in phys:
        im=G(f'/api/resource/Item/{x["item_code"]}?fields=["weight_per_unit","gst_hsn_code"]') or {}
        wg=int(float(im.get('weight_per_unit') or 0)*1000)
        if not hsn and im.get('gst_hsn_code'): hsn=im['gst_hsn_code']
        skus.append(x['item_code'])
        e={"sku":x['item_code'],"description":x['item_name'],"quantity":x['qty'],"price":x['rate'],
           "gst_info":{"seller_gstin":seller_gstin,"taxable_value":0,"hsn_code":str(im.get('gst_hsn_code') or ''),"igst_tax_rate":0,"sgst_tax_rate":0,"cgst_tax_rate":0},"additional":{}}
        if wg>0: e["additional"]["weight"]=wg*x['qty']; tw+=wg*x['qty']
        items.append(e)
    if tw<=0:
        net=float(doc.get('total_net_weight') or 0); tw=int(net*1000) if net>0 else 800
    ic=len(items); twk=tw/1000.0
    if twk<0.5 and ic==1: bl,bb,bh,tier=20,15,10,"tier:small"
    elif twk<3: bl,bb,bh,tier=30,20,15,"tier:medium"
    elif twk<8: bl,bb,bh,tier=40,30,25,"tier:large"
    else: bl,bb,bh,tier=50,40,35,"tier:xl"
    vol=int(((bl*bb*bh)/5000.0)*1000); billed=max(tw,vol)
    # order type / cod
    otype="PREPAID"; cod=0
    if doc.get('custom_order_type') in ('COD','PPCOD') and float(doc.get('custom_cod_amount') or 0)>0:
        otype="COD"; cod=float(doc['custom_cod_amount'])
    # drop
    addr=G(f'/api/resource/Address/{doc.get("shipping_address_name")}') or {}
    drop=dict(name=addr.get('address_title') or doc.get('customer_name') or "",
              address=(addr.get('address_line1') or "")+((", "+addr['address_line2']) if addr.get('address_line2') else ""),
              city=addr.get('city') or "",state=addr.get('state') or "",pincode=addr.get('pincode') or "",
              phone=(addr.get('phone') or "").replace('+91','').replace(' ','').strip(),email=addr.get('email_id') or "")
    if not drop['pincode']: return None,'no-drop-pincode'
    si=G(f'/api/resource/Sales Invoice?filters=[["shopify_order_number","=","{son}"],["docstatus","=",1]]&fields=["name"]')
    inv=si[0]['name'] if si else ref
    gt=max(float(doc.get('grand_total') or 1),1.0)
    # recommendation
    recp=[{"pickup_pincode":PICKUP['pincode'],"drop_pincode":drop['pincode'],"order_type":otype,"reference_number":ref,
           "item":", ".join(e['description'] for e in items),"invoice_value":gt,"delivery_type":"FORWARD","weight":int(tw),
           "height":bh,"length":bl,"breadth":bb,"higher_of_dry_weight_and_volumetric_weight":int(billed),"item_count":ic,
           "additional":{"custom_fields":[{"key":"sku","value":",".join(skus)},{"key":"tier","value":tier}]}}]
    try:
        rj=requests.post(f"https://www.clickpost.in/api/v1/recommendation_api/?key={CPKEY}",json=recp,headers={'Content-Type':'application/json'},timeout=60).json()
    except: rj={}
    pref=[]
    for it in rj.get('result',[]): pref=it.get('preference_array',[]); break
    cands=[]
    for p in pref[:2]: cands.append((p.get('cp_id'),p.get('cp_name') or p.get('courier_name'),p.get('account_code','')))
    for cid,cn in [(5,'Bluedart'),(4,'Delhivery'),(9,'Shadowfax')]:
        if not any(c[0]==cid for c in cands): cands.append((cid,cn,''))
    pickup_time=time.strftime("%Y-%m-%d",time.localtime(time.time()+86400))+"T10:00:00+05:30"
    for cp_id,cp_name,acct in cands:
        if not cp_id: continue
        payload={"pickup_info":{"pickup_city":PICKUP['city'],"pickup_state":PICKUP['state'],"pickup_pincode":PICKUP['pincode'],"pickup_country":"IN","pickup_address":PICKUP['address'],"pickup_name":PICKUP['name'],"pickup_phone":PICKUP['phone'],"email":PICKUP['email'],"pickup_time":pickup_time},
          "drop_info":{"drop_name":drop['name'],"drop_address":drop['address'],"drop_city":drop['city'],"drop_state":drop['state'],"drop_pincode":drop['pincode'],"drop_country":"IN","drop_phone":drop['phone'],"drop_email":drop['email']},
          "shipment_details":{"courier_partner":cp_id,"reference_number":ref,"order_type":otype,"invoice_value":gt,"invoice_number":inv,"invoice_date":str(doc.get('posting_date')),"cod_value":cod,"weight":int(tw),"height":bh,"breadth":bb,"length":bl,"higher_of_dry_weight_and_volumetric_weight":int(billed),"item_count":ic,"items":items},
          "gst_info":{"seller_gstin":seller_gstin,"taxable_value":float(doc.get('net_total') or 0),"hsn_code":hsn,"igst_tax_rate":0,"sgst_tax_rate":0,"cgst_tax_rate":0},
          "additional":{"label":True,"return_info":{"pincode":PICKUP['pincode'],"name":PICKUP['name'],"address":PICKUP['address'],"phone":PICKUP['phone'],"city":PICKUP['city'],"state":PICKUP['state'],"country":"IN"},
            "custom_fields":[{"key":"sku","value":",".join(skus)},{"key":"order_code","value":son},{"key":"warehouse_address","value":WH_FULL},{"key":"number_of_boxes","value":1},{"key":"tier","value":tier}]}}
        if acct: payload['additional']['account_code']=acct
        try:
            cr=requests.post(f"https://www.clickpost.in/api/v3/create-order/?username={CPUSER}&key={CPKEY}",data=json.dumps(payload),headers={'Content-Type':'application/json'},timeout=90).json()
        except Exception as ex:
            cr={'meta':{'success':False,'message':str(ex)}}
        if cr.get('meta',{}).get('success'):
            awb=cr['result'].get('waybill','')
            S.put(f'{BASE}/api/resource/Delivery Note/{dn_name}',data=json.dumps({"awb_number":awb,"courier_partner":cp_name}),timeout=60)
            return awb,cp_name
    return None,'all-couriers-failed'

def shopify_fulfill(SHTOK, oid, awb, company, dn_name=None):
    """Create a Shopify fulfillment with tracking for an unfulfilled order."""
    SH={'X-Shopify-Access-Token':SHTOK,'Content-Type':'application/json'}
    GQL=f'{API}/graphql.json'
    fo=requests.get(f'{API}/orders/{oid}/fulfillment_orders.json',headers={'X-Shopify-Access-Token':SHTOK},timeout=60).json().get('fulfillment_orders',[])
    open_fos=[f for f in fo if f.get('status') in ('open','in_progress','scheduled')]
    if not open_fos: return 'no-open-fulfillment-order'
    foids=[{"fulfillmentOrderId":f"gid://shopify/FulfillmentOrder/{f['id']}"} for f in open_fos]
    q="""mutation($f:FulfillmentV2Input!){fulfillmentCreateV2(fulfillment:$f){fulfillment{id status} userErrors{field message}}}"""
    v={"f":{"lineItemsByFulfillmentOrder":foids,"trackingInfo":{"company":company,"number":awb},"notifyCustomer":False}}
    r=requests.post(GQL,headers=SH,data=json.dumps({"query":q,"variables":v}),timeout=60).json()
    res=r.get('data',{}).get('fulfillmentCreateV2',{})
    ue=res.get('userErrors',[])
    if ue: return f'ERR {ue}'
    fid=res.get('fulfillment',{}).get('id','')
    # write fulfillment id back to DN
    if dn_name and fid:
        numeric=fid.split('/')[-1]
        try: S.put(f'{BASE}/api/resource/Delivery Note/{dn_name}',data=json.dumps({"shopify_fulfillment_id":numeric}),timeout=60)
        except: pass
    return f'OK {fid.split("/")[-1]}'

def combo_repush_verify(results, courier_lookup=None, extra_waves=(600, 900)):
    """Safety re-check + re-push for combo (multi-AWB) batch results.
    `results` = list of tuples/dicts with at least (son, dn, awb1, awb2, courier).
    Accepts tuples of any length >=5; first 5 are (son, so_or_dn, dn, awb1, awb2[, courier...]) — extract dn,awb1,awb2,courier robustly.
    For each wave delay (seconds), checks Shopify and re-pushes any clobbered fulfillments with notify=true.
    Catches Atlas ecommerce_integrations queued sync clobbers that happen AFTER the initial 240s notify window
    (typically for late-created fulfillments — hold-released orders, retry-created fulfillments).
    AWB3-AWARE: reads custom_awb_3 from the DN; if present, includes in expected/push sets.
    """
    SHTOK_local=shtoken(); SH_local={'X-Shopify-Access-Token':SHTOK_local,'Content-Type':'application/json'}
    GQL=f'{API}/graphql.json'
    def normalize(r):
        # supports both (son,so,dn,awb1,awb2,courier,status), (son,so,dn,awb1,awb2,awb3,courier,status), (son,dn,awb1,awb2,courier)
        if len(r)>=8: return (r[0],r[2],r[3],r[4],r[6])
        if len(r)==7: return (r[0],r[2],r[3],r[4],r[5])
        if len(r)==6: return (r[0],r[1],r[2],r[3],r[4])
        if len(r)==5: return r
        return None
    eligible=[normalize(r) for r in results]
    eligible=[r for r in eligible if r and r[2] and r[3]]
    if not eligible: return
    for wave_idx,delay in enumerate(extra_waves,1):
        print(f'\n--- Safety wave {wave_idx}: sleeping {delay}s before re-check ---')
        time.sleep(delay)
        fixed=0; intact=0
        for son,dn,awb1,awb2,courier in eligible:
            d=G(f'/api/resource/Delivery Note/{dn}?fields=["shopify_order_id","custom_awb_3"]') or {}
            oid=d.get('shopify_order_id'); awb3=d.get('custom_awb_3') or None
            if not oid: continue
            try: o=requests.get(f'{API}/orders/{oid}.json?status=any',headers={'X-Shopify-Access-Token':SHTOK_local},timeout=30).json().get('order') or {}
            except: continue
            expected=set([a for a in [awb1,awb2,awb3] if a])
            nums=[]
            for f in (o.get('fulfillments') or []): nums.extend(f.get('tracking_numbers') or [])
            if expected==set(nums): intact+=1; continue
            # clobbered — find success fid and re-push
            succ=[f for f in (o.get('fulfillments') or []) if f.get('status')=='success']
            if not succ: print(f'  {son}: no success ful'); continue
            fid=succ[0]['id']
            push_nums=list(expected); urls=[f'https://www.clickpost.in/tracking/#/{a}' for a in push_nums]
            q='mutation u($f:ID!,$t:FulfillmentTrackingInput!){fulfillmentTrackingInfoUpdateV2(fulfillmentId:$f,trackingInfoInput:$t,notifyCustomer:true){fulfillment{id trackingInfo{number}} userErrors{message}}}'
            for _ in range(3):
                res=requests.post(GQL,headers=SH_local,data=json.dumps({'query':q,'variables':{'f':f'gid://shopify/Fulfillment/{fid}','t':{'company':courier,'numbers':push_nums,'urls':urls}}}),timeout=60).json()
                ti=[t.get('number') for t in (((res.get('data') or {}).get('fulfillmentTrackingInfoUpdateV2') or {}).get('fulfillment') or {}).get('trackingInfo',[])]
                if expected==set(ti): print(f'  ✅ wave{wave_idx} fix {son}: {ti}'); fixed+=1; break
                time.sleep(4)
            else: print(f'  ⚠️ wave{wave_idx} {son}: last {ti}')
        print(f'  wave {wave_idx} done: intact={intact} fixed={fixed} of {len(eligible)}')
