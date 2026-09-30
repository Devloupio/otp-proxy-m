# OTP Proxy M

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![HA custom integration](https://img.shields.io/badge/Home%20Assistant-custom%20integration-red)](https://www.home-assistant.io)

Intégration Home Assistant + documentation pour consommer l'API **OpenTripPlanner 2 du réseau M** (Mobilités M, Grenoble — TAG / Transisère, `otp.mobilites-m.fr`) derrière le **WAF** qui bloque les requêtes GraphQL standard (`stop(id: …)`).

## Problème

Le réseau M expose une API OTP2 publique (<https://otp.mobilites-m.fr/otp/routers/default>) mais un WAF amont renvoie **HTTP 403** pour tout body JSON contenant la sous-chaîne `stop(id:` (regex `stop\s*\(`, insensible à la casse, appliquée au body décodé). Or :

- l'intégration HACS [openpublictransport](https://docs.openpublictransport.net/providers/otp-custom/) (provider `otp_custom`) interroge `{base}/index/graphql` en POST JSON avec exactement `{ stop(id: "…") { … stoptimesWithoutPatterns … } }` à **chaque scan** ;
- aucun retry ni fallback n'existe dans ce client (403 ⇒ erreur immédiate).

Sans contournement : recherche d'arrêt OK, mais **aucun horaire de départ** ne peut être affiché.

## Solution

`otp_proxy_m` est une intégration custom **sans dépendance externe** qui enregistre dans Home Assistant une vue HTTP aiohttp :

```
openpublictransport (non modifié)
   │  base URL : http://127.0.0.1:8123/otp_proxy_m/m/otp/routers/default
   ▼
otp_proxy_m (cette intégration)
   │  1. GET  /index            → 200 émulé (health-check du config flow)
   │  2. POST /index/graphql    → réécriture sûre :
   │       stop(id: "SEM:0501")  →  stop: stops(ids: ["SEM:0501"])
   │     + reshape réponse : data.stop (liste) → data.stop (objet)
   │  3. autres requêtes        → forward tel quel
   ▼
https://otp.mobilites-m.fr/otp/routers/default  (OTP2 2.7.0)
```

La réécriture est **sémantiquement identique** (alias GraphQL `stop:` + sélecteur pluriel `stops(ids:)` accepté par le WAF) et ne dépend d'aucun contournement fragile. Elle est testée unitairement contre les requêtes exactes envoyées par `python-openpublictransport` (recherche, stoptimes, parentStation, planConnection).

## Installation

### HACS (custom repository)

1. HACS → ⋮ → **Custom repositories** → `https://github.com/devloupio/otp-proxy-m` (catégorie *Integration*)
2. Télécharger **OTP Proxy M**
3. Redémarrer Home Assistant

### Manuel

```bash
cd /config/custom_components
wget https://github.com/devloupio/otp-proxy-m/releases/latest/download/otp-proxy-m.zip
unzip otp-proxy-m.zip
# → crée otp_proxy_m/
```

Puis redémarrer HA.

## Configuration

1. **Settings → Devices & Services → Add Integration → OTP Proxy M**
   - Nom : `OTP Proxy M`
   - Upstream (défaut) : `https://otp.mobilites-m.fr/otp/routers/default`
   - Clé de route (défaut) : `m`
2. **Integration départs** : ajouter *Public Transport Departures* (openpublictransport)
   - Entry type : **Departure Monitor**
   - Provider : **OTP2 — Eigene Instanz**
   - Base URL : `http://127.0.0.1:8123/otp_proxy_m/m/otp/routers/default`
   - API key : *(vide)*
   - Arrêt : `Saint-Martin-d'Hères Village` (ou tout arrêt du réseau M)

> Le proxy écoute uniquement en local (HA) ; aucune authentification n'est requise pour l'URL `/otp_proxy_m/...` (exposée par HA, protégée par votre réseau).

## Entités

- `sensor.otp_proxy_m_status` — santé du proxy + compteurs (`requests_total`, `rewrites_total`, `errors_total`, `upstream_403_total`, `last_error`).

## Limitations connues

- **Horaires théoriques uniquement** : l'OTP2 public du réseau M n'a **pas** d'updater GTFS-RT (`realtime: false` sur tous les départs testés).
- Modes `CABLE_CAR` (Bulles / Téléphérique) possiblement non mappés par openpublictransport.
- Requêtes GraphQL `stop(id: $variable)` **non supportées** par le réécriteur (clairement rejetées en 400, jamais transmises).

## Temps réel (v1.1.0+)

Le proxy **enrichit automatiquement les départs** avec les données live de l'API REST legacy (`data.mobilites-m.fr`, header `origin` requis) : `realtime`, `retard` (minutes dans les attributs HA), `realtimeState`, `occupancy`. Mécanisme : fetch REST des stops de la query, matching `trip { gtfsId }` (injecté automatiquement) == REST `tripId`, fallback `scheduledDeparture` ±2 s.

Les **itinéraires** (Trip Planner) restent théoriques : le planner legacy ne renvoie pas de realtime exploitable.

## Dépannage

- Activer les logs debug : `configuration.yaml` →

```yaml
logger:
  logs:
    custom_components.otp_proxy_m: debug
```

- Le sensor `status` passe en `error`/`down` avec `last_error` explicite (timeout, 403, rewrite).

## Développement

```bash
python3 -m pytest tests/
```

Voir [docs/](docs/) : [architecture](docs/architecture.md) · [api](docs/api.md) · [installation](docs/installation.md) · [waf](docs/waf.md) · [security](SECURITY.md)

## License

[MIT](LICENSE)