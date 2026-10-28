#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只跑历史崩过的题：从已有结果文件提取 ok=False 的题，带 calc 工具重测。"""
import json, os, re, subprocess, sys, time, urllib.request
from decimal import Decimal as D
HERE=os.path.dirname(os.path.abspath(__file__))
URL="http://127.0.0.1:8080/v1/chat/completions"; MODEL="R9700-Qwen3.8-27B-W3A4-HIP"
TOOL={"type":"function","function":{"name":"calc",
 "description":"唯一计算工具。四则运算用 eval，argv 传一个表达式字符串，例如 [\"4827+3916\"]",
 "parameters":{"type":"object","properties":{
   "cmd":{"type":"string","description":"eval/conv/pct/tip/temp/ratio/wavg/compound/dates/diff/integ/limit/solve/det/inv/matmul/binom/comb/stat/vec/cplx"},
   "argv":{"type":"array","items":{"type":"string"}}},"required":["cmd","argv"]}}}

def call(msgs, tc="auto"):
    b={"model":MODEL,"messages":msgs,"max_tokens":700,"temperature":0,"stream":False,
       "tools":[TOOL],"tool_choice":tc,"chat_template_kwargs":{"enable_thinking":False}}
    r=urllib.request.Request(URL,data=json.dumps(b).encode(),headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(r,timeout=300).read())

def calc(argv):
    r=subprocess.run(["tools/calc/calc"]+[str(x) for x in argv],capture_output=True,text=True,timeout=60)
    return (r.stdout or "").strip() or "(空)"

def ask(prompt):
    msgs=[{"role":"user","content":prompt}]; used=None
    for rnd in range(3):
        d=call(msgs, tc=("none" if rnd == 2 else "auto")); m=d["choices"][0]["message"]; tcs=m.get("tool_calls") or []
        if not tcs: return (m.get("content") or ""), used
        out=None
        for t in tcs:
            a=json.loads(t["function"]["arguments"])
            out=calc([a.get("cmd","eval")]+[str(x) for x in a.get("argv",[])])
            used="%s %s"%(a.get("cmd")," ".join(str(x) for x in a.get("argv",[])))
        msgs=msgs+[m]+[{"role":"tool","tool_call_id":t["id"],"content":out} for t in tcs]
    return "", used

def num(s):
    s = s.replace("\u2212", "-").replace("\u2013", "-").replace("\uff0d", "-")   # 全角/数学减号
    m=re.findall(r"-?\d[\d,]*\.?\d*", s.replace(",","")); return [D(x) for x in m] if m else []

def ok_num(std, ans):
    ns=num(ans)
    if not ns: return False
    t=D(str(std)); tol=max(D("0.006"),abs(t)*D("0.002"))
    return any(abs(x-t)<=tol for x in ns)   # 答案里任一数字命中即可（题面数字先出现不影响）

fails=[]
for f,tag in (("math-paiton.json","daily"),("mathadv-paiton-adv.json","adv")):
    p=os.path.join(HERE,f)
    if not os.path.exists(p): continue
    for r in json.load(open(p))["rows"]:
        if not r["ok"]: fails.append(dict(bank=tag,cat=r["cat"],prompt=r["prompt"],std=r["std"]))

print("历史崩题 %d 道（日常 %d / 高数 %d）\n"%(len(fails),
      sum(1 for x in fails if x["bank"]=="daily"), sum(1 for x in fails if x["bank"]=="adv")))
fixed=0; rows=[]
for i,r in enumerate(fails,1):
    ans,tool=ask(r["prompt"])
    good=ok_num(r["std"],ans)
    fixed+=good
    rows.append(dict(**r,ok=good,ans=ans[:120],tool=tool))
    print("%2d %-8s %-6s | %-34s | std=%-9s ans=%-28s | %s"%(
        i,r["cat"],r["bank"],r["prompt"][:34],r["std"],(ans or "")[:28].replace("\n"," "),
        ("FIXED" if good else "still FAIL")+" ["+str(tool)+"]"))
print("\n修复 %d/%d"%(fixed,len(fails)))
json.dump(rows,open(os.path.join(HERE,"retest-fails.json"),"w"),ensure_ascii=False,indent=1)
