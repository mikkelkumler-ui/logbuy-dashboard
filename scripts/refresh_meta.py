"""Fetch fresh Meta Ads data for the LogBuy Partner brand awareness dashboard.

Usage: python3 -I scripts/refresh_meta.py <out_dir>
Writes daily.csv, periods.csv, ads.csv, img/*.jpg and manifest.json to <out_dir>.
The Graph API token is added by the environment's network proxy.
"""
import csv, datetime as dt, json, os, sys, urllib.parse, urllib.request

CAMPAIGN = "120223286891680405"
API = "https://graph.facebook.com/v21.0/"
FIELDS = "spend,impressions,reach,frequency,cpm,clicks,ctr,inline_link_clicks,video_thruplay_watched_actions"


def get_all(path, params):
    url, rows = API + path + "?" + urllib.parse.urlencode(params), []
    while url:
        d = json.load(urllib.request.urlopen(url))
        rows += d.get("data", [])
        url = d.get("paging", {}).get("next")
    return rows


def thruplays(r):
    return sum(int(float(a["value"])) for a in r.get("video_thruplay_watched_actions", []) if a["action_type"] == "video_view")


def metrics(r):
    return {
        "spend": float(r.get("spend", 0)), "impressions": int(r.get("impressions", 0)), "reach": int(r.get("reach", 0)),
        "frequency": round(float(r.get("frequency", 0)), 4), "cpm": round(float(r.get("cpm", 0)), 2),
        "clicks": int(r.get("clicks", 0)), "link_clicks": int(r.get("inline_link_clicks", 0)),
        "ctr": round(float(r.get("ctr", 0)), 4), "thruplays": thruplays(r),
    }


def tr(a, b):
    return json.dumps({"since": str(a), "until": str(b)})


def main(out):
    os.makedirs(out + "/img", exist_ok=True)
    fetched = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = dt.date.today() - dt.timedelta(days=1)
    cur0 = end - dt.timedelta(days=29)
    prev1, prev0 = cur0 - dt.timedelta(days=1), cur0 - dt.timedelta(days=30)
    day0 = end - dt.timedelta(days=89)

    daily = get_all(CAMPAIGN + "/insights", {"fields": FIELDS, "time_increment": 1, "time_range": tr(day0, end), "limit": 500})
    with open(out + "/daily.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["date", "spend", "impressions", "reach", "frequency", "cpm", "clicks", "link_clicks", "ctr", "thruplays"])
        w.writeheader()
        for r in sorted(daily, key=lambda r: r["date_start"]):
            w.writerow({"date": r["date_start"], **metrics(r)})

    with open(out + "/periods.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["period", "start", "end", "spend", "impressions", "reach", "frequency", "cpm", "clicks", "link_clicks", "ctr", "thruplays", "fetched_at"])
        w.writeheader()
        for name, a, b in [("current", cur0, end), ("previous", prev0, prev1)]:
            r = get_all(CAMPAIGN + "/insights", {"fields": FIELDS, "time_range": tr(a, b)})
            w.writerow({"period": name, "start": a, "end": b, **metrics(r[0] if r else {}), "fetched_at": fetched})

    ins = {r["ad_id"]: r for r in get_all(CAMPAIGN + "/insights", {"level": "ad", "fields": "ad_id," + FIELDS, "time_range": tr(cur0, end), "limit": 500})}
    ads = get_all(CAMPAIGN + "/ads", {"limit": 100, "fields": "id,name,effective_status,created_time,creative.thumbnail_width(800).thumbnail_height(800){thumbnail_url,image_url,object_type}"})
    rows = []
    for a in ads:
        if a["id"] not in ins:
            continue
        c = a.get("creative", {})
        m = metrics(ins[a["id"]])
        img = None
        src = c.get("image_url") or c.get("thumbnail_url")
        if src:
            img = f"img/ad_{a['id']}.jpg"
            with open(out + "/" + img, "wb") as f:
                f.write(urllib.request.urlopen(src).read())
        video = c.get("object_type") == "VIDEO" or m["thruplays"] > 0 or "video" in a["name"].lower()
        rows.append({"ad_id": a["id"], "ad_name": a["name"], "status": a["effective_status"], "type": "Video" if video else "Billede",
                     "created": a.get("created_time", "")[:10], **{k: m[k] for k in ["spend", "impressions", "reach", "frequency", "cpm", "link_clicks", "ctr", "thruplays"]},
                     "image": img or ""})
    rows.sort(key=lambda r: -r["spend"])
    with open(out + "/ads.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["ad_id", "ad_name", "status", "type", "created", "spend", "impressions", "reach", "frequency", "cpm", "link_clicks", "ctr", "thruplays", "image"])
        w.writeheader()
        w.writerows(rows)

    manifest = {"fetched_at": fetched, "end": str(end),
                "current": [str(cur0), str(end)], "previous": [str(prev0), str(prev1)], "daily": [str(day0), str(end)],
                "daily_rows": len(daily), "ads": len(rows), "images": sorted(r["image"] for r in rows if r["image"])}
    json.dump(manifest, open(out + "/manifest.json", "w"), indent=1)
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
