# API du proxy

## Endpoints exposés (dans HA)

### `GET /otp_proxy_m/{key}/index`

Émulation du endpoint index (absent sur l'OTP public) pour le health-check du config flow openpublictransport.

```json
{"serverInfo": {"name": "otp-proxy-m", "otpVersion": "2.7.0", "upstream": "https://otp.mobilites-m.fr/otp/routers/default"}}
```

### `POST /otp_proxy_m/{key}/otp/routers/default/index/graphql`

Corps JSON `{"query": "...", "variables": {...}?}`. Réécriture automatique `stop(id:)` → `stop: stops(ids:)`; reshape réponse liste→objet. `Content-Type: application/graphql` forwardé tel quel (non inspecté par le WAF).

Erreurs :

| Code | Cas |
|---|---|
| 400 | body JSON invalide, query non-string, motif `stop(…)` non ré-écrivable (variables, id non-littéral, args extra, parens déséquilibrées) |
| 502 | upstream 403 (WAF évolutif) / erreur connexion |
| 504 | timeout upstream (> 30 s) |
| 404 | route `{key}` inconnue (entry non chargée) |

### Tout autre `GET/POST /otp_proxy_m/{key}/{path}`

Forward tel quel (suffixe au upstream configuré, query string conservée, headers `accept`/`x-api-key`/`user-agent` seulement).

## Sensor de diagnostic

`sensor.otp_proxy_m_status`

| Attribut | Description |
|---|---|
| `route_url` | base URL à donner aux clients |
| `upstream` | URL distante configurée |
| `requests_total` / `rewrites_total` | compteurs cumulés |
| `errors_total` / `upstream_403_total` | erreurs (403 = WAF a changé ?) |
| `last_error` | dernier message d'erreur |
| `last_request_at` / `last_success_at` | timestamps ISO UTC |

États : `ok` / `error` (erreurs mais succès récent) / `down` (aucun succès depuis > 5 min malgré des requêtes).

## API upstream (réseau M, pour référence)

- Base : `https://otp.mobilites-m.fr/otp/routers/default`
- GraphQL : `POST {base}/index/graphql`
- Version : OTP 2.7.0 ; **pas de GTFS-RT** (horaires théoriques).
- Recherche : `{ stops(name: "X") { gtfsId name lat lon … } }`
- Départs : `{ stop(id: "SEM:0501") { stoptimesWithoutPatterns(numberOfDepartures: n) { … } } }` — *uniquement via ce proxy* (WAF).
- `data.mobilites-m.fr` : SPA web + API REST legacy non-OTP (ex. `/api/routers/default/index/stops/SEM:0501/stoptimes` avec header `origin`) — **non utilisé** par cette intégration.