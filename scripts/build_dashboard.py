# -*- coding: utf-8 -*-
"""Notion에서 서버/작업 데이터를 조회해 마스킹 후 index.html을 재생성한다.
template.html의 SNAPSHOT 블록과 SNAPSHOT_AT만 교체한다."""
import json, os, re, urllib.request, datetime

TOKEN = os.environ['NOTION_TOKEN']
SERVERS_DB = '37d888f36d5180cd9656e1316caa5bcd'  # 운용 서버 현황
USAGE_DB = '37d888f36d518000b813edc35108f67a'  # 서버 사용 현황
API = 'https://api.notion.com/v1/databases/%s/query'


def query(db):
    rows, cursor = [], None
    while True:
        body = {'page_size': 100}
        if cursor:
            body['start_cursor'] = cursor
        req = urllib.request.Request(
            API % db, data=json.dumps(body).encode(),
            headers={'Authorization': 'Bearer ' + TOKEN,
                     'Notion-Version': '2022-06-28',
                     'Content-Type': 'application/json'})
        d = json.loads(urllib.request.urlopen(req).read())
        rows += d['results']
        if not d.get('has_more'):
            break
        cursor = d['next_cursor']
    return rows


purl = lambda pid: 'https://app.notion.com/p/' + pid.replace('-', '')
text = lambda p: ''.join(t['plain_text'] for t in p.get('rich_text', []))
title = lambda p: ''.join(t['plain_text'] for t in p.get('title', []))
sel = lambda p: (p.get('select') or {}).get('name')
msel = lambda p: [o['name'] for o in p.get('multi_select', [])]
rel = lambda p: [purl(r['id']) for r in p.get('relation', [])]


def mask_ip(ip):
    if not ip:
        return ip
    return re.sub(r'^(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}$', r'\1.xx', ip.strip())


def mask_serial(s):
    if not s or '셋업' in s:
        return s
    return s[:3] + '••••'


def clean(d):
    return {k: v for k, v in d.items() if v not in (None, '')}


servers = []
for pg in query(SERVERS_DB):
    pr = pg['properties']
    servers.append(clean({
        '서버 ID': title(pr.get('서버 ID', {})),
        'url': purl(pg['id']),
        '위치': sel(pr.get('위치', {})),
        '랙 넘버': sel(pr.get('랙 넘버', {})),
        '서버 모델': sel(pr.get('서버 모델', {})),
        '운용형태': sel(pr.get('운용형태', {})),
        'IP 주소(서비스)': mask_ip(text(pr.get('IP 주소(서비스)', {}))),
        'IP 주소(BMC)': mask_ip(text(pr.get('IP 주소(BMC)', {}))),
        '서버 시리얼': mask_serial(text(pr.get('서버 시리얼', {}))),
        'Driver Ver.': sel(pr.get('Driver Ver.', {})),
        'OS&Ver.': sel(pr.get('OS&Ver.', {})),
        'SDK Ver.': sel(pr.get('SDK Ver.', {})),
        '구성 GPU/NPU': json.dumps(msel(pr.get('구성 GPU/NPU', {})), ensure_ascii=False),
        '이용 현황': json.dumps(rel(pr.get('이용 현황', {})), ensure_ascii=False),
    }))

usage = []
for pg in query(USAGE_DB):
    pr = pg['properties']
    d = (pr.get('사용 기간') or {}).get('date') or {}
    usage.append(clean({
        '작업': title(pr.get('작업', {})),
        'url': purl(pg['id']),
        '운용 서버': json.dumps(rel(pr.get('운용 서버', {})), ensure_ascii=False),
        '활용 GPU/NPU': sel(pr.get('활용 GPU/NPU', {})),
        'date:사용 기간:start': d.get('start'),
        'date:사용 기간:end': d.get('end'),
    }))

html = open('template.html', encoding='utf-8').read()
snap = ('var SNAPSHOT={servers:' + json.dumps(servers, ensure_ascii=False)
        + ',usage:' + json.dumps(usage, ensure_ascii=False) + '};')
html2 = re.sub(r'var SNAPSHOT=\{.*?\]\};', lambda m: snap, html, count=1, flags=re.S)
assert html2 != html, 'SNAPSHOT 블록 교체 실패'
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%Y-%m-%d %H:%M')
html3 = re.sub(r"var SNAPSHOT_AT='[^']*';", "var SNAPSHOT_AT='" + now + " KST';", html2, count=1)
assert html3 != html2, 'SNAPSHOT_AT 교체 실패'
# 마스킹 안전망: 4옥텟 IP가 SNAPSHOT 안에 남아있으면 중단
s0 = html3.index('var SNAPSHOT={')
s1 = html3.index(']};', s0)
assert not re.search(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', html3[s0:s1]), '마스킹 누락 IP 존재'
open('index.html', 'w', encoding='utf-8').write(html3)
print('OK:', len(servers), 'servers,', len(usage), 'tasks @', now)
