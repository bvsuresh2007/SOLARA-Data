"""rep_dupe_guard.py — Layer-2 safety net against duplicate AWBs on replacement (REP) DNs.

Root cause it guards: a replacement DN can get booked TWICE — Gopal's v7 Clickpost hook
(Delivery Note On Submit, reference = DN name) + this repo's process_reps_mrp.book_mrp
(reference = <order>-REP). The DN keeps the last-written waybill; the other is an orphaned
live booking stuck at OrderPlaced. (process_reps_mrp.py now DEFERS to the hook, so new batches
shouldn't create these — this script catches any that still slip through, and backfills history.)

HOW IT FINDS THE ORPHAN (reliably):
  - Atlas document Version history logs every awb_number overwrite as [old, new]. The OLD value
    is the orphan waybill (the hook's booking that book_mrp overwrote). We also union in the DN's
    current awb fields + a reference-status cross-check (track-order by reference_number).
  - Each candidate waybill is tracked (Clickpost track-order). An orphan = a waybill NOT on the DN
    record whose status is still 'dead' (New / OrderPlaced / Online shipment booked).

SAFETY:
  - REPORT-ONLY by default. Pass --cancel to actually void orphans.
  - Even with --cancel, it NEVER cancels a waybill that is (a) on the DN record, or (b) has moved
    (Delivered / In-Transit / Out-For-Delivery / RTO). A DN with TWO *moved* shipments is flagged
    as DOUBLE-SHIPPED for manual review, never auto-cancelled.

USAGE:
  python rep_dupe_guard.py <dns.txt | batch_results.json>   # report only
  python rep_dupe_guard.py <...> --cancel                   # void confirmed dead orphans
  python rep_dupe_guard.py --days 7                          # scan replacement DNs from last 7 days
  python rep_dupe_guard.py --days 7 --cancel
"""
import sys, os, json, time, re, urllib.parse as up, urllib3, requests
urllib3.disable_warnings(); sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
from complete_awb_lib import S, BASE, G, CPUSER, CPKEY

ARGS=sys.argv[1:]
DO_CANCEL='--cancel' in ARGS
DAYS=None
for i,a in enumerate(ARGS):
    if a=='--days' and i+1<len(ARGS): DAYS=int(ARGS[i+1])
POS=[a for a in ARGS if not a.startswith('--') and not a.isdigit()]

DEAD={'new','online shipment booked','orderplaced'}  # genuinely booked but not yet moved
def normstat(st):
    if st is None: return 'ABSENT'          # no booking / not trackable — NOT a live shipment, never an orphan
    s=str(st).strip().lower()
    if s=='': return 'ABSENT'
    if 'deliver' in s and 'out for' not in s: return 'DELIVERED'
    if 'rto' in s: return 'RTO'
    if 'cancel' in s: return 'CANCELLED'
    if s in DEAD: return 'DEAD'
    return 'MOVING'
def cp_for(awb): return 9 if awb.endswith('OLL') else None  # Shadowfax; numeric resolved by probe

_tc={}
def track(awb):
    if awb in _tc: return _tc[awb]
    cps=[9] if awb.endswith('OLL') else [5,9,4,46,2]
    out=({},None)
    for cp in cps:
        url='https://www.clickpost.in/api/v2/track-order/?'+up.urlencode({'username':CPUSER,'key':CPKEY,'waybill':awb,'cp_id':cp})
        for _ in range(3):
            try:
                r=requests.get(url,timeout=30,verify=False)
                if r.status_code==200:
                    res=(r.json().get('result') or {}).get(awb) or {}
                    if res: out=(res,cp); break
            except Exception: pass
            time.sleep(2)
        if out[0]: break
    _tc[awb]=out; return out
def track_ref(ref):
    """Status of a reference_number's booking (no waybill returned by this endpoint)."""
    url='https://www.clickpost.in/api/v2/track-order/?'+up.urlencode({'username':CPUSER,'key':CPKEY,'reference_number':ref,'cp_id':9})
    try:
        r=requests.get(url,timeout=30,verify=False)
        if r.status_code==200:
            res=(r.json().get('result') or {}).get(ref) or {}
            if res: return (res.get('latest_status') or {}).get('status')
    except Exception: pass
    return None
def cancel(awb,cp):
    url='https://www.clickpost.in/api/v1/cancel-order/?'+up.urlencode({'username':CPUSER,'key':CPKEY,'waybill':awb,'cp_id':cp})
    for _ in range(3):
        try:
            j=requests.get(url,timeout=60,verify=False).json(); m=j.get('meta',{})
            return m.get('success'), str(m.get('message',j))[:100]
        except Exception as e: time.sleep(3); last=str(e)[:100]
    return None, last

def dn_awbset(d):
    s=[]
    if d.get('awb_number'): s.append(d['awb_number'])
    if d.get('custom_awb_2'): s.append(d['custom_awb_2'])
    try:
        for x in json.loads(d.get('custom_awb_list') or '[]'):
            if x.get('awb'): s.append(x['awb'])
    except Exception: pass
    return list(dict.fromkeys(s))
def version_awbs(dn):
    """Every awb_number value ever written to this DN (from Version history)."""
    r=S.get(f'{BASE}/api/resource/Version',params={'filters':json.dumps([['ref_doctype','=','Delivery Note'],['docname','=',dn]]),'fields':json.dumps(['data']),'limit_page_length':0},timeout=60,verify=False)
    out=set()
    if r.status_code==200:
        for row in r.json().get('data',[]):
            try:
                for c in json.loads(row.get('data') or '{}').get('changed',[]):
                    if str(c[0]).lower()=='awb_number':
                        for v in c[1:]:
                            if v and isinstance(v,str): out.add(v)
            except Exception: pass
    return out

def collect_dns():
    if DAYS is not None:
        cutoff=(time.strftime('%Y-%m-%d',time.localtime(time.time()-DAYS*86400)))
        r=S.get(f'{BASE}/api/resource/Delivery Note',params={'filters':json.dumps([['is_replacement','=',1],['docstatus','=',1],['creation','>=',cutoff]]),'fields':json.dumps(['name']),'limit_page_length':0},timeout=120,verify=False)
        return [x['name'] for x in (r.json().get('data',[]) if r.status_code==200 else [])]
    if not POS: print('No input. Pass a DN list / results.json, or --days N.'); sys.exit(1)
    fp=POS[0]; txt=open(fp).read()
    dns=set()
    if fp.endswith('.json'):
        try:
            for row in json.loads(txt):
                for v in (row if isinstance(row,(list,tuple)) else [row]):
                    if isinstance(v,str) and re.match(r'^(SHPDN|OTHDN|REZDN|OFFDN)',v): dns.add(v)
        except Exception: pass
    if not dns:
        dns={w for w in re.split(r'\s+',txt) if re.match(r'^(SHPDN|OTHDN|REZDN|OFFDN)',w)}
    return sorted(dns)

DNS=collect_dns()
print(f'Scanning {len(DNS)} replacement DN(s)  cancel={DO_CANCEL}\n')
rows=[]
for i,dn in enumerate(DNS,1):
    d=G(f'/api/resource/Delivery Note/{dn}') or {}
    if not d: rows.append({'dn':dn,'verdict':'DN-READ-FAIL'}); print(f'[{i}] {dn} DN-READ-FAIL'); continue
    kept=dn_awbset(d); keptset=set(kept)
    cust=d.get('customer_name')
    cand=set(kept) | version_awbs(dn)
    # classify every candidate waybill
    stat={}
    for a in cand: stat[a]=normstat((track(a)[0].get('latest_status') or {}).get('status'))
    # reference-status cross-check (detect a live orphan even if Version missed it)
    son=d.get('shopify_order_number') or dn
    refstat={r:normstat(track_ref(r)) for r in dict.fromkeys([dn, dn+'-REP', str(son), str(son)+'-REP'])}
    # a reference is "active" only if it has a real pending/moving/delivered booking — NOT cancelled/RTO/absent
    live_refs=[r for r,s in refstat.items() if s in ('DEAD','MOVING','DELIVERED')]
    orphans=[a for a in cand if a not in keptset and stat.get(a)=='DEAD']
    # a TRUE double-ship = an off-DN parcel that actually delivered or is actively moving.
    moved_offdn=[a for a in cand if a not in keptset and stat.get(a) in ('DELIVERED','MOVING')]
    # off-DN that is cancelled or returning (incl. 'SHIPPER INSTRUCTED TO RTO') = a voided dup — benign.
    voided_offdn=[a for a in cand if a not in keptset and stat.get(a) in ('CANCELLED','RTO')]
    verdict='CLEAN'; actions=[]
    if moved_offdn:
        verdict='DOUBLE-SHIPPED (manual review)'   # two real parcels (delivered/in-transit) — never auto-cancel
    elif orphans:
        verdict='ORPHAN-DUP'
        if DO_CANCEL:
            for a in orphans:
                # re-verify dead + not on DN, right before cancel
                res,cp=track(a); cp=cp or cp_for(a)
                if normstat((res.get('latest_status') or {}).get('status'))!='DEAD' or a in keptset:
                    actions.append((a,'SKIP-changed')); continue
                ok,msg=cancel(a,cp); actions.append((a,('cancelled' if ok else 'cancel-fail:'+str(msg))))
        else:
            actions=[(a,'would-cancel') for a in orphans]
    elif len(live_refs) >= 2 and not orphans and not moved_offdn:
        # two genuinely-active references but Version gave no off-DN waybill — flag for manual recovery
        verdict='DUP-SUSPECT (refs live, waybill not recovered)'
    rows.append({'dn':dn,'cust':cust,'kept':kept,'candidates':sorted(cand),'stat':stat,
                 'refstat':refstat,'orphans':orphans,'moved_offdn':moved_offdn,'voided_offdn':voided_offdn,'verdict':verdict,'actions':actions})
    tag=verdict if verdict!='CLEAN' else 'clean'
    extra=('  orphans=%s %s'%(orphans,actions)) if (orphans or actions) else ('  DOUBLE=%s'%moved_offdn if moved_offdn else '')
    print(f'[{i}/{len(DNS)}] {dn} {cust or ""} -> {tag}{extra}')

clean=[r for r in rows if r['verdict']=='CLEAN']
orph=[r for r in rows if r['verdict']=='ORPHAN-DUP']
dbl=[r for r in rows if r['verdict'].startswith('DOUBLE')]
susp=[r for r in rows if r['verdict'].startswith('DUP-SUSPECT')]
print('\n================ REP DUPE GUARD SUMMARY ================')
print('scanned        :',len(rows))
print('clean          :',len(clean))
print('orphan-dup     :',len(orph),'(%s)'%('cancelled' if DO_CANCEL else 'report-only; rerun with --cancel'))
for r in orph: print('   %s %s  orphans=%s  %s'%(r['dn'],r['cust'] or '',r['orphans'],r['actions']))
print('DOUBLE-SHIPPED :',len(dbl),'(MANUAL — two real shipments; never auto-cancelled)')
for r in dbl: print('   %s %s  off-DN moved=%s'%(r['dn'],r['cust'] or '',r['moved_offdn']))
print('dup-suspect    :',len(susp),'(refs live but orphan waybill not recoverable from Version — check manually)')
for r in susp: print('   %s %s  refstat=%s'%(r['dn'],r['cust'] or '',r['refstat']))
json.dump(rows,open('rep_dupe_guard_results.json','w'),indent=1,default=str)
print('\n-> rep_dupe_guard_results.json')
