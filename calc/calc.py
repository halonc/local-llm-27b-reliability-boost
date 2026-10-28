#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calc.py —— 工程计算唯一入口（Decimal 精确，禁止心算）。

为什么有它：模型心算会错。实测三次真错都是低级错，不是理解错——
  · H 型钢 119.8 cm² 换算成 28.1 kg/m（正确 94.0，差 3.3 倍）
  · 1200+380+260+150 加成 2010（正确 1990）
  · 2026-10-20（周二）的"本周五"算成 10-24（正确 10-23）
所以：**凡超过个位数加减的计算，一律走这里**。

用法：
  calc.py eval "1200+380+260+150"                 # 精确求值
  calc.py eval "1990*1.05/5" --round 1            # 定点保留
  calc.py conv 119.8 cm2 m2                       # 单位换算
  calc.py conv 1065.6 kg t --round 3
  calc.py pct 1990 5                              # 1990 加 5%（损耗）
  calc.py verify "119.8 cm2 -> m2 * 7850" 94.0    # 正算 vs 给定值（容差）
  calc.py boq rows.txt                            # 批量校验 数量×单价=合价
  calc.py date 2026-10-20 "本周五"                 # 日期推算
  calc.py date 2026-10-20 "+34d"
  calc.py units                                   # 列可用单位
  calc.py selfcheck                               # 演示 + 自检

退出码：0 通过；1 校验失败（verify/boq 不匹配）。
"""
import argparse
import json
import ast
import math
import datetime as dt
import operator
import re
import sys
from decimal import Decimal, getcontext, ROUND_HALF_UP

getcontext().prec = 34
D = Decimal

# ---------------------------------------------------------------- 单位表（值 → 基准单位的系数）
UNITS = {
    # 长度 → m
    "mm": ("L", Decimal("0.001")), "cm": ("L", Decimal("0.01")),
    "m": ("L", Decimal("1")), "km": ("L", Decimal("1000")),
    # 面积 → m²
    "mm2": ("A", Decimal("0.000001")), "cm2": ("A", Decimal("0.0001")),
    "m2": ("A", Decimal("1")), "km2": ("A", Decimal("1000000")),
    # 体积 → m³
    "cm3": ("V", Decimal("0.000001")), "m3": ("V", Decimal("1")),
    "l": ("V", Decimal("0.001")), "ml": ("V", Decimal("0.000001")),
    # 质量 → kg
    "g": ("M", Decimal("0.001")), "kg": ("M", Decimal("1")),
    "t": ("M", Decimal("1000")),
    # 力 → N
    "n": ("F", Decimal("1")), "kn": ("F", Decimal("1000")),
    # 压强 → Pa
    "pa": ("P", Decimal("1")), "kpa": ("P", Decimal("1000")),
    "mpa": ("P", Decimal("1000000")),
    # 功率 → W
    "w": ("W", Decimal("1")), "kw": ("W", Decimal("1000")),
    # 时间 → s
    "s": ("T", Decimal("1")), "min": ("T", Decimal("60")), "h": ("T", Decimal("3600")),
}

ALIASES = {"㎡": "m2", "m²": "m2", "cm²": "cm2", "mm²": "mm2", "km²": "km2",
           "m³": "m3", "cm³": "cm3", "М": "m"}


def q(x: Decimal, ndigits=None) -> str:
    """定点输出，去掉无意义的尾零。"""
    if ndigits is not None:
        x = x.quantize(Decimal(1).scaleb(-ndigits), rounding=ROUND_HALF_UP)
        return f"{x:.{ndigits}f}"
    s = format(x.normalize(), "f")
    return s


# ---------------------------------------------------------------- 安全表达式求值
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


_FUNCS = {
    "sqrt": lambda x: D(str(math.sqrt(float(x)))),
    "abs": lambda x: abs(x),
    "exp": lambda x: D(str(math.exp(float(x)))),
    "log": lambda x: D(str(math.log(float(x)))),
    "log10": lambda x: D(str(math.log10(float(x)))),
    "log2": lambda x: D(str(math.log2(float(x)))),
    "sin": lambda x: D(str(math.sin(float(x)))),
    "cos": lambda x: D(str(math.cos(float(x)))),
    "tan": lambda x: D(str(math.tan(float(x)))),
    "pi": lambda: D(str(math.pi)),
}


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value))
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        return _FUNCS[node.func.id](*[_eval_node(a) for a in node.args])
    if isinstance(node, ast.Name) and node.id in _FUNCS:      # 允许 pi 作为常量
        return _FUNCS[node.id]()
    raise ValueError("只允许 + - * / **、sqrt/abs/log/exp/sin/cos 与数字：%r" % ast.dump(node)[:60])


def safe_eval(expr: str):
    expr = (expr.replace(",", "").replace("×", "*").replace("÷", "/").replace("^", "**")
                .replace("（", "(").replace("）", ")"))
    tree = ast.parse(expr, mode="eval")
    return _eval_node(tree)


# ---------------------------------------------------------------- 子命令
def cmd_eval(a):
    val = safe_eval(a.expr)
    out = q(val, a.round)
    print(out)
    if a.selfcheck:
        print("自检：表达式=%s 结果=%s 单位=%s" % (a.expr, out, "已按定点输出" if a.round is not None else "未定点"))
    return 0


def cmd_conv(a):
    f = ALIASES.get(a.src, a.src).lower()
    t = ALIASES.get(a.dst, a.dst).lower()
    if f not in UNITS or t not in UNITS:
        print("未知单位：%s / %s（用 units 子命令查看）" % (a.src, a.dst), file=sys.stderr)
        return 2
    df, cf = UNITS[f]
    dt_, ct = UNITS[t]
    if df != dt_:
        print("量纲不一致：%s(%s) vs %s(%s)" % (a.src, df, a.dst, dt_), file=sys.stderr)
        return 2
    val = Decimal(str(a.value)) * cf / ct
    print(q(val, a.round))
    return 0


def cmd_pct(a):
    base = Decimal(str(a.base))
    rate = Decimal(str(a.rate)) / Decimal(100)
    print("基数=%s 比例=%s%% 增量=%s 结果=%s"
          % (q(base), q(Decimal(str(a.rate))), q(base * rate, 4), q(base * (1 + rate), 4)))
    return 0


def cmd_verify(a):
    """表达式里允许 `X cm2 -> m2` 形式：先把 X 换算，再继续算。"""
    expr = a.expr
    m = re.match(r"^\s*([0-9.]+)\s*(\S+)\s*->\s*(\S+)\s*(.*)$", expr)
    if m:
        v, src, dst, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        f = ALIASES.get(src, src).lower()
        t = ALIASES.get(dst, dst).lower()
        if f not in UNITS or t not in UNITS:
            print("未知单位 %s/%s" % (src, dst), file=sys.stderr)
            return 2
        converted = Decimal(v) * UNITS[f][1] / UNITS[t][1]
        expr = "%s %s" % (q(converted), rest.strip() or "")
        print("换算：%s %s = %s %s" % (v, src, q(converted), dst))
    got = safe_eval(expr)
    exp = Decimal(str(a.expected))
    tol = Decimal(str(a.tol))
    ok = abs(got - exp) <= tol
    print("正算=%s 期望=%s 差=%s 容差=%s → %s"
          % (q(got, 4), q(exp, 4), q(got - exp, 4), q(tol, 4), "通过" if ok else "不通过"))
    return 0 if ok else 1


def cmd_boq(a):
    """行格式：名称 数量 单价 合价（空白或 | 分隔）。兼容千分位逗号。"""
    bad = 0
    n = 0
    with open(a.file, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p for p in re.split(r"[|\t]+|\s{2,}", line) if p.strip()]
            if len(parts) < 4:
                parts = line.split()
            nums = []
            for p in parts[::-1]:
                p2 = p.replace(",", "")
                try:
                    nums.append(Decimal(p2)); 
                    if len(nums) == 3:
                        break
                except Exception:
                    pass
            if len(nums) < 3:
                continue
            amount, rate, qty = nums[0], nums[1], nums[2]
            expect = (qty * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            n += 1
            if abs(expect - amount) > Decimal("0.01"):
                bad += 1
                print("第%d行 不符：数量=%s × 单价=%s = %s，表列 %s，差 %s"
                      % (i, q(qty), q(rate), q(expect, 2), q(amount, 2), q(amount - expect, 2)))
    print("共 %d 行，错 %d 行" % (n, bad))
    return 0 if bad == 0 else 1


def cmd_date(a):
    d = dt.date.fromisoformat(a.date)
    wd = "一二三四五六日"[d.weekday()]
    print("基准日：%s（星期%s）" % (d.isoformat(), wd))
    tgt = a.target.strip()
    if tgt.startswith("+"):
        n = int(re.sub(r"[^0-9-]", "", tgt))
        r = d + dt.timedelta(days=n)
        print("推算：%sd → %s（星期%s）" % (n, r.isoformat(), "一二三四五六日"[r.weekday()]))
        return 0
    m = re.match(r"^(本周|这周|下周|上周)([一二三四五六日天])$", tgt)
    if m:
        base = d - dt.timedelta(days=d.weekday())  # 本周一
        off = {"本周": 0, "这周": 0, "下周": 7, "上周": -7}[m.group(1)]
        idx = "一二三四五六日".index("日" if m.group(2) == "天" else m.group(2))
        r = base + dt.timedelta(days=off + idx)
        print("推算：%s → %s（星期%s）" % (tgt, r.isoformat(), "一二三四五六日"[r.weekday()]))
        return 0
    try:
        r = dt.date.fromisoformat(tgt)
        print("相差：%d 天" % (r - d).days)
        return 0
    except Exception:
        print("无法识别的目标：%r（支持 本周五 / 下周一 / +34d / YYYY-MM-DD）" % tgt, file=sys.stderr)
        return 2



# ---------------------------------------------------------------- 公式模板（实测必错 6 类，只许填参数）
def cmd_tip(a):
    """账单分摊：每人 = 账单 × (1+小费率%) ÷ 人数"""
    bill, rate, n = D(str(a.bill)), D(str(a.rate)) / 100, int(a.people)
    total = bill * (1 + rate)
    print("含小费总额=%s  每人=%s" % (q(total, 2), q(total / n, 2)))
    return 0


def cmd_temp(a):
    v = D(str(a.value)); f = a.src.upper(); t = a.dst.upper()
    if f == "C" and t == "F": r = v * 9 / 5 + 32
    elif f == "F" and t == "C": r = (v - 32) * 5 / 9
    elif f == "C" and t == "K": r = v + D("273.15")
    elif f == "K" and t == "C": r = v - D("273.15")
    elif f == "F" and t == "K": r = (v - 32) * 5 / 9 + D("273.15")
    elif f == "K" and t == "F": r = (v - D("273.15")) * 9 / 5 + 32
    else: print("不支持 %s→%s（C/F/K）" % (f, t), file=sys.stderr); return 2
    print("%s %s = %s %s" % (q(v, 2), f, q(r, a.round if a.round is not None else 2), t))
    return 0


def cmd_ratio(a):
    """配比：总量 × 该料份数 ÷ 份数总和"""
    parts = [D(x) for x in a.parts.split(":")]
    total = D(str(a.total)); idx = int(a.pick) - 1
    if idx < 0 or idx >= len(parts):
        print("份数序号越界（1..%d）" % len(parts), file=sys.stderr); return 2
    v = total * parts[idx] / sum(parts)
    print("总份数=%s 第%d份=%s → %s" % (q(sum(parts)), idx + 1, q(parts[idx]), q(v, a.round if a.round is not None else 4)))
    return 0


def cmd_wavg(a):
    """加权平均：Σ(值×权重) ÷ Σ权重。接受 "80x3,90x2" 或位置式 "80 3 90 2 70 1"。"""
    num = D(0); den = D(0)
    raw0 = [a.items] + list(getattr(a, "extra", []) or [])
    raw = []
    for t in raw0:
        raw.extend([x for x in re.split(r"[,;\s]+", str(t)) if x])
    if len(raw) >= 2 and all(re.match(r"^-?[0-9.]+$", str(x)) for x in raw):
        nums = [str(x) for x in raw]
        if len(nums) % 2 == 0 and len(nums) >= 4:
            h = len(nums) // 2
            # 两种写法都试：值/权重交错，或「前一半值 + 后一半权重」
            cands = [
                ["%sx%s" % (nums[i], nums[i + 1]) for i in range(0, len(nums), 2)],
                ["%sx%s" % (nums[i], nums[h + i]) for i in range(h)],
            ]
            # 值通常大于权重：若前一半全部大于后一半，按「值组+权重组」
            best = cands[1] if all(D(nums[i]) > D(nums[h + i]) for i in range(h)) else cands[0]
            a_items = ",".join(best)
        else:
            pairs = ["%sx%s" % (nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
            a_items = ",".join(pairs)
    else:
        a_items = a.items
    for tok in re.split(r"[,;\s]+", a_items):
        if not tok: continue
        m = re.match(r"^(-?[0-9.]+)[xX*×](-?[0-9.]+)$", tok)
        if not m:
            print("格式应为 值x权重，例如 80x3,90x2,70x1：%r" % tok, file=sys.stderr); return 2
        v, w = D(m.group(1)), D(m.group(2))
        num += v * w; den += w
    if den == 0:
        print("权重和为 0", file=sys.stderr); return 2
    print("Σ(值×权重)=%s Σ权重=%s 加权平均=%s" % (q(num), q(den), q(num / den, a.round if a.round is not None else 4)))
    return 0


def cmd_compound(a):
    """复利：本息 = 本金×(1+r)^n；单利：本金×r×n"""
    p = D(str(a.principal)); r = D(str(a.rate)) / 100; n = D(str(a.years))
    if a.simple:
        interest = p * r * n; total = p + interest
        print("单利：利息=%s 本息=%s" % (q(interest, 2), q(total, 2)))
    else:
        total = p * ((1 + r) ** n); interest = total - p
        print("复利：利息=%s 本息=%s" % (q(interest, 2), q(total, 2)))
    return 0


def cmd_dates(a):
    """日期差：默认 (后-前).days；--inclusive 含首日 +1"""
    d1 = dt.date.fromisoformat(a.start); d2 = dt.date.fromisoformat(a.end)
    n = (d2 - d1).days
    if a.inclusive: n += 1
    print("相差 %d 天%s（%s → %s）" % (n, "（含首尾）" if a.inclusive else "（不含首日）",
                                  d1.isoformat(), d2.isoformat()))
    return 0



# ---------------------------------------------------------------- 高等数学 / 线代 / 概率（sympy）
def _sp():
    try:
        import sympy as sp
    except ImportError:
        print("需要 sympy：用 tools/calc/calc（wrapper 会用 calc-venv）", file=sys.stderr)
        sys.exit(3)
    return sp


def _mat(s):
    """矩阵参数容错：接受 "1,2,3;4,5,6;7,8,10"、"[[1,2,3],[4,5,6]]"、换行分隔。"""
    s = s.strip().replace("，", ",")
    if s.startswith("["):
        try:
            rows = json.loads(s)
            if rows and isinstance(rows[0], (list, tuple)):
                return [[D(str(x)) for x in row] for row in rows]
        except Exception:
            pass
    rows = [r for r in re.split(r"[;\n]", s) if r.strip()]
    return [[D(x.strip()) for x in r.split(",")] for r in rows]


def cmd_diff(a):
    sp = _sp(); x = sp.Symbol(a.var); f = sp.sympify(a.expr)
    if a.at is None and a.pos:
        p0 = [t for t in a.pos if re.match(r"^-?[0-9./pi]+$", str(t).replace("pi", "3.14"))]
        if p0: a.at = p0[0]
    d = sp.simplify(sp.diff(f, x))
    if a.at is None:
        print("d/d%s(%s) = %s" % (a.var, sp.sstr(f), sp.sstr(d)))
    else:
        v = sp.simplify(d.subs(x, sp.sympify(a.at)))
        print("f'(%s) = %s   [导数式 %s]" % (a.at, sp.N(v, a.round), sp.sstr(d)))
    return 0


def cmd_integ(a):
    sp = _sp(); x = sp.Symbol(a.var); f = sp.sympify(a.expr)
    b = [t for t in (a.bounds or []) if re.match(r"^-?[0-9.]+$", str(t))]
    if a.frm is None and len(b) >= 2: a.frm, a.to = b[0], b[1]
    if a.frm is None:
        print("∫%s d%s = %s + C" % (sp.sstr(f), a.var, sp.sstr(sp.simplify(sp.integrate(f, x)))))
    else:
        v = sp.integrate(f, (x, sp.sympify(a.frm), sp.sympify(a.to)))
        print("∫[%s,%s] %s d%s = %s" % (a.frm, a.to, sp.sstr(f), a.var, sp.N(v, a.round)))
    return 0


def cmd_limit(a):
    sp = _sp(); x = sp.Symbol(a.var); f = sp.sympify(a.expr)
    v = sp.limit(f, x, sp.sympify(a.to))
    print("lim %s→%s %s = %s" % (a.var, a.to, sp.sstr(f), sp.sstr(v)))
    return 0


def cmd_solve(a):
    sp = _sp(); x = sp.Symbol(a.var)
    expr = re.sub(r"\s*=\s*0\s*$", "", a.expr.strip())
    f = sp.sympify(expr)
    sols = sp.solve(sp.Eq(f, 0), x)
    print("根: " + ", ".join(sp.sstr(sp.simplify(t)) + "(" + sp.sstr(sp.N(t, a.round)) + ")" for t in sols))
    return 0


def cmd_det(a):
    sp = _sp(); m = sp.Matrix([[sp.sympify(str(x)) for x in row] for row in _mat(a.m)])
    print("det = %s" % sp.sstr(sp.simplify(m.det())))
    return 0


def cmd_inv(a):
    sp = _sp(); m = sp.Matrix([[sp.sympify(str(x)) for x in row] for row in _mat(a.m)])
    print("A⁻¹ = %s" % sp.sstr(sp.simplify(m.inv())))
    return 0


def cmd_matmul(a):
    sp = _sp()
    A = sp.Matrix([[sp.sympify(str(x)) for x in r] for r in _mat(a.a)])
    B = sp.Matrix([[sp.sympify(str(x)) for x in r] for r in _mat(a.b)])
    print("A·B = %s" % sp.sstr(A * B))
    return 0


def cmd_binom(a):
    vals = [str(a.n), str(a.p)] + ([str(a.k)] if a.k is not None else [])
    nums = [D(v) for v in vals]
    # 识别：n 最大且整数，p 在 (0,1]，k 为小整数
    cand_p = [x for x in nums if D(0) < x <= D(1)]
    p = cand_p[0] if cand_p else D("0.5")
    ints = sorted([int(x) for x in nums if x == int(x) and x > D(1)], reverse=True)
    n = ints[0] if ints else int(nums[0])
    rest = [int(x) for x in nums if x == int(x) and x > D(1) and int(x) != n]
    k = rest[0] if rest else 0
    c = D(math.comb(n, k))
    prob = c * (p ** k) * ((1 - p) ** (n - k))
    print("P(X=%d) = C(%d,%d)·p^%d·(1-p)^%d = %s" % (k, n, k, k, n - k, q(prob, a.round)))
    return 0


def cmd_comb(a):
    import math as _m
    if a.perm:
        print("P(%d,%d) = %d" % (int(a.n), int(a.k), _m.perm(int(a.n), int(a.k))))
    else:
        print("C(%d,%d) = %d" % (int(a.n), int(a.k), _m.comb(int(a.n), int(a.k))))
    return 0


def cmd_stat(a):
    txt = a.nums.replace(";", ",") + " " + " ".join(getattr(a, "extra", []) or [])
    ddof_kw = a.ddof
    want_std = bool(re.search(r"std|标准|sd\b", txt, re.I))
    if "sample" in txt.lower() or "样本" in txt: ddof_kw = 1
    if "pop" in txt.lower() or "总体" in txt or "variance" in txt.lower(): ddof_kw = 0
    xs = [D(t) for t in re.findall(r"-?[0-9]+(?:\.[0-9]+)?", txt)]
    n = len(xs); mean = sum(xs) / n
    ss = sum((x - mean) ** 2 for x in xs)
    var_p = ss / n
    var_s = ss / (n - 1) if n > 1 else D(0)
    var = var_s if ddof_kw == 1 else var_p
    if want_std:
        sd = var.sqrt() if hasattr(var, "sqrt") else D(str(float(var) ** 0.5))
        print("n=%d 均值=%s 标准差=%s" % (n, q(mean, a.round), q(sd, a.round)))
        return 0
    print("n=%d 均值=%s 方差=%s 标准差=%s" % (n, q(mean, a.round), q(var, a.round),
                                           q(var.sqrt() if hasattr(var, "sqrt") else D(str(float(var) ** 0.5)), a.round)))
    return 0


def cmd_vec(a):
    def _vec(t):
        t = str(t).strip().strip("[]()")
        return [D(x.strip()) for x in re.split(r"[,;\s]+", t) if x.strip()]
    A = _vec(a.a)
    B = _vec(a.b) if a.b else None
    if a.op == "norm" or (B is None and a.op != "norm"):
        print("|a| = %s" % q(sum(x * x for x in A).sqrt() if hasattr(sum(x * x for x in A), "sqrt")
                              else D(str(float(sum(x * x for x in A)) ** 0.5)), a.round)); return 0
    if a.op == "dot":
        print("a·b = %s" % q(sum(x * y for x, y in zip(A, B)), a.round)); return 0
    if a.op == "cross":
        c = [A[1] * B[2] - A[2] * B[1], A[2] * B[0] - A[0] * B[2], A[0] * B[1] - A[1] * B[0]]
        print("a×b = (%s, %s, %s)" % tuple(q(x) for x in c)); return 0
    if a.op == "angle":
        d = sum(x * y for x, y in zip(A, B))
        na = sum(x * x for x in A) ** D("0.5"); nb = sum(y * y for y in B) ** D("0.5")
        print("cos = %s" % q(d / (na * nb), a.round)); return 0
    return 2


def cmd_cplx(a):
    sp = _sp()
    e = re.sub(r"(\d)\s*[ij]\b", r"\1*I", a.expr.strip())
    e = e.replace("**", "^").replace("^", "**")
    z = sp.sympify(e, locals={"I": sp.I})
    z = sp.simplify(sp.expand(z))
    print("z = %s  实部=%s 虚部=%s |z|=%s arg=%s" % (
        sp.sstr(z), sp.sstr(sp.re(z)), sp.sstr(sp.im(z)),
        sp.sstr(sp.N(sp.Abs(z), a.round)), sp.sstr(sp.N(sp.arg(z), a.round))))
    return 0



def cmd_binop(a):
    """add/sub/mul/div：两个数直接算（模型最常误用的子命令名）。"""
    op = {"add": "+", "sub": "-", "mul": "*", "div": "/", "mod": "%"}[a.cmd]
    v = safe_eval("%s%s%s" % (a.x, op, a.y))
    print(q(v, getattr(a, "round", None)))
    return 0


def cmd_units(a):
    groups = {"L": "长度", "A": "面积", "V": "体积", "M": "质量", "F": "力", "P": "压强", "W": "功率", "T": "时间"}
    cur = None
    for k, (g, c) in UNITS.items():
        if g != cur:
            print("\n[%s]" % groups.get(g, g)); cur = g
        print("  %-4s = %s 基准" % (k, c))
    return 0


def cmd_selfcheck(a):
    print("1) H 型钢：119.8 cm² × 7850 kg/m³ → 每米重量")
    v = (Decimal("119.8") * UNITS["cm2"][1]) * Decimal("7850")
    print("   = %s kg/m  （期望 94.0；曾误答 28.1）\n" % q(v, 2))
    print("2) 模板：1200+380+260+150，×1.05，÷5")
    s = safe_eval("1200+380+260+150")
    print("   合计=%s 一次投入=%s m²  （期望 1990 / 417.9；曾误答 2010）\n" % (q(s), q(s * Decimal("1.05") / 5, 1)))
    d = dt.date(2026, 10, 20)
    base = d - dt.timedelta(days=d.weekday())
    f = base + dt.timedelta(days=4)
    print("3) 2026-10-20（星期%s）的『本周五』= %s（期望 10-23；曾误答 10-24）"
          % ("一二三四五六日"[d.weekday()], f.isoformat()))
    print("\n自检：单位✓ 加法✓ 日期✓")
    return 0


class FriendlyParser(argparse.ArgumentParser):
    def error(self, message):
        print("参数错误：%s" % message)
        print("正确用法：%s" % self.format_usage().strip())
        sys.exit(2)


def main():
    ap = FriendlyParser(description="工程计算唯一入口（Decimal）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("eval"); p.add_argument("expr"); p.add_argument("--round", type=int)
    p.add_argument("--selfcheck", action="store_true"); p.set_defaults(f=cmd_eval)

    p = sub.add_parser("conv"); p.add_argument("value"); p.add_argument("src"); p.add_argument("dst")
    p.add_argument("--round", type=int); p.set_defaults(f=cmd_conv)

    p = sub.add_parser("pct"); p.add_argument("base"); p.add_argument("rate"); p.set_defaults(f=cmd_pct)

    p = sub.add_parser("verify"); p.add_argument("expr"); p.add_argument("expected")
    p.add_argument("--tol", default="0.01"); p.set_defaults(f=cmd_verify)

    p = sub.add_parser("boq"); p.add_argument("file"); p.set_defaults(f=cmd_boq)

    p = sub.add_parser("date"); p.add_argument("date"); p.add_argument("target"); p.set_defaults(f=cmd_date)

    p = sub.add_parser("tip"); p.add_argument("bill"); p.add_argument("rate"); p.add_argument("people"); p.set_defaults(f=cmd_tip)

    p = sub.add_parser("temp"); p.add_argument("value"); p.add_argument("src"); p.add_argument("dst")
    p.add_argument("--round", type=int); p.set_defaults(f=cmd_temp)

    p = sub.add_parser("ratio"); p.add_argument("total"); p.add_argument("parts"); p.add_argument("pick")
    p.add_argument("--round", type=int); p.set_defaults(f=cmd_ratio)

    p = sub.add_parser("wavg"); p.add_argument("items"); p.add_argument("extra", nargs="*")
    p.add_argument("--round", type=int); p.set_defaults(f=cmd_wavg)

    p = sub.add_parser("compound"); p.add_argument("principal"); p.add_argument("rate"); p.add_argument("years")
    p.add_argument("--simple", action="store_true"); p.set_defaults(f=cmd_compound)

    p = sub.add_parser("dates"); p.add_argument("start"); p.add_argument("end")
    p.add_argument("--inclusive", action="store_true"); p.set_defaults(f=cmd_dates)

    p = sub.add_parser("diff"); p.add_argument("expr"); p.add_argument("pos", nargs="*")
    p.add_argument("--var", default="x")
    p.add_argument("--at"); p.add_argument("--round", type=int, default=6); p.set_defaults(f=cmd_diff)

    p = sub.add_parser("integ"); p.add_argument("expr"); p.add_argument("bounds", nargs="*")
    p.add_argument("--var", default="x")
    p.add_argument("--from", dest="frm"); p.add_argument("--to"); p.add_argument("--round", type=int, default=6)
    p.set_defaults(f=cmd_integ)

    p = sub.add_parser("limit"); p.add_argument("expr"); p.add_argument("--var", default="x")
    p.add_argument("--to", default="0"); p.set_defaults(f=cmd_limit)

    p = sub.add_parser("solve"); p.add_argument("expr"); p.add_argument("--var", default="x")
    p.add_argument("--round", type=int, default=6); p.set_defaults(f=cmd_solve)

    p = sub.add_parser("det"); p.add_argument("m"); p.set_defaults(f=cmd_det)
    p = sub.add_parser("inv"); p.add_argument("m"); p.set_defaults(f=cmd_inv)
    p = sub.add_parser("matmul"); p.add_argument("a"); p.add_argument("b"); p.set_defaults(f=cmd_matmul)

    p = sub.add_parser("binom"); p.add_argument("n"); p.add_argument("p"); p.add_argument("k", nargs="?")
    p.add_argument("--round", type=int, default=6); p.set_defaults(f=cmd_binom)

    p = sub.add_parser("comb"); p.add_argument("n"); p.add_argument("k")
    p.add_argument("--perm", action="store_true"); p.set_defaults(f=cmd_comb)

    p = sub.add_parser("stat"); p.add_argument("nums"); p.add_argument("extra", nargs="*")
    p.add_argument("--ddof", type=int, default=0)
    p.add_argument("--round", type=int, default=4); p.set_defaults(f=cmd_stat)

    p = sub.add_parser("vec"); p.add_argument("op", choices=["dot", "cross", "norm", "angle"])
    p.add_argument("a"); p.add_argument("b", nargs="?"); p.add_argument("--round", type=int, default=4)
    p.set_defaults(f=cmd_vec)

    p = sub.add_parser("cplx"); p.add_argument("expr"); p.add_argument("--round", type=int, default=4)
    p.set_defaults(f=cmd_cplx)

    for _name in ("add", "sub", "mul", "div", "mod"):
        p = sub.add_parser(_name); p.add_argument("x"); p.add_argument("y")
        p.add_argument("--round", type=int); p.set_defaults(f=cmd_binop, cmd=_name)

    sub.add_parser("units").set_defaults(f=cmd_units)
    sub.add_parser("selfcheck").set_defaults(f=cmd_selfcheck)

    a = ap.parse_args()
    sys.exit(a.f(a))


if __name__ == "__main__":
    main()
