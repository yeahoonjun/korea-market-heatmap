#!/usr/bin/env python3
"""Mock Worker for the 일정 tab: qa/news/mock_api.py (web/ + quiet /api stubs) plus GET /api/calendar (AGENTS §3-33).

  python3 qa/calendar/mock_cal.py [port=8994]

/api/calendar answers the Worker's shape (worker/src/calendar.js) for any from..to (≤ 42 days), built around KST today so the page
always has a week to draw: 한국 지표 (with a released value on a past day), 미국 지표 (22:30 KST / 08:30 ET), 금리 (★3), 시장
(2nd-Thursday expiry + weekly expiries flagged weekly), 기업 (DART 무상증자 · a lock-up with %, 005930 for the 관심 badge, a group
row of 15 dividend record dates), one closed day and one special day. Corp rows carry the Worker's `cls` / `minor` (§9-6): today has
three 주식권리일정 details (minor), a 주총 of a stock on the map (000660, shown) and one off the map (900222, a detail); the first
Saturday has one detail only (the empty-day line "숨긴 일정 1개 (기업 세부 일정)"). 미국 rows carry rg:'us' (FRED · FOMC).
Test controls: /__mode?cal=ok|fail|none|empty|slow|stale   fail: 502 {error}; none: 404 (an older Worker); empty: no events;
slow: 2.5 s; stale: sources.fred ok:false + stale:true.   /__stats · /__reset as in mock_api.py.
"""
import json
import pathlib
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / 'news'))
import mock_api  # noqa: E402

KST = timezone(timedelta(hours=9))
mock_api.DEFAULT['cal'] = 'ok'
mock_api.MODE['cal'] = 'ok'


def d2s(d):
    return d.strftime('%Y-%m-%d')


def second_thu(y, m):
    d = datetime(y, m, 1)
    n = 0
    while True:
        if d.weekday() == 3:
            n += 1
            if n == 2:
                return d
        d += timedelta(days=1)


def events_for(frm, to, mode):
    today = datetime.now(KST).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    out, days = [], {}
    if mode == 'empty':
        return out, days
    d = frm
    while d <= to:
        s, wd, off = d2s(d), d.weekday(), (d - today).days
        if wd < 5:
            ev = {'id': f'bok:{s}:a', 'd': s, 't': '08:00', 'k': 'kr', 'star': 2 if wd in (1, 3) else 1, 'src': 'bok', 'title': f'{d.month}월 소비자동향조사 결과' if wd == 1 else '통화 및 유동성'}
            if off < 0 and wd == 1:
                ev['value'] = {'text': '소비자심리지수 105.4', 'src': 'ecos', 'p': d.strftime('%Y%m')}
            out.append(ev)
            out.append({'id': f'fred:10:{s}', 'd': s, 't': '22:30', 'k': 'us', 'rg': 'us', 'star': 3 if wd == 3 else 1, 'src': 'fred', 'rid': 10,
                        'title': '미국 소비자물가(CPI)' if wd == 3 else '미국 주간 신규 실업수당 청구', 'orig': {'d': s, 't': '08:30', 'tz': 'America/New_York'}})
        if wd == 0 or (wd == 3 and d != second_thu(d.year, d.month)):
            out.append({'id': f'rule:wk:{s}', 'd': s, 't': None, 'k': 'mkt', 'star': 1, 'src': 'rule', 'weekly': True,
                        'title': f"위클리 옵션 만기 ({'월' if wd == 0 else '목'})", 'sub': '코스피200 ' + ('월' if wd == 0 else '목') + '요일물'})
        if d == second_thu(d.year, d.month):
            out.append({'id': f'rule:exp:{s}', 'd': s, 't': '15:20', 'k': 'mkt', 'star': 3 if d.month % 3 == 0 else 2, 'src': 'rule',
                        'title': '선물 · 옵션 동시만기' if d.month % 3 == 0 else f'옵션 만기 ({d.month}월물)'})
        if off == 3:
            out.append({'id': f'cb:bok:{s}', 'd': s, 't': None, 'k': 'cb', 'star': 3, 'src': 'manual', 'title': '금통위 통화정책방향 결정', 'sub': '기준금리 결정',
                        'url': 'https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755&pYear=2026'})
        if off == 0:
            out.append({'id': f'dart:R1:asstd:{s}', 'd': s, 't': None, 'k': 'corp', 'star': 2, 'src': 'dart', 'api': 'fricDecsn', 'c': '005930', 'n': '삼성전자', 'cls': 'rights',
                        'exd': d2s(d - timedelta(days=1)), 'title': '무상증자 신주배정기준일', 'sub': '권리락 전날 · 1주당 1주', 'r': '20261113000111', 'url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261113000111'})
            for i, (c, n, t, w, cl) in enumerate((('900111', '가나상사', '임시총회 명세통지시한', '임시총회', 'agm'), ('900112', '다라리츠', '배당/분배 명세접수시한', '배당/분배', 'div'),
                                                  ('900113', '마바산업', '매수청구 반대의사접수시한', '매수청구', 'etc'))):
                out.append({'id': f'fsc:rights:{c}:{s}:{i}', 'd': s, 't': None, 'k': 'corp', 'star': 1, 'src': 'fsc', 'api': 'getRighExerReasSche_V2', 'c': c, 'n': n,
                            'title': t, 'why': w, 'cls': cl, 'minor': True})
            out.append({'id': f'fsc:rights:000660:{s}:agm', 'd': s, 't': None, 'k': 'corp', 'star': 1, 'src': 'fsc', 'api': 'getRighExerReasSche_V2', 'c': '000660', 'n': 'SK하이닉스',
                        'title': '임시총회 총회개최일', 'sub': '명부폐쇄 11/2', 'why': '임시총회', 'cls': 'agm'})
            out.append({'id': f'fsc:rights:900222:{s}:agm', 'd': s, 't': None, 'k': 'corp', 'star': 1, 'src': 'fsc', 'api': 'getRighExerReasSche_V2', 'c': '900222', 'n': '사아테크',
                        'title': '임시총회 총회개최일', 'why': '임시총회', 'cls': 'agm'})
        if off == 1:
            out.append({'id': f'fsc:lock:000660:{s}', 'd': s, 't': None, 'k': 'corp', 'star': 3, 'src': 'fsc', 'api': 'getLockUpRetuInfo_V3', 'c': '000660', 'n': 'SK하이닉스', 'cls': 'lock',
                        'title': '보호예수 해제 2,150만 주', 'sub': '상장주식의 18.4% · 최대주주', 'pct': 18.4})
            out.append({'id': f'fsc:lock:900333:{s}', 'd': s, 't': None, 'k': 'corp', 'star': 1, 'src': 'fsc', 'api': 'getLockUpRetuInfo_V3', 'c': '900333', 'n': '차카바이오', 'cls': 'lock', 'minor': True,
                        'title': '보호예수 해제 3,000주', 'sub': '상장주식의 0.2% · 주식매수선택권', 'pct': 0.2})
            out.append({'id': f'grp:div-rec:{s}', 'd': s, 't': None, 'k': 'corp', 'src': 'fsc', 'star': 2, 'title': '배당 기준일', 'grp': 'div-rec', 'cls': 'div', 'n': 15,
                        'codes': ['005930', '000660', '035420', '005380', '051910', '006400', '035720', '000270', '068270', '105560', '055550', '012330', '028260', '066570', '003550'], 'sub': '15개 종목'})
        if off == 2:
            out.append({'id': f'cb:fomc:{s}', 'd': s, 't': '04:00', 'k': 'cb', 'rg': 'us', 'star': 3, 'src': 'manual', 'title': 'FOMC 금리 결정', 'sub': '경제전망(SEP) 함께',
                        'orig': {'d': d2s(d - timedelta(days=1)), 't': '14:00', 'tz': 'America/New_York'}, 'tentative': None})
        if wd == 5 and 0 <= off <= 6:          # the Saturday of the first 7 days: a details-only day (the empty-day line)
            out.append({'id': f'fsc:rights:900444:{s}:x', 'd': s, 't': None, 'k': 'corp', 'star': 1, 'src': 'fsc', 'api': 'getRighExerReasSche_V2', 'c': '900444', 'n': '자차홀딩스',
                        'title': '기타 명세접수시한', 'why': '기타', 'cls': 'etc', 'minor': True})
        if off == 5 and wd < 5:
            days[s] = {'kind': 'closed', 'note': '휴장 · 테스트 휴일'}
        if off == 4 and wd < 5:
            days[s] = {'kind': 'special', 'note': '수능 · 정규장 10:00–16:30', 'open': '10:00', 'close': '16:30'}
        d += timedelta(days=1)
    for e in out:
        if e.get('tentative') is None:
            e.pop('tentative', None)
    out.sort(key=lambda e: (e['d'], e['t'] or '', -e['star']))
    return out, days


class H(mock_api.H):
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == '/__mode':
            q = dict(urllib.parse.parse_qsl(u.query))
            if 'cal' in q:
                mock_api.MODE['cal'] = q['cal']
        if u.path != '/api/calendar':
            return super().do_GET()
        q = dict(urllib.parse.parse_qsl(u.query))
        with mock_api.LOCK:
            mock_api.STATS[u.path] = mock_api.STATS.get(u.path, 0) + 1
        mode = mock_api.MODE.get('cal', 'ok')
        if mode == 'none':
            return self.send_body(b'{"error":"not found"}', 404)
        if mode == 'fail':
            return self.send_json({'error': '일정을 만들지 못했어요'}, 502)
        if mode == 'slow':
            time.sleep(2.5)
        try:
            frm = datetime.strptime(q['from'], '%Y-%m-%d')
            to = datetime.strptime(q['to'], '%Y-%m-%d')
        except Exception:
            return self.send_json({'error': 'from · to는 YYYY-MM-DD 형식이어야 해요'}, 400)
        if (to - frm).days + 1 > 42 or to < frm:
            return self.send_json({'error': '한 번에 42일까지 받을 수 있어요'}, 400)
        evs, days = events_for(frm, to, mode)
        src = {k: {'name': n, 'ok': True, 'at': datetime.now(KST).strftime('%Y-%m-%d %H:%M')} for k, n in
               (('bok', '한국은행 통계공표일정'), ('kostat', '국가데이터처 보도계획'), ('fred', 'FRED 발표 일정'), ('vals', '발표값(ECOS · FRED)'), ('dart', 'OpenDART'), ('fsc', '금융위원회'))}
        src['fsc']['parts'] = {'divi': 'ok', 'lock': 'ok', 'rights': 'ok'}
        body = {'asOf': datetime.now(KST).strftime('%Y-%m-%dT%H:%M:%S+09:00'), 'from': q['from'], 'to': q['to'], 'tz': 'Asia/Seoul', 'days': days, 'events': evs, 'sources': src, 'manual': '2026-11-15'}
        if mode == 'stale':
            body['sources']['fred'].update(ok=False, err='network')
            body['stale'] = True
        return self.send_json(body)


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8994
    srv = mock_api.ThreadingHTTPServer(('127.0.0.1', port), H)
    print(f'calendar mock on http://127.0.0.1:{port}/', file=sys.stderr)
    srv.serve_forever()
