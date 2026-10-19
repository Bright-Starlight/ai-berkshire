#!/usr/bin/env python3
"""把仓库里已入库的报告生成一个适合墨水屏阅读的静态站点。

输入：reports/index.json（由 tools/reports_index.py 生成）、投资炼丹/、实盘记录/ 下已纳入 Git 的 Markdown。
输出：site/ 目录，纯 HTML，无框架；按公司、专题、时间、类型、公众号发表五个维度建索引，另有站内搜索与 RSS。

用法：python3 tools/build_site.py [--out site]
依赖：markdown、pypinyin（pip install markdown pypinyin）
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import quote

import markdown
from pypinyin import Style, lazy_pinyin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_URL = "https://github.com/xbtlin/ai-berkshire"
SITE_NAME = "AI Berkshire 研究阅读"
FRONT = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.S)
H1 = re.compile(r"^#\s+(.+?)\s*$", re.M)
DATE8 = re.compile(r"(20[2-3]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])")
ASSET_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".csv", ".json", ".txt", ".html"}
TYPE_ORDER = ["深度系列", "研究", "财报", "估值仓位", "组织管理", "横评对比", "公众号", "筛选", "底稿"]
NOISE_BUCKETS = {"筛选池"}


def sh(args):
    return subprocess.check_output(args, cwd=ROOT).decode("utf-8", "replace")


def tracked(prefix):
    out = subprocess.check_output(["git", "ls-files", "-z", "--", prefix], cwd=ROOT)
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]


def page_id(path):
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]


def slug(name):
    s = re.sub(r"[^0-9A-Za-z一-鿿]+", "-", name).strip("-")
    return s or page_id(name)


def initial(name):
    c = name.strip()[:1]
    if not c:
        return "#"
    if re.match(r"[A-Za-z]", c):
        return c.upper()
    if re.match(r"[一-鿿]", c):
        return lazy_pinyin(c, style=Style.FIRST_LETTER)[0].upper()
    return "#"


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8", errors="replace") as f:
        return f.read()


# ---------- 收集条目 ----------

def collect():
    items = []
    idx = json.load(open(os.path.join(ROOT, "reports", "index.json"), encoding="utf-8"))
    for r in idx["reports"]:
        if not os.path.exists(os.path.join(ROOT, r["path"])):
            continue
        items.append({
            "title": r["title"], "path": r["path"], "bucket": r["bucket"], "group": r["group"],
            "series": r.get("series", ""), "type": r.get("type", "研究"), "date": r.get("date", ""),
        })
    for p in tracked("投资炼丹/"):
        if not p.endswith(".md") or p.endswith("README.md"):
            continue
        parts = p.split("/")
        group = parts[1] if len(parts) > 2 else "其他"
        text = read(p)
        m = H1.search(FRONT.sub("", text))
        name = os.path.basename(p)[:-3]
        dm = DATE8.match(name)
        date = "%s-%s-%s" % dm.groups() if dm else ""
        title = m.group(1).strip() if m else re.sub(r"^\d{8}-", "", name).replace("-", " ")
        pub = re.search(r"发表标题：(.+)", text)
        if pub:
            title = pub.group(1).strip()
        items.append({"title": title, "path": p, "bucket": "公众号发表", "group": group,
                      "series": "", "type": "公众号", "date": date})
    for p in tracked("实盘记录/"):
        if not p.endswith(".md"):
            continue
        text = read(p)
        m = H1.search(FRONT.sub("", text))
        name = os.path.basename(p)[:-3]
        dm = DATE8.search(name)
        date = "%s-%s-%s" % dm.groups() if dm else git_date(p)
        items.append({"title": m.group(1).strip() if m else name, "path": p, "bucket": "实盘记录",
                      "group": "实盘记录", "series": "", "type": "实盘", "date": date})
    for it in items:
        it["id"] = page_id(it["path"])
        it["url"] = "r/%s.html" % it["id"]
    items.sort(key=lambda x: (x["date"] or "0000"), reverse=True)
    return items


def git_date(path):
    try:
        out = sh(["git", "log", "-1", "--format=%cs", "--", path]).strip()
        return out
    except subprocess.CalledProcessError:
        return ""


# ---------- HTML 外壳 ----------

CSS = """
html{font-size:20px;-webkit-text-size-adjust:100%}
body{margin:0 auto;padding:0 1rem 3rem;max-width:44rem;color:#000;background:#fff;
font-family:-apple-system,"PingFang SC","Hiragino Sans GB","Noto Sans CJK SC","Source Han Sans SC","Microsoft YaHei",sans-serif;line-height:1.75}
html.s1{font-size:17px}html.s3{font-size:24px}html.s4{font-size:28px}
a{color:#000;text-decoration:underline;text-underline-offset:3px}
nav.top{padding:.7rem 0;border-bottom:3px solid #000;font-size:.95rem;line-height:2.2}
nav.top a{margin-right:.9rem;white-space:nowrap}
nav.top .size{float:right}nav.top .size a{margin:0 0 0 .4rem;text-decoration:none;border:1px solid #000;padding:0 .4rem}
.crumb{font-size:.85rem;color:#333;margin:.8rem 0 0}
h1{font-size:1.55rem;line-height:1.35;margin:.8rem 0 .4rem}
h2{font-size:1.25rem;line-height:1.4;border-bottom:1px solid #777;padding-bottom:.15rem;margin-top:1.8rem}
h3{font-size:1.08rem;margin-top:1.4rem}
.meta{color:#333;font-size:.85rem;margin:.2rem 0 1rem}
ul.list{list-style:none;padding:0;margin:0}
ul.list li{padding:.65rem 0;border-bottom:1px solid #bbb}
ul.list li a{display:block}
ul.list .meta{margin:0}
.grid a.btn{display:inline-block;border:2px solid #000;padding:.45rem .9rem;margin:.3rem .6rem .3rem 0;text-decoration:none;font-weight:600}
.table-wrap{overflow-x:auto;margin:1rem 0}
table{border-collapse:collapse;font-size:.82rem;line-height:1.45}
th,td{border:1px solid #555;padding:.3rem .5rem;vertical-align:top;text-align:left}
th{background:#e8e8e8}
blockquote{border-left:4px solid #000;margin:1rem 0;padding:.1rem 1rem;color:#111}
pre{overflow-x:auto;border:1px solid #888;padding:.6rem;font-size:.8rem;line-height:1.4}
code{font-size:.9em}
img{max-width:100%;height:auto}
hr{border:0;border-top:1px solid #888}
.idx{columns:2;column-gap:2rem}
.idx li{break-inside:avoid}
details{margin:.6rem 0}summary{cursor:pointer;padding:.4rem 0;font-weight:600}
footer{margin-top:3rem;border-top:3px solid #000;padding-top:.8rem;font-size:.85rem;color:#333}
input.q{font-size:1.1rem;width:100%;padding:.5rem;border:2px solid #000;box-sizing:border-box}
@media (max-width:600px){html{font-size:18px}.idx{columns:1}}
"""

SIZE_JS = """
(function(){var k='aib-size',h=document.documentElement;var s=localStorage.getItem(k);if(s)h.className=s;
window.setSize=function(c){h.className=c;localStorage.setItem(k,c);return false;}})();
"""


def shell(title, body, depth, crumb=""):
    rel = "../" * depth
    nav = (
        '<nav class="top"><a href="{r}index.html">首页</a><a href="{r}companies/index.html">公司</a>'
        '<a href="{r}topics/index.html">专题</a><a href="{r}dates/index.html">时间</a>'
        '<a href="{r}types/index.html">类型</a><a href="{r}wechat/index.html">公众号</a>'
        '<a href="{r}search.html">搜索</a>'
        '<span class="size">字号 <a href="#" onclick="return setSize(\'s1\')">小</a>'
        '<a href="#" onclick="return setSize(\'\')">中</a><a href="#" onclick="return setSize(\'s3\')">大</a>'
        '<a href="#" onclick="return setSize(\'s4\')">特大</a></span></nav>'
    ).format(r=rel)
    crumb_html = '<div class="crumb">%s</div>' % crumb if crumb else ""
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>%s · %s</title><link rel="stylesheet" href="%sstyle.css">'
        '<link rel="alternate" type="application/rss+xml" title="%s" href="%sfeed.xml">'
        '<script>%s</script></head><body>%s%s%s'
        '<footer>%s ｜ <a href="%s">GitHub 仓库</a> ｜ 生成时间 %s</footer></body></html>'
    ) % (html.escape(title), SITE_NAME, rel, SITE_NAME, rel, SIZE_JS, nav, crumb_html, body,
         SITE_NAME, REPO_URL, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))


def li(it, depth, show_group=True):
    rel = "../" * depth
    bits = [it["date"] or "日期不详"]
    if show_group and it["group"]:
        bits.append(it["group"])
    if it["type"]:
        bits.append(it["type"])
    return '<li><a href="%s%s">%s</a><div class="meta">%s</div></li>' % (
        rel, it["url"], html.escape(it["title"]), " · ".join(html.escape(b) for b in bits))


def ul(items, depth, show_group=True, limit=None):
    rows = items if limit is None else items[:limit]
    return '<ul class="list">%s</ul>' % "".join(li(i, depth, show_group) for i in rows)


# ---------- Markdown → HTML ----------

LINK_ATTR = re.compile(r'(href|src)="([^"]+)"')


def convert(it, by_path, out_dir):
    text = FRONT.sub("", read(it["path"]))
    m1 = H1.search(text)
    if m1 and (m1.start() < 1500 or m1.group(1).strip() == it["title"]):
        text = text[:m1.start()] + text[m1.end():]
    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists", "toc"],
                           extension_configs={"toc": {"toc_depth": "2-3"}})
    body = md.convert(text)
    base = os.path.dirname(it["path"])
    missing = []

    def fix(m):
        attr, url = m.group(1), m.group(2)
        if re.match(r"^(https?:|mailto:|#|data:)", url):
            return m.group(0)
        clean = url.split("#")[0].split("?")[0]
        target = os.path.normpath(os.path.join(base, clean)).replace("\\", "/")
        if target in by_path:
            return '%s="../%s"' % (attr, by_path[target]["url"])
        ext = os.path.splitext(target)[1].lower()
        src = os.path.join(ROOT, target)
        if ext in ASSET_EXT and os.path.isfile(src):
            dst = os.path.join(out_dir, "files", target)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
            return '%s="../files/%s"' % (attr, quote(target))
        if os.path.exists(src):
            return '%s="%s/blob/main/%s"' % (attr, REPO_URL, quote(target))
        missing.append(url)
        return m.group(0)

    body = LINK_ATTR.sub(fix, body)
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    toc = md.toc if md.toc and md.toc.count("<li>") >= 3 else ""
    return body, toc


# ---------- 各类页面 ----------

def write(out_dir, rel_path, content):
    p = os.path.join(out_dir, rel_path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


def build(out_dir):
    items = collect()
    by_path = {i["path"]: i for i in items}
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    write(out_dir, "style.css", CSS)
    write(out_dir, ".nojekyll", "")

    companies = defaultdict(list)
    topics = defaultdict(list)
    screens = defaultdict(list)
    wechat = defaultdict(list)
    months = defaultdict(list)
    types = defaultdict(list)
    for it in items:
        if it["bucket"] == "公司":
            companies[it["group"]].append(it)
        elif it["bucket"] == "公众号发表":
            wechat[it["group"]].append(it)
            companies[it["group"]].append(it)
        elif it["bucket"] == "筛选池":
            screens[it["group"]].append(it)
        elif it["bucket"] == "实盘记录":
            topics["实盘记录"].append(it)
        else:
            topics[it["group"]].append(it)
        if it["date"]:
            months[it["date"][:7]].append(it)
        types[it["type"]].append(it)

    comp_url = {c: "companies/%s/index.html" % slug(c) for c in companies}
    topic_url = {t: "topics/%s/index.html" % slug(t) for t in topics}
    screen_url = {s: "screens/%s/index.html" % slug(s) for s in screens}

    def group_link(it, depth):
        rel = "../" * depth
        if it["bucket"] in ("公司", "公众号发表") and it["group"] in comp_url:
            return '<a href="%s%s">%s</a>' % (rel, comp_url[it["group"]], html.escape(it["group"]))
        if it["bucket"] == "筛选池" and it["group"] in screen_url:
            return '<a href="%s%s">%s</a>' % (rel, screen_url[it["group"]], html.escape(it["group"]))
        g = "实盘记录" if it["bucket"] == "实盘记录" else it["group"]
        if g in topic_url:
            return '<a href="%s%s">%s</a>' % (rel, topic_url[g], html.escape(g))
        return html.escape(g)

    # 报告页
    for it in items:
        body, toc = convert(it, by_path, out_dir)
        same = [x for x in (companies.get(it["group"]) or topics.get(it["group"]) or screens.get(it["group"]) or [])
                if x["id"] != it["id"]][:12]
        meta = " · ".join(x for x in [it["date"], it["type"]] if x)
        head = "<h1>%s</h1><div class=\"meta\">%s ｜ %s ｜ <a href=\"%s/blob/main/%s\">GitHub 原文</a></div>" % (
            html.escape(it["title"]), group_link(it, 1), html.escape(meta), REPO_URL, quote(it["path"]))
        if toc:
            head += "<details><summary>目录</summary>%s</details>" % toc
        tail = ""
        if same:
            tail = "<h2>同一专题的其他报告</h2>" + ul(same, 1, show_group=False)
        crumb = '<a href="../index.html">首页</a> › %s' % group_link(it, 1)
        write(out_dir, it["url"], shell(it["title"], head + '<article>%s</article>' % body + tail, 1, crumb))

    # 公司索引与公司页
    def company_page(name, rows):
        groups = defaultdict(list)
        for r in rows:
            key = "公众号发表" if r["bucket"] == "公众号发表" else r["type"]
            groups[key].append(r)
        order = ["公众号发表"] + TYPE_ORDER
        parts = ["<h1>%s</h1><div class=\"meta\">共 %d 篇，最近更新 %s</div>" % (
            html.escape(name), len(rows), rows[0]["date"] if rows and rows[0]["date"] else "—")]
        for k in order + [k for k in groups if k not in order]:
            if k in groups:
                parts.append("<h2>%s（%d）</h2>%s" % (html.escape(k), len(groups[k]), ul(groups[k], 2, show_group=False)))
        return "".join(parts)

    for c, rows in companies.items():
        write(out_dir, comp_url[c], shell(c, company_page(c, rows), 2,
                                          '<a href="../../index.html">首页</a> › <a href="../index.html">公司</a>'))
    letters = defaultdict(list)
    for c in companies:
        letters[initial(c)].append(c)
    top = sorted(companies, key=lambda c: -len(companies[c]))[:24]
    body = "<h1>按公司</h1><div class=\"meta\">%d 家公司，%d 篇报告</div><h2>报告最多的公司</h2><div class=\"grid\">%s</div>" % (
        len(companies), sum(len(v) for v in companies.values()),
        "".join('<a class="btn" href="../%s">%s %d</a>' % (comp_url[c], html.escape(c), len(companies[c])) for c in top))
    body += "<h2>全部公司（按拼音首字母）</h2>"
    for L in sorted(letters):
        names = sorted(letters[L], key=lambda c: lazy_pinyin(c))
        body += "<h3>%s</h3><ul class=\"list idx\">%s</ul>" % (L, "".join(
            '<li><a href="../%s">%s</a><div class="meta">%d 篇 · 最近 %s</div></li>' % (
                comp_url[c], html.escape(c), len(companies[c]), companies[c][0]["date"] or "—") for c in names))
    write(out_dir, "companies/index.html", shell("按公司", body, 1))

    # 专题
    def simple_group_page(name, rows, depth, crumb):
        by_series = defaultdict(list)
        for r in rows:
            by_series[r["series"] or ""].append(r)
        parts = ["<h1>%s</h1><div class=\"meta\">共 %d 篇</div>" % (html.escape(name), len(rows))]
        if len(by_series) > 1:
            for s in sorted(by_series, key=lambda s: (s == "", s), reverse=True):
                parts.append("<h2>%s（%d）</h2>%s" % (html.escape(s or "主报告"), len(by_series[s]), ul(by_series[s], depth, show_group=False)))
        else:
            parts.append(ul(rows, depth, show_group=False))
        return shell(name, "".join(parts), depth, crumb)

    for t, rows in topics.items():
        write(out_dir, topic_url[t], simple_group_page(t, rows, 2, '<a href="../../index.html">首页</a> › <a href="../index.html">专题</a>'))
    for s, rows in screens.items():
        write(out_dir, screen_url[s], simple_group_page(s, rows, 2, '<a href="../../index.html">首页</a> › <a href="../../topics/index.html">专题</a>'))
    tnames = sorted(topics, key=lambda t: topics[t][0]["date"] or "", reverse=True)
    body = "<h1>专题与横评</h1><ul class=\"list\">%s</ul>" % "".join(
        '<li><a href="../%s">%s</a><div class="meta">%d 篇 · 最近 %s</div></li>' % (
            topic_url[t], html.escape(t), len(topics[t]), topics[t][0]["date"] or "—") for t in tnames)
    body += "<h2>筛选池与召回池</h2><ul class=\"list\">%s</ul>" % "".join(
        '<li><a href="../%s">%s</a><div class="meta">%d 篇 · 最近 %s</div></li>' % (
            screen_url[s], html.escape(s), len(screens[s]), screens[s][0]["date"] or "—")
        for s in sorted(screens, key=lambda s: screens[s][0]["date"] or "", reverse=True))
    write(out_dir, "topics/index.html", shell("专题", body, 1))

    # 时间
    years = defaultdict(list)
    for m in months:
        years[m[:4]].append(m)
    body = "<h1>按时间</h1>"
    for y in sorted(years, reverse=True):
        body += "<h2>%s 年</h2><div class=\"grid\">%s</div>" % (y, "".join(
            '<a class="btn" href="%s.html">%s 月 %d</a>' % (m, int(m[5:]), len(months[m])) for m in sorted(years[y], reverse=True)))
    write(out_dir, "dates/index.html", shell("按时间", body, 1))
    for m, rows in months.items():
        main = [r for r in rows if r["bucket"] not in NOISE_BUCKETS]
        noise = [r for r in rows if r["bucket"] in NOISE_BUCKETS]
        body = "<h1>%s 年 %d 月</h1><div class=\"meta\">%d 篇</div>%s" % (m[:4], int(m[5:]), len(rows), ul(main, 1))
        if noise:
            body += "<details><summary>筛选池与召回池日报（%d）</summary>%s</details>" % (len(noise), ul(noise, 1))
        write(out_dir, "dates/%s.html" % m, shell("%s 年 %d 月" % (m[:4], int(m[5:])), body, 1,
                                                   '<a href="../index.html">首页</a> › <a href="index.html">时间</a>'))

    # 类型
    tlist = [t for t in TYPE_ORDER if t in types] + [t for t in types if t not in TYPE_ORDER]
    body = "<h1>按类型</h1><div class=\"grid\">%s</div>" % "".join(
        '<a class="btn" href="%s.html">%s %d</a>' % (slug(t), html.escape(t), len(types[t])) for t in tlist)
    write(out_dir, "types/index.html", shell("按类型", body, 1))
    for t in tlist:
        rows = types[t]
        main = [r for r in rows if r["bucket"] not in NOISE_BUCKETS]
        noise = [r for r in rows if r["bucket"] in NOISE_BUCKETS]
        body = "<h1>%s</h1><div class=\"meta\">%d 篇</div>%s" % (html.escape(t), len(rows), ul(main, 1))
        if noise:
            body += "<details><summary>筛选池与召回池（%d）</summary>%s</details>" % (len(noise), ul(noise, 1))
        write(out_dir, "types/%s.html" % slug(t), shell(t, body, 1, '<a href="../index.html">首页</a> › <a href="index.html">类型</a>'))

    # 公众号发表
    wrows = sorted((r for rows in wechat.values() for r in rows), key=lambda r: r["date"], reverse=True)
    body = "<h1>公众号发表版</h1><div class=\"meta\">%d 篇，正文为公众号发表版本</div>%s" % (len(wrows), ul(wrows, 1))
    write(out_dir, "wechat/index.html", shell("公众号", body, 1))

    # 搜索
    sdata = [{"t": i["title"], "g": i["group"], "k": i["type"], "d": i["date"], "u": i["url"]} for i in items]
    write(out_dir, "search.json", json.dumps(sdata, ensure_ascii=False, separators=(",", ":")))
    body = ("<h1>搜索</h1><p>输入公司名、关键词或日期（如 2026-09），按标题、公司、类型匹配。</p>"
            '<input class="q" id="q" type="search" placeholder="例如：拼多多 财报" autofocus>'
            '<div class="meta" id="n"></div><ul class="list" id="out"></ul>'
            "<script>var D=null;function esc(s){return s.replace(/[&<>\"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]})}"
            "function run(){var q=document.getElementById('q').value.trim().toLowerCase();var out=document.getElementById('out'),n=document.getElementById('n');"
            "if(!q){out.innerHTML='';n.textContent='';return}var ws=q.split(/\\s+/);var r=D.filter(function(x){var s=(x.t+' '+x.g+' '+x.k+' '+x.d).toLowerCase();return ws.every(function(w){return s.indexOf(w)>=0})});"
            "n.textContent='共 '+r.length+' 条'+(r.length>200?'，只显示前 200 条':'');out.innerHTML=r.slice(0,200).map(function(x){return '<li><a href=\"'+x.u+'\">'+esc(x.t)+'</a><div class=\"meta\">'+esc([x.d,x.g,x.k].filter(Boolean).join(' · '))+'</div></li>'}).join('')}"
            "fetch('search.json').then(function(r){return r.json()}).then(function(d){D=d;document.getElementById('q').addEventListener('input',run);run()});</script>")
    write(out_dir, "search.html", shell("搜索", body, 0))

    # 首页
    recent, per_group = [], defaultdict(int)
    for i in items:
        if i["bucket"] in NOISE_BUCKETS or i["type"] == "底稿" or i["series"] == "evidence":
            continue
        if per_group[i["group"]] >= 2:
            continue
        per_group[i["group"]] += 1
        recent.append(i)
        if len(recent) >= 30:
            break
    body = "<h1>%s</h1><p class=\"meta\">%d 篇报告 · %d 家公司 · 最近更新 %s</p>" % (
        SITE_NAME, len(items), len(companies), items[0]["date"] if items else "—")
    body += "<div class=\"grid\">%s</div>" % "".join(
        '<a class="btn" href="%s">%s</a>' % (u, t) for u, t in [
            ("companies/index.html", "按公司"), ("topics/index.html", "专题与横评"), ("dates/index.html", "按时间"),
            ("types/index.html", "按类型"), ("wechat/index.html", "公众号发表版"), ("search.html", "搜索")])
    body += "<h2>最近更新</h2>" + ul(recent, 0)
    body += "<h2>报告最多的公司</h2><div class=\"grid\">%s</div>" % "".join(
        '<a class="btn" href="%s">%s %d</a>' % (comp_url[c], html.escape(c), len(companies[c])) for c in top[:16])
    write(out_dir, "index.html", shell("首页", body, 0))
    write(out_dir, "404.html", shell("没有这一页", "<h1>没有这一页</h1><p><a href=\"index.html\">回首页</a></p>", 0))

    # RSS
    feed_items = [i for i in items if i["bucket"] not in NOISE_BUCKETS][:50]
    base = "https://xbtlin.github.io/ai-berkshire/"
    rss = ['<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>%s</title><link>%s</link><description>投资研究报告</description>' % (SITE_NAME, base)]
    for i in feed_items:
        rss.append("<item><title>%s</title><link>%s%s</link><guid>%s%s</guid><pubDate>%s</pubDate><description>%s</description></item>" % (
            html.escape(i["title"]), base, i["url"], base, i["url"],
            datetime.strptime(i["date"], "%Y-%m-%d").strftime("%a, %d %b %Y 00:00:00 +0000") if i["date"] else "",
            html.escape(" · ".join(x for x in [i["group"], i["type"]] if x))))
    rss.append("</channel></rss>")
    write(out_dir, "feed.xml", "".join(rss))

    print("生成 %d 篇报告页，%d 家公司，%d 个专题，%d 个月份 -> %s" % (len(items), len(companies), len(topics) + len(screens), len(months), out_dir))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "site"))
    args = ap.parse_args()
    build(args.out)
