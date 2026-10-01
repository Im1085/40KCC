"""Parse Wahapedia datasheet ability text into calculator effects.

Effect = [side, key, value, scope, who, cond]
  side : 'a' (applies when this unit attacks) | 'd' (applies when this unit is attacked)
  key  : a-side: hit, wnd, rrH1, rrH, rrW1, rrW, A, S, AP, D, BS, lethal, sus, dev, crit5, ioc
         d-side: fnp, inv, mD1, halfD, stealth, mHit, mWnd
  scope: 'all' | 'melee' | 'ranged'
  who  : 'model' (only this model's weapons) | 'unit' (whole unit) | 'led' (unit it leads)
  cond : 1 = conditional/situational (off by default), 0 = always on
"""
import re

COND = ['if ', 'once per', 'select ', 'until the', 'until ', 'that targets', 'targets a', 'targets an', 'targets the', 'targets one',
        'within', 'charge', 'aura', 'can use this ability', 'roll one d6', 'below half', 'closest', 'against mortal',
        'psychic attack', 'in your ', "opponent’s", 'when ', 'excluding', 'objective', 'for each', 'instead',
        'battle-shocked', 'destroyed', 'remained stationary', 'on a ', 'token', 'wounded', 'engaged', 'fought',
        'has the ', 'is the target', 'that are', 'of the following']

def _scope(s):
    m, r = 'melee' in s, ('ranged' in s or 'shooting' in s)
    return 'melee' if m and not r else 'ranged' if r and not m else 'all'

def _who(s, full):
    if 'leading a unit' in s or ('leading a unit' in full and 'that unit' in s): return 'led'
    if re.search(r"this model(’|')s|this model makes|equipped by this model|the bearer(’|')s (weapons|melee|ranged|attacks)|the bearer (has|makes)|this model has", s): return 'model'
    if re.search(r"(models in|model in|this unit|the bearer’s unit|bearer's unit)", s): return 'unit'
    if re.search(r"(this model|the bearer)", s): return 'model'
    return 'unit'

def _is_cond(s):
    s2 = re.sub(r"^while this model is leading a unit,?\s*", '', s)
    s2 = re.sub(r"that targets (an enemy unit|a unit|an enemy)\b", '', s2)
    s2 = s2.replace('while this unit is leading a unit', '')
    return 1 if any(c in s2 for c in COND) else 0

STAT = {'a': 'A', 's': 'S', 'ap': 'AP', 'd': 'D', 'ws': 'BS', 'bs': 'BS'}

NONKW = {'CP', 'OC', 'AP', 'WS', 'BS', 'SV', 'LD', 'VP', 'HP', 'II', 'III', 'IV'}

def _strip(x):
    return x.replace('⟦', '').replace('⟧', '')

def _phrases(seg):
    """Runs of keyword words (⟦marked⟧ or ALL-CAPS) in a text segment → list of word lists."""
    out, cur = [], []
    seg = re.sub(r'\[[^\]]*\]', ' , ', seg)          # ignore [WEAPON ABILITY] names
    seg = re.sub(r'(?i)if your army faction is[^,]*,', ' , ', seg)   # faction gate, not a unit filter
    for m in re.finditer(r"⟦([^⟧]+)⟧|([A-Za-z’'\-]+)|([^\sA-Za-z])", seg):
        if m.group(1):
            cur += [w.lower() for w in m.group(1).split()]
        elif m.group(2) and m.group(2).isupper() and len(m.group(2)) >= 2 and m.group(2) not in NONKW:
            cur.append(m.group(2).lower())
        else:
            if cur: out.append(cur); cur = []
    if cur: out.append(cur)
    return out

def kwreq(seg):
    """Keyword requirement of a clause: [[any-of phrases], [excluded phrases]] or None."""
    m = re.search(r'excluding([^)]*)', seg, re.I)
    exc = _phrases(m.group(1)) if m else []
    inc_seg = seg[:m.start()] + seg[m.end():] if m else seg
    inc = _phrases(inc_seg)
    if not inc and not exc: return None
    return [inc, exc]

def parse(text, name=''):
    t = re.sub(r'\s+', ' ', text or '').strip()
    marked = t
    t = _strip(t)
    low = t.lower()
    # ability-level keyword requirement: "XXX model only." or the first sentence naming keyworded units
    abreq = None
    mo = re.match(r'^(.+?) (?:model|unit)s? only\b', marked)
    if mo and len(mo.group(1)) < 80:
        words = [w for w in re.split(r'\s+or\s+', _strip(mo.group(1)))]
        abreq = [[[x.lower() for x in re.findall(r"[A-Za-z’'\-]+", w)] for w in words], []]
    else:
        for sent in re.split(r'(?<=[.])\s+', marked):
            if '⟦' in sent and re.search(r'\bunits?\b|\bmodels?\b', sent, re.I):
                abreq = kwreq(sent); break
    t = marked
    ab_cond = 1 if re.search(r'once per (battle|turn|phase|battle round)|can use this ability|roll one d6|select one', low) else 0
    effs = []
    # split into sentences, keeping bracketed tokens intact
    sents = [x.strip() for x in re.split(r'(?<=[.])\s+(?=[A-Z\[⟦])', t) if x.strip()]
    # stat bullet lists ("have: +3 A . +2 S .") are split by '. ' — rejoin short fragments to previous sentence
    merged = []
    for x in sents:
        if merged and re.match(r'^\+\d', x): merged[-1] += ' ' + x
        else: merged.append(x)
    ctx_prev = ''
    clauses = []
    for raw in merged:
        parts = re.split(r',? and,? (?=if )|; ', raw)
        lead = ''
        for i, pt in enumerate(parts):
            if i == 0:
                m0 = re.match(r'^(each time [^,]*,)', pt, re.I)
                lead = m0.group(1) + ' ' if m0 else ''
                clauses.append(pt)
            else:
                clauses.append(lead + pt)
    for raw in clauses:
        creq = kwreq(raw) if ('⟦' in raw) else None
        req = creq or abreq
        raw = _strip(raw)
        s = raw.lower()
        # context sentence for fragments like "If you do, ..."
        ctx = (ctx_prev + ' ' + s) if s.startswith('if you do') else s
        cond = 1 if (ab_cond or _is_cond(ctx)) else 0
        sc = _scope(ctx); who = _who(s, low)
        enemy = 'enemy' in s or 'opponent' in s
        targeted = bool(re.search(r'(targets? (this|that|the bearer|a model in this|its)|allocated to|an attack targets|attack is made against|targeted)', s))
        def add(side, key, val=1, scope=None, c=None):
            e = [side, key, val, scope or (sc if side == 'a' else 'all'), who, cond if c is None else c, None, req]
            if e not in effs: effs.append(e)
        # ----- defensive -----
        for m in re.finditer(r'(\d)\+ invulnerable save', s):
            add('d', 'inv', int(m.group(1)))
        for m in re.finditer(r'feel no pain (\d)\+', s):
            c = 1 if (cond or re.search(r'against (mortal|psychic)|damage characteristic of 1|psychic attack', s)) else 0
            add('d', 'fnp', int(m.group(1)), c=c)
        if 'subtract 1 from the damage characteristic' in s and ('allocated' in s or 'targets' in s):
            add('d', 'mD1')
        if re.search(r'halve the damage characteristic', s) and ('allocated' in s or 'targets' in s):
            add('d', 'halfD')
        if re.search(r'\[stealth\]|the stealth ability', s):
            add('d', 'stealth')
        if 'subtract 1 from the hit roll' in s and (targeted or enemy):
            add('d', 'mHit', 1, c=1 if (enemy and 'within' in s) or cond else 0)
        if 'subtract 1 from the wound roll' in s and (targeted or enemy):
            add('d', 'mWnd', 1, c=1 if ('strength' in s or cond) else 0)
        # ----- offensive (skip debuffs aimed at enemies) -----
        if not enemy or 'targets' in s:
            if re.search(r'add 1 to (the )?hit rolls?|\+1 to hit', s) and not targeted_def(s): add('a', 'hit', 1)
            if re.search(r'add 1 to (the )?wound rolls?|\+1 to wound', s) and not targeted_def(s): add('a', 'wnd', 1)
            if re.search(r're-roll (a |the )?hit rolls? of 1', s): add('a', 'rrH1')
            if re.search(r're-roll (the |a )?hit rolls?(?! of 1)', s) and not re.search(r're-roll (a |the )?hit rolls? of 1', s): add('a', 'rrH')
            if re.search(r're-roll (a |the )?wound rolls? of 1', s): add('a', 'rrW1')
            if re.search(r're-roll (the |a )?wound rolls?(?! of 1)', s) and not re.search(r're-roll (a |the )?wound rolls? of 1', s): add('a', 'rrW')
            if '[lethal hits]' in s: add('a', 'lethal')
            m = re.search(r'\[sustained hits (\d)\]', s)
            if m: add('a', 'sus', int(m.group(1)))
            if '[devastating wounds]' in s: add('a', 'dev')
            if '[ignores cover]' in s: add('a', 'ioc')
            if '[twin-linked]' in s: add('a', 'rrW')
            if '[lance]' in s: add('a', 'wnd', 1, c=1)
            if re.search(r'unmodified hit roll of 5\+', s) and 'critical hit' in s: add('a', 'crit5')
            # "+3 A", "+1 A and S", "+1 A , WS and S", "+2 D"
            for m in re.finditer(r'\+(\d+)\s+((?:a|s|ap|d|ws|bs)(?:\s*(?:,|and)\s*(?:a|s|ap|d|ws|bs))*)(?=\s*[.,;)]|\s*$|\s+(?:and|to|for)\b)', s):
                for st in re.split(r'\s*(?:,|and)\s*', m.group(2)):
                    if st in STAT:
                        add('a', STAT[st], int(m.group(1)))
            for m in re.finditer(r'add (\d) to the (attacks|strength|damage) characteristic', s):
                add('a', {'attacks': 'A', 'strength': 'S', 'damage': 'D'}[m.group(2)], int(m.group(1)))
            for m in re.finditer(r'improve the ((?:strength|attacks|armour penetration|damage|weapon skill|ballistic skill)(?:(?:,| and|, and) (?:strength|attacks|armour penetration|damage|weapon skill|ballistic skill))*) characteristics? of [^.]*? by (\d)', s):
                for st in re.split(r',\s*and\s*|,\s*|\s+and\s+', m.group(1)):
                    k = {'strength': 'S', 'attacks': 'A', 'armour penetration': 'AP', 'damage': 'D', 'weapon skill': 'BS', 'ballistic skill': 'BS'}.get(st.strip())
                    if k: add('a', k, int(m.group(2)))
        ctx_prev = s
    return effs

def targeted_def(s):
    # "each time an attack targets this unit, add 1 to the wound roll" would be an enemy buff — rare; keep simple
    return False
