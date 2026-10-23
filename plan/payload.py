import json, sys
m = json.load(open('/home/claude/avenrow-media/plan/manifest.json'))
def info(r):
    d, t = r['dubai'].split(' ')
    dt = f"{d}T{t[:8]}"
    base = {"autoPublish": True, "draft": False, "media": [r['media']], "text": r['text'],
            "publicationDate": {"dateTime": dt, "timezone": "Asia/Dubai"}}
    if r['plat'] == 'pinterest':
        base["providers"] = [{"network": "pinterest"}]
        base["pinterestData"] = {"boardId": r['board'], "pinTitle": r['title'], "pinLink": r['link'], "pinNewFormat": True}
    elif r['plat'] == 'tiktok':
        base["providers"] = [{"network": "tiktok"}]
        base["tiktokData"] = {"disableComment": False, "disableDuet": True, "disableStitch": True, "privacyOption": "PUBLIC_TO_EVERYONE", "title": r['text'], "autoAddMusic": False, "isAigc": True}
    else:
        base["providers"] = [{"network": "instagram"}]
        if r['fmt'] == 'REEL':
            base["instagramData"] = {"autoPublish": True, "type": "REEL", "showReelOnFeed": True, "isAiGenerated": True}
            base["videoCoverMilliseconds"] = 2000
        else:
            base["instagramData"] = {"autoPublish": True, "type": "POST", "showReelOnFeed": True, "isAiGenerated": True}
            base["mediaAltText"] = [r['alt']]
    return dt + "+04:00", base
if __name__ == "__main__":
    i = int(sys.argv[1]); date, b = info(m[i]); print(date); print(json.dumps(b, ensure_ascii=False))
