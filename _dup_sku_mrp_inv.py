import io,sys,json,urllib.parse
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',line_buffering=True)
from complete_awb_lib import S,BASE,G
from clickpost_mrp import mrp_value
H={'Authorization':S.headers['Authorization']}
targets=open('_dup_batch.txt').read().split()
_mrp={}
def M(s):
    if s not in _mrp:
        try:_mrp[s]=mrp_value(BASE,H,s)
        except:_mrp[s]=0
    return _mrp[s]
_b={}
def comp(sku):
    if sku in _b: return _b[sku]
    pb=S.get(f'{BASE}/api/resource/Product Bundle',params={'filters':json.dumps([['new_item_code','=',sku]]),'fields':json.dumps(['name'])},timeout=40,verify=False).json().get('data',[])
    if pb:
        b=G('/api/resource/Product Bundle/'+urllib.parse.quote(pb[0]['name'])) or {}
        _b[sku]=[(it['item_code'],int(it.get('qty') or 1)) for it in b.get('items',[])]
    else:_b[sku]=None
    return _b[sku]
_bin={}
def binq(sku):
    if sku in _bin: return _bin[sku]
    rows=S.get(f'{BASE}/api/resource/Bin',params={'filters':json.dumps([['item_code','=',sku]]),'fields':json.dumps(['warehouse','actual_qty','reserved_qty','projected_qty'])},timeout=40,verify=False).json().get('data',[])
    d={}
    for r in rows:
        d[r['warehouse']]=(r.get('actual_qty') or 0,r.get('reserved_qty') or 0,r.get('projected_qty') or 0)
    _bin[sku]=d
    return d
def wh_short(w):
    w=w or ''
    if w.startswith('Main'): return 'Main'
    if 'Hold' in w: return 'Hold'
    if 'Damage' in w or 'Reject' in w: return 'Dmg'
    return w.split(' - ')[0][:10]
repskus={}; allskus=set()
for rep in targets:
    so=G(f'/api/resource/Sales Order/{rep}') or {}
    ls=[]
    for it in so.get('items',[]):
        c=comp(it['item_code'])
        if c:
            for cs,cq in c: ls.append((cs,int(it.get('qty') or 1)*cq))
        else: ls.append((it['item_code'],int(it.get('qty') or 1)))
    repskus[rep]=ls
    for s,q in ls: allskus.add(s)
print('===== PER-REP SKU + MRP =====')
for rep in targets:
    parts=[]
    for s,q in repskus[rep]:
        m=M(s); tag='' if (m and m>=1) else ' !ZERO-MRP'
        parts.append(f'{s} x{q} @Rs{m}{tag}')
    print(f'{rep}: '+' | '.join(parts))
print('\n===== MRP SUMMARY =====')
zero=sorted([s for s in allskus if not M(s) or M(s)<1])
if not zero: print(f'ALL {len(allskus)} SKUs have MRP>=1  -> MRP OK')
else:
    print('ZERO-MRP SKUs:',zero)
    for r in targets:
        z=[s for s,q in repskus[r] if not M(s) or M(s)<1]
        if z: print(f'  BLOCKED {r}: {z}')
print('\n===== INVENTORY (batch demand vs stock; act=physical, avail=act-reserved) =====')
from collections import defaultdict
# aggregate demand across ALL reps in the batch (repskus is already combo-expanded)
demand=defaultdict(float); demreps=defaultdict(list)
for rep in targets:
    seen=set()
    for s,q in repskus[rep]:
        demand[s]+=q
        if s not in seen: demreps[s].append(rep); seen.add(s)
low=[]; short=[]; resneg=[]
for s in sorted(allskus):
    d=binq(s)
    main=d.get('Main Warehouse - WTBBPL') or next((v for w,v in d.items() if w.startswith('Main')),(0,0,0))
    hold=next((v for w,v in d.items() if 'Hold' in w),(0,0,0))
    mavail=main[0]-main[1]; havail=hold[0]-hold[1]
    tot_act=sum(v[0] for v in d.values())
    tot_avail=sum((v[0]-v[1]) for v in d.values())
    dem=demand.get(s,0)
    reps=sorted(set(demreps[s]))
    # NEEDS-MR predictor: total physical < total batch demand (matches driver's submit_cover)
    if dem>tot_act:
        flag=f'  <<< SHORT {int(dem-tot_act)}u (demand {int(dem)} > phys {int(tot_act)}) -> NEEDS-MR'
        short.append((s,int(dem),int(tot_act),int(dem-tot_act),reps))
    # reserved-negative risk: physical covers demand but available goes negative
    elif dem>tot_avail:
        flag=f'  <<< RES-NEG (demand {int(dem)} > avail {int(tot_avail)}; phys {int(tot_act)} covers)'
        resneg.append((s,int(dem),int(tot_avail),int(tot_act),reps))
    else:
        flag=''
    print(f'{s:28s} demand{dem:.0f} | Main act{main[0]:.0f} res{main[1]:.0f} avail{mavail:.0f} | Hold act{hold[0]:.0f} avail{havail:.0f} | tot_act{tot_act:.0f} tot_avail{tot_avail:.0f}{flag}')
    if tot_avail<1: low.append(s)
print('\n===== SHORTFALL SUMMARY (batch demand vs physical stock) =====')
if not short and not resneg:
    print('No shortfalls: every SKU has physical stock >= batch demand.  -> INVENTORY OK')
if short:
    print('WILL NEEDS-MR (physical < batch demand) -- needs MR BEFORE shipping:')
    for s,dem,act,sh,reps in short:
        print(f'  {s}: demand {dem} vs phys {act}  -> MR {sh} units | REPs: {reps}')
if resneg:
    print('RESERVED-NEGATIVE risk (phys covers, avail negative -- usually ships, may need posting-time nudge):')
    for s,dem,av,act,reps in resneg:
        print(f'  {s}: demand {dem} vs avail {av} (phys {act}) | REPs: {reps}')
json.dump({'targets':targets,'repskus':{k:v for k,v in repskus.items()},'zero_mrp':zero,'no_stock':low,
           'short':[{'sku':s,'demand':dem,'phys':act,'mr_units':sh,'reps':reps} for s,dem,act,sh,reps in short],
           'resneg':[{'sku':s,'demand':dem,'avail':av,'phys':act,'reps':reps} for s,dem,av,act,reps in resneg]},
          open('_dup_sku_mrp_inv.json','w'))
