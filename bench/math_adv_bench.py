#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""高等数学 / 线性代数 / 概率统计 60 题（14 类）。

标准答案全部由 Python 算（math + numpy），模型只回一行「答案=…」。
用法：
  python3 tools/model-ab/math_adv_bench.py bank
  python3 tools/model-ab/math_adv_bench.py run --model <id> --tag paiton-adv
"""
import argparse, json, math, os, re, sys, time, urllib.request
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
M = math

# (类别, 题目, 表达式, 保留位数)
BANK = [
    # 1 导数求值
    ("导数", "f(x)=x³-3x²+2x，求 f'(2)。", "3*2**2-6*2+2", 0),
    ("导数", "f(x)=x²·eˣ，求 f'(1)（保留 4 位）。", "(2*1*M.e**1 + 1**2*M.e**1)", 4),
    ("导数", "f(x)=ln(x²+1)，求 f'(1)。", "2*1/(1**2+1)", 0),
    ("导数", "f(x)=sin(2x)，求 f'(π/4)（保留 4 位）。", "2*M.cos(2*M.pi/4)", 4),
    ("导数", "f(x)=x/(x+1)，求 f'(2)（保留 4 位）。", "1/(2+1)**2", 4),
    # 2 定积分
    ("定积分", "求 ∫₀¹ 3x² dx。", "1**3-0**3", 0),
    ("定积分", "求 ∫₀^π sin x dx。", "-M.cos(M.pi)+M.cos(0)", 0),
    ("定积分", "求 ∫₁² (1/x) dx（保留 4 位）。", "M.log(2)-M.log(1)", 4),
    ("定积分", "求 ∫₀¹ eˣ dx（保留 4 位）。", "M.e**1-M.e**0", 4),
    ("定积分", "求 ∫₀² (x²+1) dx（保留 4 位）。", "(2**3/3+2)-(0+0)", 4),
    # 3 极限
    ("极限", "求 lim(x→0) sin(x)/x。", "1", 0),
    ("极限", "求 lim(x→∞) (1+1/x)^x（保留 5 位）。", "M.e", 5),
    ("极限", "求 lim(x→0) (1-cos x)/x²（保留 4 位）。", "0.5", 4),
    ("极限", "求 lim(x→∞) (3x²+2x)/(2x²-1)（保留 4 位）。", "1.5", 4),
    ("极限", "求 lim(x→0) (eˣ-1)/x。", "1", 0),
    # 4 级数
    ("级数", "求 Σ(n=1→∞) 1/2ⁿ。", "1", 0),
    ("级数", "求 Σ(n=1→∞) 1/(n(n+1))。", "1", 0),
    ("级数", "求 Σ(n=0→∞) (1/3)ⁿ（保留 4 位）。", "1/(1-1/3)", 4),
    ("级数", "求 Σ(n=1→10) n。", "sum(range(1,11))", 0),
    ("级数", "求 Σ(n=1→∞) 1/n²（保留 5 位）。", "M.pi**2/6", 5),
    # 5 行列式
    ("行列式", "求 det[[3,1],[2,4]]。", "3*4-1*2", 0),
    ("行列式", "求 det[[1,2,3],[4,5,6],[7,8,10]]。", "np.linalg.det(np.array([[1,2,3],[4,5,6],[7,8,10]],dtype=float))", 0),
    ("行列式", "求 det[[2,0,0],[0,3,0],[0,0,4]]。", "24", 0),
    ("行列式", "求 det[[1,1,1],[1,2,3],[1,4,9]]。", "np.linalg.det(np.array([[1,1,1],[1,2,3],[1,4,9]],dtype=float))", 0),
    ("行列式", "求 det[[5,2],[1,3]]。", "5*3-2*1", 0),
    # 6 矩阵
    ("矩阵", "A=[[1,2],[3,4]]，B=[[5,6],[7,8]]，求 (A·B) 第 1 行第 1 列元素。", "(np.array([[1,2],[3,4]])@np.array([[5,6],[7,8]]))[0,0]", 0),
    ("矩阵", "A=[[1,2],[3,4]]，求 trace(A)。", "1+4", 0),
    ("矩阵", "A=[[1,2],[3,4]]，求 det(A)。", "1*4-2*3", 0),
    ("矩阵", "A=[[1,2],[3,4]]，求 A⁻¹ 第 1 行第 1 列元素（保留 4 位）。", "np.linalg.inv(np.array([[1,2],[3,4]],dtype=float))[0,0]", 4),
    ("矩阵", "A=[[1,2],[3,4]]，求 (A²) 第 2 行第 2 列元素。", "(np.array([[1,2],[3,4]])@np.array([[1,2],[3,4]]))[1,1]", 0),
    # 7 三角函数
    ("三角函数", "sin(π/6) = ?（保留 4 位）", "M.sin(M.pi/6)", 4),
    ("三角函数", "cos(π/3) = ?（保留 4 位）", "M.cos(M.pi/3)", 4),
    ("三角函数", "tan(π/4) = ?（保留 4 位）", "M.tan(M.pi/4)", 4),
    ("三角函数", "sin(π/2) = ?", "1", 0),
    ("三角函数", "cos(2π/3) = ?（保留 4 位）", "M.cos(2*M.pi/3)", 4),
    # 8 对数指数
    ("对数指数", "log₂(32) = ?", "M.log2(32)", 0),
    ("对数指数", "ln(e³) = ?", "3", 0),
    ("对数指数", "log₁₀(1000) = ?", "3", 0),
    ("对数指数", "解 2ˣ=32，x = ?", "M.log2(32)", 0),
    ("对数指数", "e^(ln 7) = ?", "7", 0),
    # 9 排列组合
    ("排列组合", "C(10,3) = ?", "M.comb(10,3)", 0),
    ("排列组合", "P(6,2) = ?", "M.perm(6,2)", 0),
    ("排列组合", "C(8,4) = ?", "M.comb(8,4)", 0),
    ("排列组合", "C(52,5) = ?", "M.comb(52,5)", 0),
    ("排列组合", "P(5,5) = ?", "M.perm(5,5)", 0),
    # 10 概率
    ("概率", "抛均匀硬币 5 次，恰有 3 次正面的概率（保留 4 位）。", "M.comb(5,3)/2**5", 4),
    ("概率", "掷一个公平六面骰，得到偶数的概率（保留 2 位）。", "3/6", 2),
    ("概率", "从 52 张牌中抽 1 张得到红桃的概率（保留 2 位）。", "13/52", 2),
    ("概率", "二项分布 n=10, p=0.3，P(X=4)（保留 4 位）。", "M.comb(10,4)*0.3**4*0.7**6", 4),
    ("概率", "3 人中有至少 2 人同月生日的概率（保留 4 位）。", "1-12*11*10/12**3", 4),
    # 11 统计
    ("统计", "数据 2,4,4,4,5,5,7,9 的总体方差（保留 2 位）。", "np.var([2,4,4,4,5,5,7,9])", 2),
    ("统计", "数据 2,4,4,4,5,5,7,9 的总体标准差（保留 2 位）。", "np.std([2,4,4,4,5,5,7,9])", 2),
    ("统计", "数据 1,2,3,4,5 的样本方差（除以 n-1，保留 2 位）。", "np.var([1,2,3,4,5], ddof=1)", 2),
    ("统计", "数据 10,20,30 的算术均值。", "np.mean([10,20,30])", 0),
    ("统计", "数据 3,5,7,9 的总体标准差（保留 4 位）。", "np.std([3,5,7,9])", 4),
    # 12 向量
    ("向量", "a=(1,2,3)，b=(4,5,6)，求 a·b。", "np.dot([1,2,3],[4,5,6])", 0),
    ("向量", "a=(1,2,3)，b=(4,5,6)，求 a×b 的第 1 个分量。", "np.cross([1,2,3],[4,5,6])[0]", 0),
    ("向量", "a=(1,2,3)，求 |a|（保留 4 位）。", "np.linalg.norm([1,2,3])", 4),
    ("向量", "a=(1,2,3)，b=(4,5,6)，求夹角余弦（保留 4 位）。", "np.dot([1,2,3],[4,5,6])/(np.linalg.norm([1,2,3])*np.linalg.norm([4,5,6]))", 4),
    ("向量", "a=(1,2,3)，b=(4,5,6)，求 |a+b|（保留 4 位）。", "np.linalg.norm(np.array([1,2,3])+np.array([4,5,6]))", 4),
    # 13 复数
    ("复数", "(2+3i)(1-2i) 的实部 = ?", "(2*1-3*(-2))", 0),
    ("复数", "(2+3i)(1-2i) 的虚部 = ?", "(2*(-2)+3*1)", 0),
    ("复数", "|3+4i| = ?", "abs(complex(3,4))", 0),
    ("复数", "(1+i)² 的实部 = ?", "(complex(1,1)**2).real", 0),
    ("复数", "arg(1+i)（弧度，保留 4 位）。", "M.pi/4", 4),
    # 14 多项式求根
    ("多项式", "x²-5x+6=0 的较大根 = ?", "max(np.roots([1,-5,6]))", 0),
    ("多项式", "x²+2x-3=0 的较大根 = ?", "max(np.roots([1,2,-3]))", 0),
    ("多项式", "x³-6x²+11x-6=0 的三个根之和 = ?", "sum(np.roots([1,-6,11,-6]))", 0),
    ("多项式", "x²-2x-1=0 的正根（保留 4 位）。", "max(np.roots([1,-2,-1]))", 4),
    ("多项式", "2x²-8x+6=0 的较小根 = ?", "min(np.roots([2,-8,6]))", 0),
]


def ans_of(expr, nd):
    v = eval(expr, {"M": M, "np": np, "math": M, "sum": sum, "abs": abs, "max": max, "min": min,
                    "range": range, "complex": complex})
    if nd == 0:
        return int(round(float(v)))
    return format(round(float(v), nd), ".%df" % nd)


PROMPT_HEAD = ("请解题。**只输出一行**，格式严格为：答案=<数值>\n"
               "不要写步骤、不要解释、不要加粗。\n\n")


def num(s):
    m = re.findall(r"-?\d[\d,]*\.?\d*", s.replace(",", ""))
    return [float(x) for x in m] if m else []


def run(a):
    rows = []; t0 = time.time()
    for i, (cat, prompt, expr, nd) in enumerate(BANK):
        std = ans_of(expr, nd)
        body = json.dumps({"model": a.model, "messages": [{"role": "user", "content": PROMPT_HEAD + prompt}],
                           "max_tokens": 150, "temperature": 0, "stream": False,
                           "chat_template_kwargs": {"enable_thinking": False}}).encode()
        req = urllib.request.Request(a.endpoint.rstrip("/") + "/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        tt = time.time()
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=300).read())
            out = (d["choices"][0]["message"].get("content") or "").strip()
        except Exception as e:
            out = "ERROR %s" % e
        dur = time.time() - tt
        cand = re.search(r"答案\s*[=:：]\s*(.+)", out)
        seg = cand.group(1) if cand else out
        ns = num(seg); target = float(std)
        ok = bool(ns) and abs(ns[0] - target) <= max(0.006, abs(target) * 0.002)
        rows.append(dict(i=i, cat=cat, prompt=prompt, std=str(std), out=out, ok=ok, dur=dur))
    per = {}
    for r in rows:
        p = per.setdefault(r["cat"], [0, 0]); p[1] += 1; p[0] += 1 if r["ok"] else 0
    print("\n== 按类别 ==")
    for k, (x, y) in per.items():
        print("  %-8s %2d/%2d %s" % (k, x, y, "OK" if x == y else "有错"))
    tot = sum(1 for r in rows if r["ok"])
    print("\n  合计 %d/%d（%.1f%%），用时 %.1f min" % (tot, len(rows), 100.0 * tot / len(rows), (time.time() - t0) / 60))
    print("\n== 错题 ==")
    for r in rows:
        if not r["ok"]:
            print("  [%s] %s\n    标准=%s 模型=%s" % (r["cat"], r["prompt"][:44], r["std"], r["out"][:60].replace("\n", " ")))
    json.dump(dict(tag=a.tag, model=a.model, per=per, rows=rows),
              open(os.path.join(HERE, "mathadv-%s.json" % a.tag), "w"), ensure_ascii=False, indent=2)
    print("\n明细: tools/model-ab/mathadv-%s.json" % a.tag)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("action", choices=["bank", "run"])
    ap.add_argument("--endpoint", default="http://127.0.0.1:8080/v1")
    ap.add_argument("--model", default="R9700-Qwen3.8-27B-W3A4-HIP"); ap.add_argument("--tag", default="paiton-adv")
    a = ap.parse_args()
    if a.action == "bank":
        for i, (c, p, e, nd) in enumerate(BANK):
            print("%3d [%-6s] %-44s -> %s" % (i, c, p[:44], ans_of(e, nd)))
    else:
        run(a)


if __name__ == "__main__":
    main()
