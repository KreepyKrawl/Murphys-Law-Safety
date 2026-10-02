#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, os, re, subprocess, sys
from collections import Counter, defaultdict
from datetime import datetime, date
from pathlib import Path
from urllib.request import Request, urlopen

EXP="RCX-PB-GC-0001"
URL="https://cdn.powerball.com/v01/media/powerball-pre-test.pdf"
START=date(2015,10,7)
CUTOFF=date(2026,9,28)
OUT=Path("artifact")
OUT.mkdir(exist_ok=True)

def sha256(b:bytes)->str: return hashlib.sha256(b).hexdigest()
def split_for(iso):
    b=hashlib.sha256(f"{EXP}|{iso}".encode()).digest()[0]%10
    return b, ("development" if b<=5 else "validation" if b<=7 else "sealed_test")

req=Request(URL, headers={"User-Agent":"Mozilla/5.0 RCX-PB-GC-0001"})
with urlopen(req, timeout=90) as r:
    pdf=r.read()
(OUT/"powerball-pre-test.pdf").write_bytes(pdf)
pdf_sha=sha256(pdf)

subprocess.run(["pdftotext","-layout","-nopgbrk",str(OUT/"powerball-pre-test.pdf"),str(OUT/"powerball-pre-test-layout.txt")],check=True)
text=(OUT/"powerball-pre-test-layout.txt").read_text("utf-8",errors="replace")
text_sha=sha256(text.encode())

marker_re=re.compile(r"POWERBALL.*NUMBERS DRAWN\s+5/69\s*\+\s*1/26",re.I)
mm=marker_re.search(text)
if not mm:
    raise SystemExit("matrix marker not found")
matrix=text[mm.start():]
(OUT/"current_matrix_extraction.txt").write_text(matrix,encoding="utf-8")

# Standard event row. Keep raw token strings as well as normalized ints.
row_re=re.compile(
 r"(?P<date>\d{2}/\d{2}/\d{2})\s+"
 r"(?P<b1>\d{1,2})\s+(?P<b2>\d{1,2})\s+(?P<b3>\d{1,2})\s+(?P<b4>\d{1,2})\s+(?P<b5>\d{1,2})\s+"
 r"(?P<wm>\d{1,2})\s+(?P<ws>\d{1,2})\s+"
 r"(?P<pb>\d{1,2})\s+(?P<pp>--|\d{1,2})\s+"
 r"(?P<pm>\d{1,2})\s+(?P<ps>\d{1,2})\s+"
 r"(?P<typ>Pre-test|Post-test|Draw(?:-[A-Za-z0-9]+)?)\b"
)
event_hint=re.compile(r"\b(?:Pre-test|Post-test|Draw(?:-[A-Za-z0-9]+)?)\b")
dateish=re.compile(r"^\s*(\S+)\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+(?:--|\d{1,2})\s+\d{1,2}\s+\d{1,2}\s+(?:Pre-test|Post-test|Draw(?:-[A-Za-z0-9]+)?)\b")

rows=[]
anoms=[]
for line_no,line in enumerate(matrix.splitlines(),1):
    raw=line.rstrip("\n")
    matches=list(row_re.finditer(raw))
    if not matches:
        if event_hint.search(raw):
            dm=dateish.search(raw)
            anoms.append({"matrix_line":line_no,"kind":"UNPARSED_EVENT_LINE","raw_line":raw,"date_token": dm.group(1) if dm else None})
        continue
    # In case extraction ever concatenates multiple event rows on one physical line, preserve each match.
    for seq_in_line,m in enumerate(matches):
        try:
            iso=datetime.strptime(m["date"],"%m/%d/%y").date().isoformat()
        except ValueError:
            anoms.append({"matrix_line":line_no,"kind":"INVALID_DATE","raw_line":raw,"raw_date":m["date"]})
            continue
        d=date.fromisoformat(iso)
        if d<START or d>CUTOFF: continue
        typ=m["typ"]
        if typ=="Post-test": continue
        bucket,split=split_for(iso)
        rec={
          "matrix_line":line_no,"match_in_line":seq_in_line,"raw_line":raw,"raw_date":m["date"],"date":iso,
          "wm_raw":m["wm"],"ws_raw":m["ws"],"pb_raw":m["pb"],"pp_raw":m["pp"],"pm_raw":m["pm"],"ps_raw":m["ps"],
          "wm":int(m["wm"]),"ws":int(m["ws"]),"pb":int(m["pb"]),"pm":int(m["pm"]),"ps":int(m["ps"]),
          "type_raw":typ,"type_class":"Draw" if typ.startswith("Draw") else typ,
          "ball1":int(m["b1"]),"ball2":int(m["b2"]),"ball3":int(m["b3"]),"ball4":int(m["b4"]),"ball5":int(m["b5"]),
          "ball1_raw":m["b1"],"ball2_raw":m["b2"],"ball3_raw":m["b3"],"ball4_raw":m["b4"],"ball5_raw":m["b5"],
          "split_bucket":bucket,"split":split
        }
        rec["balls"]=[rec[f"ball{i}"] for i in range(1,6)]
        rec["white_object_ids"]=[f"WS:{rec['ws']}:B:{x}" for x in rec["balls"]]
        rec["powerball_object_id"]=f"PS:{rec['ps']}:B:{rec['pb']}"
        rows.append(rec)

rows.sort(key=lambda r:(r["date"],r["matrix_line"],r["match_in_line"]))
by=defaultdict(list)
for r in rows: by[r["date"]].append(r)

for d,rr in sorted(by.items()):
    for i,r in enumerate(rr): r["sequence_index"]=i
    pres=[r for r in rr if r["type_class"]=="Pre-test"]
    draws=[r for r in rr if r["type_class"]=="Draw"]
    if len(pres)!=4: anoms.append({"date":d,"kind":"PRETEST_COUNT","count":len(pres),"blocking":True})
    if len(draws)!=1: anoms.append({"date":d,"kind":"DRAW_COUNT","count":len(draws),"blocking":True})
    for r in rr:
        if len(set(r["balls"]))!=5: anoms.append({"date":d,"matrix_line":r["matrix_line"],"kind":"DUPLICATE_WHITE_LABEL_WITHIN_ROW","blocking":True})
        if not all(1<=x<=69 for x in r["balls"]): anoms.append({"date":d,"matrix_line":r["matrix_line"],"kind":"WHITE_OUT_OF_RANGE","blocking":True})
        if not 1<=r["pb"]<=26: anoms.append({"date":d,"matrix_line":r["matrix_line"],"kind":"POWERBALL_OUT_OF_RANGE","blocking":True})
    for fld in ("wm","ws","pm","ps"):
        vals=[r[fld] for r in rr]
        if len(set(vals))>1:
            anoms.append({"date":d,"kind":"SOURCE_REGIME_DISCONTINUITY","field":fld,"values_in_source_order":vals,"blocking":False})
    if len({r["split"] for r in rr})!=1:
        anoms.append({"date":d,"kind":"SPLIT_INCONSISTENCY","blocking":True})

# Check date continuity against expected Powerball schedule for current matrix.
# Wed+Sat until 2021-08-21, then Mon+Wed+Sat from 2021-08-23. This is only a completeness check, not a model feature.
from datetime import timedelta
expected=[]
d=START
while d<=CUTOFF:
    if d < date(2021,8,23):
        if d.weekday() in (2,5): expected.append(d.isoformat())
    else:
        if d.weekday() in (0,2,5): expected.append(d.isoformat())
    d+=timedelta(days=1)
obs=sorted(by)
missing=sorted(set(expected)-set(obs))
extra=sorted(set(obs)-set(expected))
if missing: anoms.append({"kind":"EXPECTED_DRAW_DATES_MISSING","dates":missing,"count":len(missing),"blocking":True})
if extra: anoms.append({"kind":"UNEXPECTED_DRAW_DATES_PRESENT","dates":extra,"count":len(extra),"blocking":True})

# Write full parsed rows.
fields=[
 "matrix_line","match_in_line","raw_line","raw_date","date","split_bucket","split","sequence_index",
 "type_raw","type_class","wm","ws","pm","ps","pp_raw","ball1","ball2","ball3","ball4","ball5","pb",
 "white_object_ids","powerball_object_id"
]
with (OUT/"PRIMARY_QUALIFIED.csv").open("w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
    for r in rows:
        q={k:r.get(k) for k in fields}
        q["white_object_ids"]="|".join(r["white_object_ids"])
        w.writerow(q)

def write_split(name, pred, mask_draw=False):
    with (OUT/name).open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in rows:
            if not pred(r): continue
            q={k:r.get(k) for k in fields}; q["white_object_ids"]="|".join(r["white_object_ids"])
            if mask_draw and r["type_class"]=="Draw":
                for k in ["raw_line","wm","ws","pm","ps","pp_raw","ball1","ball2","ball3","ball4","ball5","pb","white_object_ids","powerball_object_id"]:
                    q[k]="MASKED"
            w.writerow(q)
write_split("DEVELOPMENT.csv",lambda r:r["split"]=="development")
write_split("VALIDATION.csv",lambda r:r["split"]=="validation")
write_split("SEALED_WORKING_VIEW.csv",lambda r:r["split"]=="sealed_test",True)

truth=[{
 "date":r["date"],"type_raw":r["type_raw"],"wm":r["wm"],"ws":r["ws"],"pm":r["pm"],"ps":r["ps"],
 "balls":r["balls"],"pb":r["pb"],"pp_raw":r["pp_raw"],"matrix_line":r["matrix_line"],
 "white_object_ids":r["white_object_ids"],"powerball_object_id":r["powerball_object_id"]
} for r in rows if r["split"]=="sealed_test" and r["type_class"]=="Draw"]
truth_bytes=(json.dumps(truth,sort_keys=True,separators=(",",":"))+"\n").encode()
(OUT/"SEALED_TRUTH.json").write_bytes(truth_bytes)
(OUT/"SEALED_TRUTH.sha256").write_text(sha256(truth_bytes)+"  SEALED_TRUTH.json\n")
(OUT/"ANOMALY_LEDGER.json").write_text(json.dumps(anoms,indent=2,sort_keys=True)+"\n")

blocking=[a for a in anoms if a.get("blocking", a["kind"] in {"UNPARSED_EVENT_LINE","INVALID_DATE","PRETEST_COUNT","DRAW_COUNT","DUPLICATE_WHITE_LABEL_WITHIN_ROW","WHITE_OUT_OF_RANGE","POWERBALL_OUT_OF_RANGE","SPLIT_INCONSISTENCY","EXPECTED_DRAW_DATES_MISSING","UNEXPECTED_DRAW_DATES_PRESENT"})]
split_dates=Counter(rr[0]["split"] for rr in by.values() if rr)
summary={
 "experiment":EXP,"source_url":URL,"source_sha256":pdf_sha,"extracted_text_sha256":text_sha,
 "matrix_start":START.isoformat(),"cutoff":CUTOFF.isoformat(),
 "pdf_bytes":len(pdf),"matrix_text_chars":len(matrix),"primary_rows":len(rows),"dates":len(by),
 "expected_dates":len(expected),"missing_dates":len(missing),"unexpected_dates":len(extra),
 "date_splits":dict(sorted(split_dates.items())),
 "anomaly_count":len(anoms),"blocking_anomaly_count":len(blocking),
 "sealed_truth_rows":len(truth),"sealed_truth_sha256":sha256(truth_bytes),
 "scoring_authorized":len(blocking)==0
}
(OUT/"QUALIFICATION_SUMMARY.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
(OUT/"BLOCKING_ANOMALIES.json").write_text(json.dumps(blocking,indent=2,sort_keys=True)+"\n")
print(json.dumps(summary,indent=2,sort_keys=True))
