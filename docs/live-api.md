# Fonctionnalités temps réel du réseau M

*(Étude 2026-09-30. L'OTP2 GraphQL n'a pas de GTFS-RT ; le live existe ailleurs.)*

## Sources de données

| API | Endpoint | Realtime | Notes |
|---|---|---|---|
| **GraphQL OTP2** | `https://otp.mobilites-m.fr/otp/routers/default/index/graphql` | ❌ | aucun updater (config `{}`), `realtime:false, delay 0` partout |
| **REST legacy** | `https://data.mobilites-m.fr/api/routers/default/...` | ✅ | header **`origin`** requis (valeur libre) ; ~3 départs/pattern ; pas de rate-limit visible |
| Planner REST (OTP1) | `/api/routers/default/plan?fromPlace=X&toPlace=Y&mode=TRANSIT` | ❌ (`realTime:false`) | itinéraires avec tripId/geometry |
| GTFS-RT brut | — | — | aucun feed public (404 partout / SPA fallback) |
| GTFS static | `/api/gtfs/{feed}` (SEM, SE2, GSV, FUN, C38…) | — | ZIP valides |

## Endpoints REST legacy validés

| Endpoint | Code | Contenu |
|---|---|---|
| `/index/stops/{id}/stoptimes` | 200 | `times[] : tripId, serviceDay, scheduledDeparture, realtimeDeparture, departureDelay, realtime, realtimeState, occupancy` — **utilisé par le proxy** |
| `/index/clusters/{id}/stoptimes` | 204 vide | parentStation non exposé |
| `/index/trips/{id}/stoptimes` | 404 | non exposé |
| `/index/routes` (+ `/routes/{id}/stops`) | 200 | statique (couleurs, ordre des arrêts) |
| `/index/traveltimes` | 200 | temps de marche/parcours par tripId (ms) |
| `/plan?fromPlace=&toPlace=&date=MM-DD-YYYY&time=HH:MM` | 200 | itinéraires OTP1 |
| sans header `origin` | 403 | `{"error":"Missing origin header"}` |

## Correspondance GraphQL ↔ REST (preuve)

`trip { gtfsId }` (GraphQL) == `tripId` (REST), à l'octet : `SEM:32255069` des deux côtés. La clé `(serviceDay, scheduledDeparture)` dérive de ±1–3 s (imports GTFS différents) — matching possible mais fragile ; le matching par tripId est exact.

Fait notable : `/otp/routers/default/index/stops/SEM:0501/stoptimes` (OTP2, sans WAF) répond la même structure legacy **mais schedulée** — le temps réel n'existe que sur `data.mobilites-m.fr`.

## Implémentation (ce proxy)

1. La query client (ex. `_GRAPHQL_STOPTIMES` d'openpublictransport) est réécrite WAF-safe + **`gtfsId` injecté dans chaque bloc `trip {`**.
2. Réponse upstream : pour chaque stop id, fetch parallèle REST `…/stops/{id}/stoptimes` (12 s timeout, n casse pas le départ en cas d'échec).
3. Matching `(serviceDay, tripId)` puis fallback `scheduledDeparture` ±2 s (rows realtime only) ; injecte `realtime/realtimeDeparture/departureDelay/realtimeState/occupancy`.
4. reshape `stop[]`→objet, réponse au client identique en structure, valeurs live.

Cadence de fraîcheur observée : batch ≥ 60 s côté backend (2 appels à 31 s ⇒ 0 variation) — inutile de scanner < 60 s.