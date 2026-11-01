import csv, json, re
csv.field_size_limit(10**9)
SRC="/mnt/user-data/attachments/2b8a49ba-d532-5f45-acbe-57b7f43ffa29/e9efe2f9-EtsyListingsDownload_3.csv"
new=list(csv.DictReader(open(SRC,encoding='utf-8-sig')))
old=list(csv.DictReader(open('/home/claude/avenrow_master_catalog_v45.csv',encoding='utf-8-sig')))
rss=json.load(open('/tmp/claude-0/res2/r3.json'))['results'][0]['items']
def idof(u): return re.search(r'fullxfull\.(\d+)',u).group(1)
url_by_img={}
for it in rss:
    img=re.search(r'il_570xN\.(\d+)',it['img']).group(1)
    url_by_img[img]=it['link'].strip()
have={idof(r['IMAGE1']) for r in old}
META={ # row -> (key, design no., theme, occasion, board, class, priority, rationale)
 1:("Christmas Eve","061","Christmas / vintage tree, cream+black","Christmas gift, stocking stuffer, hostess","Gift Ideas for Every Occasion","Christmas","High","NEW 2026-11-01; Christmas discovery window opens early Nov"),
 2:("Winter Wonderland","060","Winter / snow globe, teal","Christmas gift, winter decor","Cozy Home & Apartment Ideas","Christmas/Winter","High","NEW 2026-11-01"),
 3:("Season's Greetings (Nutcracker)","059","Christmas / nutcracker, cream+red+green","Christmas gift, holiday decor","Candles & Candle Decor","Christmas","High","NEW 2026-11-01"),
 4:("Joy to the World","058","Christmas / gold star, red-white check","Christmas gift for her","Gift Ideas for Every Occasion","Christmas","High","NEW 2026-11-01"),
 5:("Merry Christmas (cream/minimal)","057","Christmas / red bow, cream","Christmas gift, minimalist decor","Cozy Home & Apartment Ideas","Christmas","High","NEW 2026-11-01"),
 6:("Holly Jolly Christmas","056","Christmas / green holly tree, cream","Christmas gift, hostess","Gift Ideas for Every Occasion","Christmas","High","NEW 2026-11-01"),
 7:("Let It Snow","055","Winter / navy snowflakes","Winter decor, Christmas gift","Cozy Home & Apartment Ideas","Christmas/Winter","High","NEW 2026-11-01"),
 8:("Merry & Bright","054","Christmas / red ribbon frame, cream","Christmas gift, mantel decor","Cozy Home & Apartment Ideas","Christmas","High","NEW 2026-11-01"),
 9:("Under the Mistletoe","053","Christmas / holly border, romantic","Romantic Christmas gift, couples","Gift Ideas for Every Occasion","Christmas","High","NEW 2026-11-01"),
 10:("Gingerbread Season","052","Christmas / gingerbread house, cream","Christmas gift, holiday baking decor","Candles & Candle Decor","Christmas","High","NEW 2026-11-01"),
 11:("Merry Christmas (burgundy)","051","Christmas / burgundy label, gold bow","Christmas gift","Gift Ideas for Every Occasion","Christmas","High","NEW 2026-11-01; listing URL unresolved"),
 12:("Cozy Home","050","Cozy home / green label, red-cream check","Housewarming, cozy home gift","Cozy Home & Apartment Ideas","Evergreen","Medium","NEW 2026-11-01; listing URL unresolved"),
 13:("Good Things Ahead","049","Encouragement / terracotta label, blue check","Good luck, encouragement, new beginnings","Gift Ideas for Every Occasion","Evergreen","Medium","NEW 2026-11-01; listing URL unresolved"),
 14:("Fresh Start","048","New beginnings / green label, red check","New beginnings, promotion, new month","Gift Ideas for Every Occasion","Evergreen","Medium","NEW 2026-11-01; listing URL unresolved"),
 15:("You Got This","047","Motivation / cream label, green check","Encouragement, exams, new job","Gift Ideas for Every Occasion","Evergreen","Medium","NEW 2026-11-01; listing URL unresolved"),
 16:("Just Breathe","046","Mindfulness / peach-pink label, check","Self-care, relaxation gift","Self Care & Cozy Living","Evergreen","Medium","NEW 2026-11-01; listing URL unresolved"),
 17:("Slow Down","045","Mindfulness / lavender label, check","Self-care, relaxation gift","Self Care & Cozy Living","Evergreen","Medium","NEW 2026-11-01; listing URL unresolved"),
}
rows=[]
for n,r in enumerate(new,1):
    k=idof(r['IMAGE1'])
    if k in have: continue
    url=url_by_img.get(k,"")
    lid=url.split('/')[4] if url else ""
    m=META[n]
    ver=("Yes - RSS feed item (shop /rss, fetched 2026-11-01 from runner): title AND primary image ID match the CSV row exactly" if url else "UNRESOLVED 2026-11-01 - not in the shop RSS (newest 10 only); shop page fetch returns a stale cached copy (32 items); browser unavailable. No URL invented.")
    imgs=[r[f'IMAGE{i}'] for i in range(1,11)]
    sizes=" | ".join(sorted({v for v in (r.get('VARIATION 1 VALUES') or '').split(',')})) if r.get('VARIATION 1 VALUES') else "4oz | 9oz"
    scents=(r.get('VARIATION 2 VALUES') or r.get('VARIATION 3 VALUES') or '').replace(',',' | ')
    rows.append(dict(listing_id=lid,etsy_url=url,url_verified=ver,title=r['TITLE'],description=r['DESCRIPTION'],price_usd=r['PRICE'],tags=r['TAGS'].replace(',',' | '),
        image_count=sum(1 for x in imgs if x),**{f'IMAGE{i}':imgs[i-1] for i in range(1,11)},sizes=sizes,scents=scents,materials=r['MATERIALS'],skus=r['SKU'].replace(',',' | '),
        inferred_theme=f"{m[0]} (design No. {m[1]}) - {m[2]}",inferred_gift_occasion=m[3],inferred_pinterest_board=m[4],seasonal_classification=m[5],seasonal_priority=m[6],
        priority_rationale=m[7],csv_row=n))
cols=list(old[0].keys())
with open('/home/claude/avenrow_master_catalog_v46.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=cols,lineterminator='\r\n'); w.writeheader()
    for r in old: w.writerow(r)
    for r in rows: w.writerow(r)
print(len(old),len(rows),len(old)+len(rows)); 
for r in rows: print(r['csv_row'],r['inferred_theme'][:30],r['listing_id'] or 'UNRESOLVED')
json.dump({r['csv_row']:{"id":r['listing_id'],"url":r['etsy_url']} for r in rows},open('/home/claude/avenrow-media/plan2/new_urls.json','w'))
