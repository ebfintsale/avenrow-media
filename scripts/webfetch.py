"""Fetch public web pages on the runner and report listing links / titles (JSON)."""
import re, json, urllib.request, html

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
                                               "Accept": "text/html,application/xhtml+xml"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        code = getattr(e, "code", None)
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        return code or str(e), body

def run_webfetch(job, out_dir):
    res = []
    for u in job["urls"]:
        st, body = get(u)
        links = {}
        for m in re.finditer(r'etsy\.com/listing/(\d+)/([a-z0-9\-]+)', body):
            links.setdefault(m.group(1), m.group(2))
        titles = re.findall(r'<title[^>]*>(.*?)</title>', body, re.S)
        cnt = re.findall(r'All\s*\(?(\d+)\)?', body)[:3]
        res.append({"url": u, "status": st, "bytes": len(body),
                    "title": html.unescape(titles[0].strip()) if titles else None,
                    "count_hint": cnt, "listings": links,
                    "head": body[:200] if not links else ""})
    return {"id": job["id"], "type": "webfetch", "results": res}
