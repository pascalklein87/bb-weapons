import math
from collections import defaultdict

from flask import Blueprint, render_template, abort
from engine.db import get_connection

guides_bp = Blueprint('guides', __name__)

# Display order for subfactions on the hub page
SUBFACTION_ORDER = [
    'Brigand', 'Barbarian', 'Noble', 'Militia', 'Southern',
    'Orc', 'Goblin', 'Ancient', 'Zombie', 'Undead', 'Beast', 'Golem',
]


def _calc_costs(r):
    """Compute AP per hit and fatigue per hit from a joined ranking row."""
    ap = r['ap_cost'] or 4
    ap_total = ap + (r['reload_ap'] or 0)
    fat_base = (r['fatigue_base_cost'] or 0) + (r['reload_fatigue'] or 0) + (r['weapon_fatigue'] or 0)
    fatigue_per_hit = math.ceil(fat_base * 0.75)
    return ap_total, fatigue_per_hit


def _ranking_query():
    """SQL to join guide_weapon_rankings with weapons and weapon_skills."""
    return """
        SELECT g.enemy_slug, g.weapon_slug, g.skill_slug, g.scenario,
               g.avg_hits_to_kill, g.min_hits, g.max_hits, g.num_simulations,
               w.name AS weapon_name, w.is_two_handed, w.mastery,
               COALESCE(ws.name, ws_base.name) AS skill_name,
               COALESCE(ws.action_cost, ws_base.action_cost) AS ap_cost,
               COALESCE(ws.fatigue_base_cost, ws_base.fatigue_base_cost) AS fatigue_base_cost,
               COALESCE(ws.reload_ap, ws_base.reload_ap, 0) AS reload_ap,
               COALESCE(ws.reload_fatigue, ws_base.reload_fatigue, 0) AS reload_fatigue,
               w.fatigue_per_use AS weapon_fatigue
        FROM guide_weapon_ranking g
        JOIN weapon w ON w.unique_slug = g.weapon_slug
        LEFT JOIN weapon_skill ws ON ws.unique_slug = g.skill_slug
        LEFT JOIN weapon_skill ws_base ON ws_base.unique_slug = CASE
            WHEN ws.unique_slug IS NULL AND g.skill_slug LIKE '%%2t' THEN REPLACE(g.skill_slug, '2t', '')
            WHEN ws.unique_slug IS NULL AND g.skill_slug LIKE '%%3t' THEN REPLACE(g.skill_slug, '3t', '')
            ELSE NULL END
    """


def _build_ranking_entry(r):
    """Build a single ranking dict from a joined DB row."""
    ap_total, fatigue_per_hit = _calc_costs(r)
    mastery = r['mastery']
    weapon_slug = r['weapon_slug']
    enemy_slug = r['enemy_slug']
    avg_hits = r['avg_hits_to_kill']

    is_ranged = mastery in ('bow', 'crossbow', 'throwing')
    if is_ranged:
        weapon_type = 'R'
    elif r['is_two_handed']:
        weapon_type = '2H'
    else:
        weapon_type = '1H'

    # Build calculator URL
    scenario = r['scenario']
    mods_map = {
        'none': '',
        'dg': 'double-grip',
        'dg_duelist': 'double-grip_duelist',
        'duelist': 'duelist',
    }
    mods = mods_map.get(scenario, '')
    if r['is_two_handed']:
        mods = ''
    calc_parts = [f"weapon={weapon_slug}",
                  f"enemy={enemy_slug}",
                  f"skill={r['skill_slug']}"]
    if mods:
        calc_parts.append(f"mods={mods}")
    calc_url = 'https://damage.bloodngold.com/?' + '&'.join(calc_parts)

    total_fatigue = round(avg_hits * fatigue_per_hit)

    return {
        'weapon_name': r['weapon_name'],
        'weapon_slug': weapon_slug,
        'skill_name': r['skill_name'],
        'weapon_type': weapon_type,
        'avg_hits': format(avg_hits, '.1f'),
        'total_fatigue': total_fatigue,
        'min_hits': r['min_hits'],
        'max_hits': r['max_hits'],
        'fat_min': r['min_hits'] * fatigue_per_hit,
        'fat_max': r['max_hits'] * fatigue_per_hit,
        'ap_cost': ap_total,
        'fatigue_per_hit': fatigue_per_hit,
        'total_ap': format(avg_hits * ap_total, '.1f'),
        'total_ap_raw': avg_hits * ap_total,
        'calc_url': calc_url,
    }


def _query(sql, params=None):
    """Execute a read query and return all rows as dicts."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params or ())
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def _query_one(sql, params=None):
    """Execute a read query and return one row as dict, or None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params or ())
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row


def _load_rankings(enemy_slug, scenario='dg_duelist'):
    """Load rankings for a specific 1H trait scenario."""
    base = _ranking_query()

    rows_1h = _query(base + """
        WHERE g.enemy_slug = %s AND g.scenario = %s AND w.is_two_handed = 0
              AND w.mastery NOT IN ('throwing', 'bow', 'crossbow')
    """, (enemy_slug, scenario))

    rows_2h = _query(base + """
        WHERE g.enemy_slug = %s AND g.scenario = 'none' AND w.is_two_handed = 1
    """, (enemy_slug,))

    throw_scenario = 'duelist' if scenario == 'dg_duelist' else 'none'
    rows_throw = _query(base + """
        WHERE g.enemy_slug = %s AND g.scenario = %s AND w.mastery = 'throwing'
    """, (enemy_slug, throw_scenario))

    all_rows = rows_1h + rows_2h + rows_throw
    unsorted = [_build_ranking_entry(r) for r in all_rows]
    return sorted(unsorted, key=lambda x: x['total_ap_raw'])


def _load_enemy(enemy_slug):
    row = _query_one("SELECT * FROM enemy WHERE unique_slug = %s",
                     (enemy_slug,))
    if not row:
        return None
    enemy = dict(row)

    loadout_rows = _query(
        "SELECT slot, durability FROM enemy_armor_loadout WHERE enemy_id = %s",
        (enemy['id'],))

    body_vals = [r['durability'] for r in loadout_rows if r['slot'] == 'body']
    head_vals = [r['durability'] for r in loadout_rows if r['slot'] == 'helmet']
    if body_vals:
        enemy['body_armor_min'] = min(body_vals)
        enemy['body_armor_max'] = max(body_vals)
    else:
        enemy['body_armor_min'] = enemy['body_armor']
        enemy['body_armor_max'] = enemy['body_armor']
    if head_vals:
        enemy['head_armor_min'] = min(head_vals)
        enemy['head_armor_max'] = max(head_vals)
    else:
        enemy['head_armor_min'] = enemy['head_armor']
        enemy['head_armor_max'] = enemy['head_armor']
    return enemy


def _load_armor_loadout(enemy_id):
    rows = _query(
        "SELECT slot, durability, percent FROM enemy_armor_loadout WHERE enemy_id = %s ORDER BY slot, durability",
        (enemy_id,))
    if not rows:
        return None
    loadout = {'body': [], 'helmet': []}
    for r in rows:
        loadout[r['slot']].append({
            'durability': r['durability'],
            'percent': r['percent'],
        })
    return loadout


def _load_all_enemies():
    """Load enemies that have guide data, grouped by faction for the switcher."""
    rows = _query("""
        SELECT DISTINCT e.name, e.unique_slug, e.subfaction, e.tier
        FROM enemy e
        JOIN guide_weapon_ranking g ON g.enemy_slug = e.unique_slug
        ORDER BY e.subfaction, e.tier
    """)
    return [{'name': r['name'], 'slug': r['unique_slug'],
             'faction': r['subfaction'] or 'Other'} for r in rows]


def _load_related_enemies(enemy):
    """Load all faction enemies sorted by tier, marking the current one."""
    rows = _query("""
        SELECT DISTINCT e.name, e.unique_slug
        FROM enemy e
        JOIN guide_weapon_ranking g ON g.enemy_slug = e.unique_slug
        WHERE e.subfaction = %s
        ORDER BY e.tier
    """, (enemy.get('subfaction', ''),))
    return [{'name': r['name'], 'slug': r['unique_slug'],
             'is_current': r['unique_slug'] == enemy['unique_slug']} for r in rows]


def _load_hub_data():
    """Load all enemies that have guide data, grouped by faction."""
    rows = _query("""
        SELECT e.name, e.unique_slug, e.hitpoints,
               COALESCE(MIN(CASE WHEN al.slot = 'body' THEN al.durability END), e.body_armor) AS body_min,
               COALESCE(MAX(CASE WHEN al.slot = 'body' THEN al.durability END), e.body_armor) AS body_max,
               COALESCE(MIN(CASE WHEN al.slot = 'helmet' THEN al.durability END), e.head_armor) AS head_min,
               COALESCE(MAX(CASE WHEN al.slot = 'helmet' THEN al.durability END), e.head_armor) AS head_max,
               e.subfaction, e.tier
        FROM enemy e
        JOIN (SELECT DISTINCT enemy_slug FROM guide_weapon_ranking) g
            ON g.enemy_slug = e.unique_slug
        LEFT JOIN enemy_armor_loadout al ON al.enemy_id = e.id
        GROUP BY e.unique_slug
        ORDER BY e.name
    """)

    # Load all rankings with joined weapon/skill data for best-of calculations
    base = _ranking_query()
    all_rankings = _query(base)

    by_enemy = defaultdict(list)
    for r in all_rankings:
        if r['is_two_handed']:
            if r['scenario'] != 'none':
                continue
        elif r['mastery'] == 'throwing':
            if r['scenario'] != 'duelist':
                continue
        else:
            if r['scenario'] != 'dg_duelist':
                continue

        ap_total, fatigue_per_hit = _calc_costs(r)
        avg_hits = r['avg_hits_to_kill']
        total_ap = avg_hits * ap_total
        total_fat = avg_hits * fatigue_per_hit

        by_enemy[r['enemy_slug']].append({
            'weapon_name': r['weapon_name'],
            'avg_hits_raw': avg_hits,
            'avg_hits': round(avg_hits, 1),
            'total_ap_raw': total_ap,
            'total_ap': round(total_ap, 1),
            'total_fat_raw': total_fat,
            'total_fat': round(total_fat),
        })

    top_by_ap = {}
    top_by_hits = {}
    top_by_fat = {}
    for slug, entries in by_enemy.items():
        top_by_ap[slug] = min(entries, key=lambda x: x['total_ap_raw'])
        top_by_hits[slug] = min(entries, key=lambda x: x['avg_hits_raw'])
        top_by_fat[slug] = min(entries, key=lambda x: x['total_fat_raw'])

    # Group by faction
    factions = {}
    for r in rows:
        subfaction = r['subfaction'] or 'Other'
        if subfaction not in factions:
            factions[subfaction] = []
        ap_entry = top_by_ap.get(r['unique_slug'], {})
        hits_entry = top_by_hits.get(r['unique_slug'], {})
        fat_entry = top_by_fat.get(r['unique_slug'], {})
        body_min, body_max = r['body_min'], r['body_max']
        head_min, head_max = r['head_min'], r['head_max']
        body_str = f'{body_min}-{body_max}' if body_min != body_max else str(body_max)
        head_str = f'{head_min}-{head_max}' if head_min != head_max else str(head_max)
        factions[subfaction].append({
            'name': r['name'],
            'slug': r['unique_slug'],
            'hitpoints': r['hitpoints'],
            'body_armor': body_str,
            'head_armor': head_str,
            'best_ap_weapon': ap_entry.get('weapon_name', ''),
            'best_ap': ap_entry.get('total_ap', 0),
            'best_hits_weapon': hits_entry.get('weapon_name', ''),
            'best_hits': hits_entry.get('avg_hits', 0),
            'best_fat_weapon': fat_entry.get('weapon_name', ''),
            'best_fat': fat_entry.get('total_fat', 0),
            'tier': r['tier'] or 0,
        })

    # Sort by SUBFACTION_ORDER, enemies by tier within each faction
    ordered = []
    for fname in SUBFACTION_ORDER:
        if fname in factions:
            factions[fname].sort(key=lambda e: e.get('tier', 0))
            ordered.append((fname, factions.pop(fname)))
    for fname, enemies in factions.items():
        enemies.sort(key=lambda e: e.get('tier', 0))
        ordered.append((fname, enemies))

    return ordered


@guides_bp.route('/')
def best_weapon_hub():
    factions = _load_hub_data()
    if not factions:
        abort(404)
    return render_template('guides/hub.html', factions=factions)


@guides_bp.route('/<enemy_slug>')
def best_weapon_against(enemy_slug):
    enemy = _load_enemy(enemy_slug)
    if not enemy:
        abort(404)

    rankings = _load_rankings(enemy_slug, 'dg_duelist')
    if not rankings:
        abort(404)

    all_scenarios = {
        'dg': _load_rankings(enemy_slug, 'dg'),
        'dg_duelist': rankings,
    }

    top_overall = rankings[0]  # best by AP
    top_by_hits = min(rankings, key=lambda r: float(r['avg_hits']))

    related = _load_related_enemies(enemy)

    immunities = []
    if enemy.get('is_bleed_immune'):
        immunities.append('bleeding')
    if enemy.get('is_injury_immune'):
        immunities.append('injuries')
    if enemy.get('is_morale_immune'):
        immunities.append('morale effects')

    all_enemies = _load_all_enemies()
    armor_loadout = _load_armor_loadout(enemy['id'])
    perks = enemy.get('perks', [])

    return render_template('guides/best_weapon.html',
                           enemy=enemy, rankings=rankings,
                           enemy_slug=enemy_slug,
                           top_overall=top_overall,
                           related=related,
                           immunities=immunities,
                           all_enemies=all_enemies,
                           armor_loadout=armor_loadout,
                           perks=perks,
                           tier=enemy.get('tier', 2),
                           faction=enemy.get('subfaction', ''),
                           all_scenarios=all_scenarios,
                           top_by_hits=top_by_hits)
