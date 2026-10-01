#!/usr/bin/env python3
"""Build the calculator's compact embedded database from a Wahapedia CSV export.

Usage:
  python3 build_db.py <folder with the Wahapedia CSVs> [wh40k_combat_calc.html]
If an HTML file is given, its embedded <script id="wh-data"> blob is replaced in place
(so future Wahapedia exports can be dropped in without touching the code).

Output format (JSON, gzipped + base64 in the HTML):
  f  = [[faction_id, name], ...]
  u  = {faction_id: [[id, name, role, M, T, Sv, inv, W, Ld, OC, [weapons], flags, kw, dmgW], ...]}
       weapon = [name, range_int (0 = melee), A, skill, S, AP, D, kwTokens]
       flags: 1 = leader/support, 2 = can be led (bodyguard), 4 = support
       kw   = '|'-joined lowercase unit keywords (for Anti-X / conditional abilities)
       dmgW = remaining-wounds threshold for the Damaged profile (0 = none)
  lm = {leader_id: [bodyguard ids]}
  meta = {edition, updated}
"""
import csv, html, io, json, re, sys, gzip, base64, collections, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from abil_parse import parse as parse_ability

SRC = sys.argv[1] if len(sys.argv) > 1 else '.'
def find(stem):
    for fn in os.listdir(SRC):
        if re.sub(r'^[0-9a-f]+-', '', fn) == stem + '.csv':
            return os.path.join(SRC, fn)
    raise SystemExit('missing ' + stem)
def R(stem):
    # Robust '|' reader: some description fields contain raw newlines, so join lines until
    # a record has the full number of separators.
    txt = open(find(stem), encoding='utf-8-sig').read().replace('\r\n', '\n')
    lines = txt.split('\n'); hdr = lines[0].split('|'); n = len(hdr) - 1
    rows, buf = [], ''
    for ln in lines[1:]:
        buf = ln if not buf else buf + '\n' + ln
        if buf.count('|') >= n:
            rows.append(dict(zip(hdr, buf.split('|')))); buf = ''
    return rows

def clean(s):
    s = re.sub(r'</li>', '. ', s or '', flags=re.I)
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', html.unescape(s)).strip()

def num(s, d=0):
    m = re.search(r'-?\d+', s or '')
    return int(m.group()) if m else d

def dice(s):
    s = (s or '').strip().upper().replace(' ', '')
    return s or '1'

def kw_tokens(desc):
    d = clean(desc).lower()
    out, unknown = [], []
    for part in [p.strip() for p in re.split(r',', d) if p.strip()]:
        cond = ''
        m = re.match(r'^(lethal hits|devastating wounds|sustained hits [d\d]+)\s*:\s*(.+)$', part)
        if m:
            part, cond = m.group(1), m.group(2).strip()
        c = ('@' + cond) if cond else ''
        if part == 'pistol': out.append('PI')
        elif part == 'close-quarters': out.append('CQ')
        elif part == 'twin-linked': out.append('TL')
        elif part == 'torrent': out.append('TO')
        elif part == 'ignores cover': out.append('IC')
        elif part == 'heavy': out.append('HV')
        elif part == 'assault': out.append('AS')
        elif part == 'psychic': out.append('PS')
        elif part == 'hazardous': out.append('HZ')
        elif part == 'precision': out.append('PR')
        elif part == 'one shot': out.append('OS')
        elif part == 'extra attacks': out.append('EA')
        elif part == 'indirect fire': out.append('IF')
        elif part == 'lance': out.append('LA')
        elif part == 'lethal hits': out.append('LH' + c)
        elif part == 'devastating wounds': out.append('DW' + c)
        elif part in ('blast', 'blast 1'): out.append('BL')
        elif re.fullmatch(r'blast \d+', part): out.append('BL' + part.split()[1])
        elif re.fullmatch(r'cleave \d+', part): out.append('CL' + part.split()[1])
        elif re.fullmatch(r'melta \d+', part): out.append('ME' + part.split()[1])
        elif re.fullmatch(r'sustained hits \d+', part): out.append('SH' + part.split()[2] + c)
        elif re.fullmatch(r'sustained hits d\d+', part): out.append('SH' + part.split()[2].upper() + c)
        elif re.fullmatch(r'rapid fire \d+', part): out.append('RF' + part.split()[2])
        elif re.fullmatch(r'rapid fire d\d+(\+\d+)?', part): out.append('RF' + part.split()[2].upper())
        elif re.fullmatch(r'anti-.+ \d\+', part):
            m = re.fullmatch(r'anti-(.+) (\d)\+', part)
            out.append('AN:%s:%s' % (m.group(1).strip(), m.group(2)))
        else:
            unknown.append(part)
    return out, unknown

def main():
    fac = R('Factions'); ds = R('Datasheets'); models = R('Datasheets_models')
    wg = R('Datasheets_wargear'); kws = R('Datasheets_keywords'); ld = R('Datasheets_leader')
    dab = R('Datasheets_abilities'); core = {a['id']: a['name'] for a in R('Abilities')}
    uab = collections.defaultdict(list)
    for a in sorted(dab, key=lambda r: int(r['line'] or 0)):
        uab[a['datasheet_id']].append(a)
    upd = open(find('Last_update'), encoding='utf-8-sig').read().split('\n')[1].strip('|\r ')

    model1 = {}
    for m in models:
        if m['datasheet_id'] not in model1 or int(m['line'] or 99) < int(model1[m['datasheet_id']]['line'] or 99):
            model1[m['datasheet_id']] = m
    ukw = collections.defaultdict(list)
    for k in kws:
        kk = k['keyword'].strip().lower()
        if kk and kk not in ukw[k['datasheet_id']]:
            ukw[k['datasheet_id']].append(kk)
    wpn = collections.defaultdict(list)
    for w in sorted(wg, key=lambda r: (int(r['line'] or 0), int(r['line_in_wargear'] or 0))):
        wpn[w['datasheet_id']].append(w)

    leaders = collections.defaultdict(list); led = set()
    for r in ld:
        a, b = int(r['leader_id']), int(r['attached_id'])
        if b not in leaders[str(a)]: leaders[str(a)].append(b)
        led.add(b)

    unknown = collections.Counter()
    units = collections.defaultdict(list)
    fac_ids = [f['id'] for f in fac]
    for d in ds:
        if d['virtual'] == 'true' or d['faction_id'] not in fac_ids: continue
        m = model1.get(d['id'])
        if not m: continue
        did = int(d['id'])
        ws, seen = [], set()
        for w in wpn[d['id']]:
            if not w['name'] or w['type'] not in ('Ranged', 'Melee'): continue
            toks, unk = kw_tokens(w['description'])
            for u in unk: unknown[u] += 1
            rng = 0 if w['type'] == 'Melee' else num(w['range'], 0) or 1
            sk = w['BS_WS'].strip()
            skill = num(sk, 0) if re.match(r'\d', sk) else 0   # 0 = no skill (torrent / N/A)
            if skill == 0 and 'TO' not in toks: skill = 6
            name = clean(w['name']).replace(' - ', ' – ')
            row = [name, rng, dice(w['A']), skill, num(w['S'], 0), num(w['AP'], 0), dice(w['D']), ','.join(toks)]
            key = json.dumps(row)
            if key in seen: continue
            seen.add(key); ws.append(row)
        inv = num(m['inv_sv'], 0) if re.match(r'\d', m['inv_sv'] or '') else 0
        flags = (1 if str(did) in leaders else 0) | (2 if did in led else 0) | (4 if d['is_support'] == 'true' else 0)
        dmgW = 0
        mm = re.match(r'\s*1\D(\d+)', d['damaged_w'] or '')
        if mm and 'subtract 1 from the hit roll' in clean(d['damaged_description']).lower():
            dmgW = int(mm.group(1))
        elif mm:
            dmgW = -int(mm.group(1))   # damaged profile that does not affect hit rolls
        # abilities: [name, text, effects]
        abl = []; fdeck = 0
        wnames = sorted({re.sub(r'\s+[–-]\s+.*$', '', w[0]).lower() for w in ws}, key=len, reverse=True)
        for a in uab[d['id']]:
            typ = a['type']
            if typ == 'Core':
                cn = core.get(a['ability_id'], ''); par = (a['parameter'] or '').strip()
                if cn == 'Feel No Pain' and re.match(r'\d', par):
                    abl.append(['Feel No Pain ' + par, 'Core ability.', [['d', 'fnp', int(par[0]), 'all', 'unit', 0]]])
                elif cn == 'Firing Deck' and re.match(r'\d', par):
                    fdeck = int(re.match(r'\d+', par).group())
                elif cn == 'Stealth':
                    abl.append(['Stealth', 'Core ability: ranged attacks against this unit are made as if it had the benefit of cover.', [['d', 'stealth', 1, 'all', 'unit', 0]]])
                continue
            if typ not in ('Datasheet', 'Wargear', 'Psychic', 'Special (правая колонка)'): continue
            nm = clean(a['name']); txt = clean(a['description'])
            if not nm or not txt: continue
            effs = parse_ability(txt, nm)
            low = txt.lower()
            for e in effs:   # restrict to named weapons when the text names one of this unit's weapons
                wf = [wn for wn in wnames if len(wn) > 3 and wn in low]
                if wf and e[0] == 'a': e.append(wf)
            abl.append([nm, txt[:700], effs])
        units[d['faction_id']].append([
            did, clean(d['name']), d['role'], m['M'], num(m['T'], 4), m['Sv'], inv, num(m['W'], 1),
            m['Ld'], num(m['OC'], 0), ws, flags, '|'.join(ukw[d['id']]), dmgW, abl, fdeck])

    f_out = [[f['id'], f['name']] for f in fac if units.get(f['id'])]
    # ---- army rules, detachments (abilities + enhancements) ----
    def abil_entry(name, desc, force_cond=False):
        nm = clean(name); txt = clean(desc)
        effs = parse_ability(txt, nm)
        for e in effs:
            if e[4] == 'model': e[4] = 'unit'
            if force_cond: e[5] = 1
        return [nm, txt[:900], effs]
    ar = collections.defaultdict(list); seen_ar = set()
    for a in R('Abilities'):
        fid = a['faction_id']
        if not fid or (fid, a['name']) in seen_ar: continue
        seen_ar.add((fid, a['name']))
        ar[fid].append(abil_entry(a['name'], a['description']))
    dets = collections.defaultdict(list); dmap = {}
    for d0 in R('Detachments'):
        if d0['type'] == 'Boarding Actions' or not d0['faction_id']: continue
        e = [d0['id'], clean(d0['name']), [], []]
        dmap[d0['id']] = e; dets[d0['faction_id']].append(e)
    for a in R('Detachment_abilities'):
        if a['detachment_id'] in dmap: dmap[a['detachment_id']][2].append(abil_entry(a['name'], a['description']))
    for a in R('Enhancements'):
        if a['detachment_id'] in dmap:
            en = abil_entry(a['name'], a['description'], force_cond=True); en.append(a['cost'])
            dmap[a['detachment_id']][3].append(en)
    for k in dets: dets[k].sort(key=lambda x: x[1])
    lm = {k: v for k, v in leaders.items()}
    out = {'f': f_out, 'u': dict(units), 'lm': lm, 'ar': dict(ar), 'det': dict(dets), 'meta': {'edition': 11, 'updated': upd}}
    raw = json.dumps(out, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    open('db_new.json', 'wb').write(raw)
    b64 = base64.b64encode(gzip.compress(raw, 9, mtime=0)).decode()
    open('db_new.b64', 'w').write(b64)
    print('factions', len(f_out), 'units', sum(len(v) for v in units.values()),
          'weapons', sum(len(u[10]) for v in units.values() for u in v), 'raw', len(raw), 'b64', len(b64))
    print('unparsed ability text:', unknown.most_common(40))
    if len(sys.argv) > 2:
        page = sys.argv[2]
        h = open(page, encoding='utf-8').read()
        m = re.search(r'(<script id="wh-data" type="text/plain" data-enc="gz64">)(.*?)(</script>)', h, re.S)
        if not m: raise SystemExit('no wh-data block in ' + page)
        h = h[:m.start(2)] + b64 + h[m.end(2):]
        open(page, 'w', encoding='utf-8').write(h)
        print('injected data into', page)

main()
