import io,sys,re,time,subprocess,json
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',line_buffering=True)
PY=r'C:\Users\accou\Documents\Projects\SOLARA-Data\venv\Scripts\python.exe'
remaining=open(sys.argv[1]).read().split()
shipped={}; terminal={}
# reasons that will NOT be fixed by retrying (surface, don't loop) — NEEDS-MR needs per-SKU user approval;
# reserved-negative/dn/mapper/SO need out-of-band handling. awb-fail & network stay retryable.
TERM=('NEEDS-MR','reserved-negative','no-rate','zero-mrp','mapper','SO-FAIL','so-submit')
def is_terminal(err):
    e=str(err or '');
    return e=='dn' or e.startswith('dn:') or any(k in e for k in TERM)
for rnd in range(8):
    if not remaining: break
    open('_rem_round.txt','w').write(' '.join(remaining))
    print(f'--- round {rnd+1}: {len(remaining)} REPs ---',flush=True)
    p=subprocess.run([PY,'process_reps_mrp.py','_rem_round.txt'],capture_output=True,text=True,encoding='utf-8',errors='replace')
    out=(p.stdout or '')+(p.stderr or '')
    done=[]
    for m in re.finditer(r'OK (REP-\S+)\s+(\S+)\s+(?:MR\[[^\]]*\]\s+)?(\S+)\s+(\S+)\s+declaredMRP=(\S+)',out):
        rep,dn,awb,courier,mrp=m.group(1),m.group(2),m.group(3),m.group(4),m.group(5)
        shipped[rep]=(dn,awb,courier,mrp); done.append(rep)
        print(f'  OK {rep} {dn} {awb} {courier} Rs{mrp}',flush=True)
    remaining=[r for r in remaining if r not in shipped]
    # drop terminal failures from the retry set so they don't loop across rounds
    try:
        for x in json.load(open('_rem_round_results.json')):
            rep=x[0]; err=x[-1]
            if rep in remaining and len(x)<6 and is_terminal(err):
                terminal[rep]=err; print(f'  TERMINAL {rep}: {err}',flush=True)
    except Exception: pass
    remaining=[r for r in remaining if r not in terminal]
    if not done:
        tail=out.strip().splitlines()[-2:] if out.strip() else ['(no output)']
        print('  no progress; tail:',' | '.join(tail)[:160],flush=True)
        time.sleep(5)
print(f'\n=== shipped {len(shipped)} | terminal {len(terminal)} | still-pending {len(remaining)}: {remaining} ===',flush=True)
if terminal:
    print('--- TERMINAL (need out-of-band handling; NOT retried) ---',flush=True)
    for r,e in terminal.items(): print(f'  {r}: {e}',flush=True)
json.dump(shipped,open('_resilient_result.json','w'))
json.dump(terminal,open('_resilient_terminal.json','w'))
