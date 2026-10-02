#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, re, subprocess
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

EXP="RCX-PB-GC-0001"
URL="https://cdn.powerball.com/v01/media/powerball-pre-test.pdf"
START=date(2015,10,7)
CUTOFF=date(2026,9,28)
OUT=Path("artifact"); OUT.mkdir(exist_ok=True)
VAULT=Path("vault"); VAULT.mkdir(exist_ok=True)
sha=lambda b: hashlib.sha256(b).hexdigest()

def split_for(iso):
    b=hashlib.sha256(f"{EXP}|{iso}".encode()).digest()[0]%10
    return b, ("development" if b<=5 else "validation" if b<=7 else "sealed_test")

def norm_date(tok):
    # v0.3 syntax-only repair: MM/DDYY -> MM/DD/YY iff uniquely valid.
    repair=None
    if re.fullmatch(r"\d{2}/\d{4}",tok):
        cand=tok[:5]+"/"+tok[5:]
        try: datetime.strptime(cand,"%m/%d/%y")
        except ValueError: pass
        else:
            repair={"kind":"SYNTAX_ONLY_DATE_NORMALIZATION","raw_date":tok,"normalized_date":cand,"blocking":False}
            tok=cand
    try: return datetime.strptime(tok,"%m/%d/%y").date().isoformat(), repair
    except ValueError: return None, repair

req=Request(URL,headers={"User-Agent":"Mozilla/5.0 RCX-PB-GC-0001"})
with urlopen(req,timeout=90) as r: pdf=r.read()
(VAULT/"powerball-pre-test.pdf").write_bytes(pdf)
pdf_sha=sha(pdf)
subprocess.run(["pdftotext","-layout","-nopgbrk",str(VAULT/"powerball-pre-test.pdf"),str(VAULT/"powerball-pre-test-layout.txt")],check=True)
text=(VAULT/"powerball-pre-test-layout.txt").read_text("utf-8",errors="replace")
text_sha=sha(text.encode())
m=re.search(r"POWERBALL.*NUMBERS DRAWN\s+5/69\s*\+\s*1/26",text,re.I)
if not m: raise SystemExit("matrix marker not found")
matrix=text[m.start():]
(VAULT/"current_matrix_extraction.txt").write_text(matrix,encoding="utf-8")

row_re=re.compile(
 r"(?P<date>\d{2}/(?:\d{2}/\d{2}|\d{4}))\s+"
 r"(?P<b1>\d{1,2})\s+(?P<b2>\d{1,2})\s+(?P<b3>\d{1,2})\s+(?P<b4>\d{1,2})\s+(?P<b5>\d{1,2})\s+"
 r"(?P<wm>\d{1,2})\s+(?P<ws>\d{1,2})\s+(?P<pb>\d{1,2})\s+(?P<pp>--|\d{1,2})\s+"
 r"(?P<pm>\d{1,2})\s+(?P<ps>\d{1,2})\s+(?P<typ>Pre-test|Post-test|Draw(?:-[A-Za-z0-9]+)?)\b")
event_hint=re.compile(r"\b(?:Pre-test|Post-test|Draw(?:-[A-Za-z0-9]+)?)\b")

rows=[]; anoms=[]
for ln,raw in enumerate(matrix.splitlines(),1):
    matches=list(row_re.finditer(raw))
    if not matches:
        if event_hint.search(raw):
            anoms.append({"matrix_line":ln,"kind":"UNPARSED_EVENT_LINE","raw_line":raw,"blocking":True})
        continue
    for mi,x in enumerate(matches):
        iso,repair=norm_date(x["date"])
        if repair:
            repair.update({"matrix_line":ln,"raw_line":raw}); anoms.append(repair)
        if iso is None:
            anoms.append({"matrix_line":ln,"kind":"INVALID_DATE","raw_date":x["date"],"raw_line":raw,"blocking":True}); continue
        d=date.fromisoformat(iso)
        if d<START or d>CUTOFF: continue
        if x["typ"]=="Post-test": continue
        bucket,sp=split_for(iso)
        r={"matrix_line":ln,"match_in_line":mi,"raw_line":raw,"raw_date":x["date"],"date":iso,
           "split_bucket":bucket,"split":sp,"type_raw":x["typ"],"type_class":"Draw" if x["typ"].startswith("Draw") else x["typ"],
           "wm":int(x["wm"]),"ws":int(x["ws"]),"pm":int(x["pm"]),"ps":int(x["ps"]),"pp_raw":x["pp"],
           "pb":int(x["pb"])}
        for i in range(1,6): r[f"ball{i}"]=int(x[f"b{i}"])
        r["balls"]=[r[f"ball{i}"] for i in range(1,6)]
        r["white_object_ids"]=[f"WS:{r['ws']}:B:{v}" for v in r["balls"]]
        r["powerball_object_id"]=f"PS:{r['ps']}:B:{r['pb']}"
        rows.append(r)

rows.sort(key=lambda r:(r["date"],r["matrix_line"],r["match_in_line"]))
by=defaultdict(list)
for r in rows: by[r["date"]].append(r)
for d,rr in sorted(by.items()):
    for i,r in enumerate(rr): r["sequence_index"]=i
    pre=[r for r in rr if r["type_class"]=="Pre-test"]; dr=[r for r in rr if r["type_class"]=="Draw"]
    if len(pre)!=4: anoms.append({"date":d,"kind":"PRETEST_COUNT","count":len(pre),"blocking":True})
    if len(dr)!=1: anoms.append({"date":d,"kind":"DRAW_COUNT","count":len(dr),"blocking":True})
    for r in rr:
        if len(set(r["balls"]))!=5: anoms.append({"date":d,"matrix_line":r["matrix_line"],"kind":"DUPLICATE_WHITE_LABEL_WITHIN_ROW","blocking":True})
        if not all(1<=v<=69 for v in r["balls"]): anoms.append({"date":d,"matrix_line":r["matrix_line"],"kind":"WHITE_OUT_OF_RANGE","blocking":True})
        if not 1<=r["pb"]<=26: anoms.append({"date":d,"matrix_line":r["matrix_line"],"kind":"POWERBALL_OUT_OF_RANGE","blocking":True})
    for fld in ("wm","ws","pm","ps"):
        vals=[r[fld] for r in rr]
        if len(set(vals))>1: anoms.append({"date":d,"kind":"SOURCE_REGIME_DISCONTINUITY","field":fld,"values_in_source_order":vals,"blocking":False})
    if len({r["split"] for r in rr})!=1: anoms.append({"date":d,"kind":"SPLIT_INCONSISTENCY","blocking":True})

expected=[]; d=START
while d<=CUTOFF:
    if (d<date(2021,8,23) and d.weekday() in (2,5)) or (d>=date(2021,8,23) and d.weekday() in (0,2,5)):
        expected.append(d.isoformat())
    d+=timedelta(days=1)
missing=sorted(set(expected)-set(by)); extra=sorted(set(by)-set(expected))
if missing: anoms.append({"kind":"EXPECTED_DRAW_DATES_MISSING","count":len(missing),"dates":missing,"blocking":True})
if extra: anoms.append({"kind":"UNEXPECTED_DRAW_DATES_PRESENT","count":len(extra),"dates":extra,"blocking":True})

fields=["matrix_line","match_in_line","raw_line","raw_date","date","split_bucket","split","sequence_index","type_raw","type_class",
        "wm","ws","pm","ps","pp_raw","ball1","ball2","ball3","ball4","ball5","pb","white_object_ids","powerball_object_id"]
def export(name,pred,mask_sealed_draw=False):
    with (OUT/name).open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in rows:
            if not pred(r): continue
            q={k:r.get(k) for k in fields}; q["white_object_ids"]="|".join(r["white_object_ids"])
            if mask_sealed_draw and r["split"]=="sealed_test" and r["type_class"]=="Draw":
                for k in ("raw_line","wm","ws","pm","ps","pp_raw","ball1","ball2","ball3","ball4","ball5","pb","white_object_ids","powerball_object_id"):
                    q[k]="MASKED"
            w.writerow(q)

export("DEVELOPMENT.csv",lambda r:r["split"]=="development")
export("VALIDATION.csv",lambda r:r["split"]=="validation")
export("SEALED_WORKING_VIEW.csv",lambda r:r["split"]=="sealed_test",True)
export("PRIMARY_WORKING_VIEW.csv",lambda r:True,True)

truth=[{"date":r["date"],"wm":r["wm"],"ws":r["ws"],"pm":r["pm"],"ps":r["ps"],"balls":r["balls"],"pb":r["pb"],"pp_raw":r["pp_raw"],
        "matrix_line":r["matrix_line"],"white_object_ids":r["white_object_ids"],"powerball_object_id":r["powerball_object_id"]}
       for r in rows if r["split"]=="sealed_test" and r["type_class"]=="Draw"]
truth_bytes=(json.dumps(truth,sort_keys=True,separators=(",",":"))+"\n").encode()
(VAULT/"SEALED_TRUTH.json").write_bytes(truth_bytes)
(VAULT/"SEALED_TRUTH.sha256").write_text(sha(truth_bytes)+"  SEALED_TRUTH.json\n")

blocking=[a for a in anoms if a.get("blocking",False)]
split_dates=Counter(rr[0]["split"] for rr in by.values() if rr)
summary={"experiment":EXP,"source_url":URL,"source_sha256":pdf_sha,"extracted_text_sha256":text_sha,
         "matrix_start":START.isoformat(),"cutoff":CUTOFF.isoformat(),"pdf_bytes":len(pdf),"primary_rows":len(rows),"dates":len(by),
         "expected_dates":len(expected),"missing_dates":len(missing),"unexpected_dates":len(extra),"date_splits":dict(sorted(split_dates.items())),
         "anomaly_count":len(anoms),"blocking_anomaly_count":len(blocking),"sealed_truth_rows":len(truth),
         "sealed_truth_sha256":sha(truth_bytes),"scoring_authorized":len(blocking)==0}
(OUT/"QUALIFICATION_SUMMARY.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
(OUT/"ANOMALY_LEDGER.json").write_text(json.dumps(anoms,indent=2,sort_keys=True)+"\n")
(OUT/"BLOCKING_ANOMALIES.json").write_text(json.dumps(blocking,indent=2,sort_keys=True)+"\n")
(OUT/"SOURCE_HASHES.txt").write_text(f"{pdf_sha}  powerball-pre-test.pdf\n{text_sha}  powerball-pre-test-layout.txt\n{sha(truth_bytes)}  SEALED_TRUTH.json\n")
print(json.dumps(summary,indent=2,sort_keys=True))
