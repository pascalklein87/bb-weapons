# bb-weapons

The best-weapon-against rankings at **weapons.bloodngold.com**. Flask + MySQL.
Every weapon ranked by kill speed against each common enemy, from precomputed
Monte Carlo results.

Split out of the old `bb-wiki` monolith on 2026-07-13.

## Routes

- `/` - ranking hub (enemies grouped by faction)
- `/<enemy_slug>` - per-enemy weapon ranking. The "open in calculator" links
  point cross-host to `damage.bloodngold.com/?weapon=...`.
- legacy 301s: `/best-weapon-against` -> `/`, `/best-weapon-against/<enemy>`
  -> `/<enemy>`

Note: `/<enemy_slug>` is a root catch-all, so literal routes (`/robots.txt`,
`/sitemap.xml`, the legacy `/best-weapon-against*`) are matched first by Flask;
unknown slugs 404 -> redirect to `/`.

## Database: `bb_weapons`

Its own DB. Holds `guide_weapon_ranking` (5082 precomputed rows) plus a
self-contained copy of the reference tables the ranking reads: `weapon`,
`weapon_skill`, `enemy`, `enemy_armor_loadout`.

TODO: read the reference tables from the shared `bb_data` instead of this copy,
leaving `bb_weapons` holding only `guide_weapon_ranking`.

## Local

    cd webapp && python app.py      # http://127.0.0.1:5003/

## Deploy

    ssh root@46.225.141.38 "bash /var/www/bb-weapons/deploy.sh"

gunicorn on `127.0.0.1:8005`. Repo: github.com/pascalklein87/bb-weapons (public).
