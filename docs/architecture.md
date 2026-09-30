# Architecture

## Vue d'ensemble

```
┌──────────────────────────────────────────────────────────────────────┐
│ Home Assistant (HAOS, ha.example.local)                                  │
│                                                                      │
│  ┌──────────────────────────┐      ┌───────────────────────────────┐ │
│  │ openpublictransport      │      │ otp_proxy_m (cette intégration)│ │
│  │ (HACS, non modifié)      │      │                               │ │
│  │                          │      │  OtpProxyView (HomeAssistant- │ │
│  │  config flow: GET /index │─────▶│  View, requires_auth=False)   │ │
│  │  scans: POST …/graphql   │      │  URL: /otp_proxy_m/{key}/{…}  │ │
│  └──────────────────────────┘      └──────────────┬────────────────┘ │
│                                                   │ aiohttp session  │
└───────────────────────────────────────────────────┼──────────────────┘
                                                    ▼
                                   WAF (règle : bloque stop\s*\() ──┐
                                                    │               │ 403 si
                                                    ▼               │ motif présent
                                   https://otp.mobilites-m.fr       │
                                   /otp/routers/default (OTP 2.7.0)─┘
```

## Composants

| Fichier | Rôle |
|---|---|
| `__init__.py` | Setup entry : enregistre la vue + route, forward `sensor` |
| `http.py` | `HomeAssistantView` sans auth : routage `/otp_proxy_m/{key}/…`, émulation `/index`, forward aiohttp, stats |
| `rewrite.py` | Réécriture GraphQL pure + reshape réponse (sans dépendance HA → testable hors HA) |
| `config_flow.py` | UI : nom, upstream, route_key + options flow |
| `sensor.py` | Sensor diagnostic (état + compteurs) |
| `const.py` | Constantes (upstream défaut, chemins, états) |

## Cycle de vie

1. `async_setup_entry` : crée `ProxyRuntime` (session aiohttp partagée HA + upstream) → `view.register_runtime(key, runtime)` ; la vue est créée une fois (singleton dans `hass.data[DOMAIN]["view"]`).
2. Chaque requête entrante est routée par `key` (défaut `m`) vers son runtime — plusieurs entries = plusieurs routes.
3. `async_unload_entry` : `unregister_runtime`, unload platforms.

## Décision clé : réécriture dans HA (pas de proxy externe)

Choix validé avec le mainteneur : **pas de conteneur/compose séparé** — le proxy vit **dans HA** (vue HTTP) pour :

- zéro dépendance à l'infrastructure HOMESERVER (exigence) ;
- URL locale `127.0.0.1:8123` (pas de port ni réseau supplémentaire) ;
- distribution HACS standard (custom repository) ;
- stats/erreurs visibles en entités HA.

## Schéma de réécriture

```
Entrée : {"query":"{ stop(id: \"SEM:0501\") { name stoptimesWithoutPatterns(…) { … } } }"}
Sortie : {"query":"{ stop: stops(ids: [\"SEM:0501\"]) { name stoptimesWithoutPatterns(…) { … } } }"}

Réponse upstream : {"data":{"stop":[ {…} ]}}   ← stops() → liste
Réponse proxy    : {"data":{"stop":  {…}  }}   ← reshape : liste[0] (ou null)
```

Le WAF inspecte le body **décodé** (JSON, unicode, form) et match `stop\s*\(` insensible à la casse — la sous-chaîne `stop(id:` ne doit apparaître nulle part, y compris dans les valeurs de chaînes (d'où le masquage des strings avant détection). La variante `Content-Type: application/graphql` n'est pas inspectée par le WAF mais n'est **pas utilisée** en path principal (dépendrait d'un contournement fragile, corrigible un jour).

## Garanties du réécriteur

- détecte `stop(` sur une version « masquée » (strings blankées) → pas de faux positif sur une valeur contenant `stop(id:` ;
- parse un `stop(...)` équilibré (nested parens supportés) ;
- accepte uniquement un id littéral string ; tout motif ambigu ⇒ `RewriteError` ⇒ 400 au client (jamais forwardé) ;
- reshape idempotent, ne touche que `data.stop`.

## Tests

`tests/test_rewrite.py` : 23 cas dont les queries **réelles** de `python-openpublictransport==0.2.0` comme fixtures (recherche `stops(name:)`, `nearest(lat,lon,…)` via fallback adresse, `_GRAPHQL_STOPTIMES`, résolution parent multi-plateformes `/N|/M`), rejets (variables, id non-string, args extra, unbalanced), reshape (objet, `[null]`, `[]`, absent).

## Perf

- Réécriture : O(n) par query (taille d'une query OTP ≈ 0,5–2 ko) — négligeable vs latence réseau (~100–300 ms upstream).
- scan_interval openpublictransport défaut 60 s ⇒ ~1 requête/minute/arrêt.
- Pas de cache (le client amont gère déjà) ; timeouts 30 s.