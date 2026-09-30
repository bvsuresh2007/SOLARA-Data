"""Process replacement REP SOs: DN(is_replacement) -> submit(auto-MR) -> AWB with MRP declared value
(mrp_total, like reship_79_v2 / v6 server script). NO Shopify push. Reads batch file from argv[1]."""
import sys, json, re, time, datetime, urllib.parse, requests, urllib3
urllib3.disable_warnings(); sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
from complete_awb_lib import S, BASE, G, PICKUP, WH_FULL, CPUSER, CPKEY
from clickpost_mrp import mrp_value
H={'Authorization':S.headers['Authorization'],'Content-Type':'application/json'}
WH='Main Warehouse - WTBBPL'; COMPANY='Win The Buy Box Private Limited'; DATE=datetime.date.today().isoformat()
REPS=open(sys.argv[1]).read().split()
def POST(p,b,t=180):
    for i in range(4):
        try:
            r=requests.post(f'{BASE}{p}',headers=H,json=b,timeout=t,verify=False)
            if r.status_code in (200,201): return (r.json().get('data') or r.json().get('message')),None
            if r.status_code in (502,503,504): time.sleep(3); continue
            e=r.text; ix=e.find('"exception":'); return None,(e[ix+12:ix+220] if ix>=0 else e[:200])
        except Exception: time.sleep(2**i)
    return None,'retry'
def PUT(p,b,t=250):
    for i in range(4):
        try:
            r=requests.put(f'{BASE}{p}',headers=H,json=b,timeout=t,verify=False)
            if r.status_code==200: return True,None
            if r.status_code in (502,503,504): time.sleep(3); continue
            e=r.text; ix=e.find('"exception":'); return False,(e[ix+12:ix+220] if ix>=0 else e[:200])
        except Exception: time.sleep(2**i)
    return False,'retry'
def imeta(sku):
    im=G(f'/api/resource/Item/{urllib.parse.quote(sku)}?fields=["item_name","gst_hsn_code","weight_per_unit","pkg_weight_gm","pkg_length_cm","pkg_width_cm","pkg_height_cm"]') or {}
    wg=int(float(im.get('pkg_weight_gm') or 0) or float(im.get('weight_per_unit') or 0)*1000) or 800
    bl=int(float(im.get('pkg_length_cm') or 0)) or 30; bw=int(float(im.get('pkg_width_cm') or 0)) or 20; bh=int(float(im.get('pkg_height_cm') or 0)) or 15
    return {'name':im.get('item_name') or sku,'hsn':str(im.get('gst_hsn_code') or ''),'wg':wg,'bl':bl,'bw':bw,'bh':bh}
def mrsku(sku,qty):
    b=S.get(f'{BASE}/api/resource/Bin',params={'filters':json.dumps([['item_code','=',sku],['warehouse','=',WH]]),'fields':json.dumps(['valuation_rate'])},timeout=30).json().get('data',[])
    vr=float(b[0].get('valuation_rate') or 0) if b else 0
    if vr<=0:
        it=G(f'/api/resource/Item/{urllib.parse.quote(sku)}?fields=["valuation_rate","last_purchase_rate"]') or {}
        vr=float(it.get('valuation_rate') or 0) or float(it.get('last_purchase_rate') or 0)
    if vr<=0: return None
    ste,_=POST('/api/resource/Stock Entry',{'doctype':'Stock Entry','stock_entry_type':'Material Receipt','company':COMPANY,'purpose':'Material Receipt','to_warehouse':WH,'set_posting_time':1,'posting_date':DATE,'posting_time':'22:00:00','items':[{'item_code':sku,'qty':qty,'t_warehouse':WH,'basic_rate':vr,'allow_zero_valuation_rate':0}]})
    if ste: PUT(f'/api/resource/Stock Entry/{ste["name"]}',{'docstatus':1}); time.sleep(1); return sku+'x'+str(int(qty))+'@'+str(int(vr))
    return None
def bin_actual(sku):
    b=S.get(f'{BASE}/api/resource/Bin',params={'filters':json.dumps([['item_code','=',sku],['warehouse','=',WH]]),'fields':json.dumps(['actual_qty'])},timeout=30).json().get('data',[])
    return float(b[0].get('actual_qty') or 0) if b else 0
def submit_cover(dn):
    """Submit DN. NEVER creates a Material Receipt — MRs require explicit user approval
    (2026-09-30 rule, after the auto-MR runaway that added 7,259 phantom AF-501 units).
    On NegativeStock, classify the blocker and return WITHOUT creating anything:
      reserved-negative:<sku> -> physical stock covers need; block is reservations (not a stock problem)
      NEEDS-MR:<sku> need=/have=/short= -> genuine physical shortage; surface for per-SKU approval."""
    d0=G(f'/api/resource/Delivery Note/{dn}') or {}
    need={}
    for it in d0.get('items',[]): need[it['item_code']]=need.get(it['item_code'],0)+float(it.get('qty') or 0)
    for pk in d0.get('packed_items',[]): need[pk['item_code']]=need.get(pk['item_code'],0)+float(pk.get('qty') or 0)
    ok,se=PUT(f'/api/resource/Delivery Note/{dn}',{'docstatus':1})
    if ok: return True,[],None
    e=se or ''
    if 'NegativeStock' in e or ('ValidationError' in e and 'units of' in e):
        m=re.search(r'units of.*?Item ([A-Za-z0-9-]+)',e)
        if not m: return False,[],e[:120]
        sku=m.group(1); needed=need.get(sku,1.0); phys=bin_actual(sku)
        if phys>=needed: return False,[],'reserved-negative:'+sku+f' (phys {phys:.0f}>=need {needed:.0f})'
        return False,[],f'NEEDS-MR:{sku} need={needed:.0f} have={phys:.0f} short={needed-phys:.0f}'
    d2=G(f'/api/resource/Delivery Note/{dn}')
    if d2.get('docstatus')==1: return True,[],None
    return False,[],e[:120]
def real_courier(awb):
    a=(awb or '').upper()
    if a.startswith('SF'): return 'Shadowfax'
    if a.startswith('WB'): return 'ElasticRun'
    if a[:3].isdigit() and len(a)==11 and a.startswith('509'): return 'Bluedart'
    if a.startswith('29044') or a.startswith('685'): return 'Delhivery'
    return None
def book_mrp(dn):
    d=G(f'/api/resource/Delivery Note/{dn}')
    addr=G(f'/api/resource/Address/{urllib.parse.quote(d.get("shipping_address_name") or "")}') or {}
    phys=[(i['item_code'],int(i['qty'])) for i in d.get('items',[]) if i['item_code'].startswith('SOL-')]
    if not phys: return None,None,'no-phys-sku'
    metas=[imeta(s) for s,_ in phys]
    wg=sum(m['wg']*q for m,(_,q) in zip(metas,phys)) or 800
    bl=max(m['bl'] for m in metas); bw=max(m['bw'] for m in metas); bh=max(m['bh'] for m in metas)
    twk=wg/1000.0
    if twk<3: b2=(30,20,15)
    elif twk<8: b2=(40,30,25)
    else: b2=(50,40,35)
    bl=max(bl,b2[0]); bw=max(bw,b2[1]); bh=max(bh,b2[2]); billed=max(wg,int((bl*bw*bh)/5000.0*1000))
    mrp_tot=sum(mrp_value(BASE,H,s)*q for s,q in phys)
    zero=[s for s,q in phys if mrp_value(BASE,H,s)<1]
    if mrp_tot<1 or zero: return None,None,'zero-mrp:'+','.join(zero or [s for s,_ in phys])
    items=[{'sku':s,'description':m['name'],'quantity':q,'price':mrp_value(BASE,H,s),'length':bl,'breadth':bw,'height':bh,
            'gst_info':{'seller_gstin':'36AADCW0665P1ZS','taxable_value':0,'hsn_code':m['hsn'],'igst_tax_rate':0,'sgst_tax_rate':0,'cgst_tax_rate':0},
            'additional':{'weight':m['wg'],'length':bl,'breadth':bw,'height':bh}} for (s,q),m in zip(phys,metas)]
    drop={'drop_name':addr.get('address_title') or d.get('customer_name') or 'Customer','drop_address':((addr.get('address_line1') or '')+((', '+addr['address_line2']) if addr.get('address_line2') else ''))[:200] or 'NA','drop_city':addr.get('city'),'drop_state':addr.get('state'),'drop_pincode':str(addr.get('pincode') or ''),'drop_country':'IN','drop_phone':(addr.get('phone') or '').replace('+91','').replace(' ','').replace('-','').lstrip('0')[-10:],'drop_email':addr.get('email_id') or 'na@solara.in'}
    pt=time.strftime('%Y-%m-%d',time.localtime(time.time()+86400))+'T10:00:00+05:30'
    son=d.get('shopify_order_number') or dn
    def mk(cp,suf):
        return {'pickup_info':{'pickup_city':PICKUP['city'],'pickup_state':PICKUP['state'],'pickup_pincode':PICKUP['pincode'],'pickup_country':'IN','pickup_address':PICKUP['address'],'pickup_name':PICKUP['name'],'pickup_phone':PICKUP['phone'],'email':PICKUP['email'],'pickup_time':pt},
                'drop_info':drop,
                'shipment_details':{'courier_partner':cp,'reference_number':str(son)+'-REP'+suf,'order_type':'PREPAID','invoice_value':max(mrp_tot,1.0),'invoice_number':str(son)+'-REP','invoice_date':DATE,'cod_value':0,'weight':wg,'height':bh,'breadth':bw,'length':bl,'higher_of_dry_weight_and_volumetric_weight':billed,'item_count':sum(q for _,q in phys),'items':items},
                'gst_info':{'seller_gstin':'36AADCW0665P1ZS','taxable_value':0,'hsn_code':metas[0]['hsn'],'igst_tax_rate':0,'sgst_tax_rate':0,'cgst_tax_rate':0},
                'additional':{'label':True,'return_info':{'pincode':PICKUP['pincode'],'name':PICKUP['name'],'address':PICKUP['address'],'phone':PICKUP['phone'],'city':PICKUP['city'],'state':PICKUP['state'],'country':'IN'},'custom_fields':[{'key':'sku','value':','.join(s for s,_ in phys)},{'key':'order_code','value':str(son)},{'key':'warehouse_address','value':WH_FULL},{'key':'number_of_boxes','value':1}]}}
    # Clickpost recommendation first (per-pincode, same as forward-order gen_awb_for_dn), then fixed fallback
    order=[]
    try:
        recp=[{'pickup_pincode':PICKUP['pincode'],'drop_pincode':str(drop.get('drop_pincode')),'order_type':'PREPAID','reference_number':str(son),'item':'g','invoice_value':max(mrp_tot,1.0),'delivery_type':'FORWARD','weight':wg,'height':bh,'length':bl,'breadth':bw,'higher_of_dry_weight_and_volumetric_weight':billed,'item_count':sum(q for _,q in phys)}]
        rj=requests.post(f'https://www.clickpost.in/api/v1/recommendation_api/?key={CPKEY}',json=recp,timeout=45,verify=False).json()
        pa=next((it.get('preference_array',[]) for it in rj.get('result',[])),[])
        for p in pa:
            cid=p.get('cp_id')
            if cid and cid not in [o[0] for o in order]: order.append((cid,p.get('cp_name') or p.get('courier_name') or str(cid)))
    except: pass
    for fb in [(5,'Bluedart'),(4,'Delhivery'),(9,'Shadowfax'),(46,'ElasticRun')]:
        if fb[0] not in [o[0] for o in order]: order.append(fb)
    for cp,cn in order:
        for suf in ('','-RW1','-RW2'):
            try: cr=requests.post(f'https://www.clickpost.in/api/v3/create-order/?username={CPUSER}&key={CPKEY}',data=json.dumps(mk(cp,suf)),headers={'Content-Type':'application/json'},timeout=90,verify=False).json()
            except: cr={'meta':{'success':False}}
            if cr.get('meta',{}).get('success'):
                w=cr['result'].get('waybill','')
                if w:
                    c=real_courier(w) or cn; PUT(f'/api/resource/Delivery Note/{dn}',{'awb_number':w,'courier_partner':c}); return w,c,round(mrp_tot,2)
    return None,None,'awb-fail'
out=[]
for i,so in enumerate(REPS,1):
    sd=G(f'/api/resource/Sales Order/{urllib.parse.quote(so)}')
    if not sd or not sd.get('name'): print(f'[{i}/{len(REPS)}] {so} SO-FAIL'); out.append((so,'',None,'SO-FAIL')); continue
    if sd.get('docstatus')==0:
        if sd.get('company_address')!='Win The Buy Box Private Limited-Billing': PUT(f'/api/resource/Sales Order/{so}',{'company_address':'Win The Buy Box Private Limited-Billing'}); time.sleep(0.3)
        oks,_=PUT(f'/api/resource/Sales Order/{so}',{'docstatus':1})
        if not oks: print(f'[{i}/{len(REPS)}] {so} SO-submit-fail'); out.append((so,'',None,'so-submit')); continue
        time.sleep(0.5)
    skus=','.join(it['item_code'] for it in sd.get('items',[]))
    r,err=POST('/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',{'source_name':so},t=120)
    if not r: print(f'[{i}/{len(REPS)}] RED {so} mapper:{err}'); out.append((so,skus,None,'mapper')); continue
    dn=r if isinstance(r,dict) else r
    dn['is_replacement']=1; dn['set_posting_time']=1; dn['posting_date']=DATE; dn['posting_time']='14:30:00'
    dn['shipping_address_name']=sd.get('shipping_address_name'); dn['customer_address']=sd.get('customer_address')
    st=''
    if sd.get('shipping_address_name'):
        a=G('/api/resource/Address/'+urllib.parse.quote(sd['shipping_address_name'])) or {}; st=(a.get('state') or '').strip().lower()
    dn['taxes_and_charges']='GST 18% Intrastate - WTBBPL' if st=='telangana' else 'GST 18% Interstate - WTBBPL'
    dn['taxes']=[]
    dn['company_address']='Win The Buy Box Private Limited-Billing'; dn.pop('company_address_display',None)
    for it in dn.get('items',[]): it.pop('item_tax_template',None)
    rr,e2=POST('/api/resource/Delivery Note',dn)
    if not rr: print(f'[{i}/{len(REPS)}] RED {so} dn:{e2}'); out.append((so,skus,None,'dn')); continue
    DN=rr['name']
    ok,mrs,serr=submit_cover(DN)
    if not ok: print(f'[{i}/{len(REPS)}] RED {so} {DN} sub:{serr}'); out.append((so,skus,DN,'sub:'+str(serr)[:40])); continue
    awb,c,mrp=book_mrp(DN)
    if awb:
        print(f'[{i}/{len(REPS)}] OK {so} {DN} '+(('MR['+';'.join(mrs)+'] ') if mrs else '')+str(awb)+' '+str(c)+' declaredMRP='+str(mrp))
        out.append((so,skus,DN,awb,c,mrp))
    else:
        print(f'[{i}/{len(REPS)}] RED {so} {DN} awb-fail'); out.append((so,skus,DN,'awb-fail'))
json.dump(out,open(sys.argv[1].replace('.txt','_results.json'),'w'))
ok=[x for x in out if len(x)>=5 and x[3] and str(x[3]) not in ('awb-fail',) and not str(x[3]).startswith(('SO','mapper','dn','sub'))]
print(f'\n=== shipped {sum(1 for x in out if len(x)>=6)}/{len(REPS)} ===')
