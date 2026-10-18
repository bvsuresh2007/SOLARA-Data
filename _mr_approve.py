"""Explicit, user-approved Material Receipts — the ONLY sanctioned way to create an MR
in the REP pipeline (2026-09-30 rule: no autonomous MRs; every MR needs user approval
with a confirmed rate — never assumed).

Input: _mr_approved.json = [{"sku": "...", "qty": N, "rate": R}, ...]
Each row MUST carry an explicit rate the USER confirmed. Rows with rate missing/<=0 are REFUSED.
Creates + submits one Material Receipt per row into Main, prints STE + new on-hand.
Run: python _mr_approve.py
"""
import sys, json, datetime, requests, urllib3
urllib3.disable_warnings(); sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
from complete_awb_lib import S, BASE
H={'Authorization':S.headers['Authorization'],'Content-Type':'application/json'}
WH='Main Warehouse - WTBBPL'; COMPANY='Win The Buy Box Private Limited'; DATE=datetime.date.today().isoformat()
rows=json.load(open('_mr_approved.json'))
assert isinstance(rows,list) and rows, '_mr_approved.json must be a non-empty list'
print(f'Creating {len(rows)} user-approved Material Receipt(s):')
done=[]
for r in rows:
    sku=r['sku']; qty=float(r['qty']); rate=float(r.get('rate') or 0)
    if rate<=0:
        print(f'  REFUSED {sku}: no confirmed rate (never assume valuation) — set "rate" and re-run'); continue
    body={'doctype':'Stock Entry','stock_entry_type':'Material Receipt','company':COMPANY,'purpose':'Material Receipt',
          'to_warehouse':WH,'set_posting_time':1,'posting_date':DATE,'posting_time':'06:00:00',
          'items':[{'item_code':sku,'qty':qty,'t_warehouse':WH,'basic_rate':rate,'allow_zero_valuation_rate':0,'expense_account':'Stock Adjustment - WTBBPL'}]}
    resp=requests.post(f'{BASE}/api/resource/Stock Entry',headers=H,json=body,timeout=120,verify=False)
    if resp.status_code in (200,201):
        nm=(resp.json().get('data') or {}).get('name')
        s=requests.put(f'{BASE}/api/resource/Stock Entry/{nm}',headers=H,json={'docstatus':1},timeout=120,verify=False)
        print(f'  OK {sku} x{qty:.0f} @Rs{rate:.0f} -> {nm} submit {s.status_code}'); done.append((sku,qty,rate,nm))
    else:
        e=resp.text; ix=e.find('"exception":'); print(f'  FAIL {sku}: {(e[ix+12:ix+160] if ix>=0 else e[:160])}')
json.dump(done,open('_mr_approved_done.json','w'))
print(f'\nCreated {len(done)} MR(s). Re-run the driver on the affected REPs to ship them.')
