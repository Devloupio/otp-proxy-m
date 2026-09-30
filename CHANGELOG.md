# Changelog

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) — versionnement [sémantique](https://semver.org/lang/fr/).

## [1.1.2] - 2026-09-30

### Fixed

- **Temps réel effectif** : la query stoptimes d'openpublictransport ne demande pas `trip { gtfsId }` ⇒ matching REST impossible ⇒ patch silencieusement no-op. Le proxy **injecte `gtfsId`** dans chaque bloc `trip {` des requêtes enrichissables et le compteur n'incrémente plus à vide.
- Fallback de matching `(serviceDay, scheduledDeparture)` ±2 s (dérive d'import OTP1/OTP2 ~1 s), rows realtime uniquement.
- Ids composes `"SEM:0501|SEM:0502"` correctement splittés côté enrichissement.

## [1.1.1] - 2026-09-30

### Fixed

- Matching stoptimes par index global `(serviceDay, tripId)` mutualisé : les objets stop de la réponse n'exposent `gtfsId` que si la query le demande — le matching ne peut pas s'appuyer sur `stop.gtfsId`.

## [1.1.0] - 2026-09-30

### Added

- **Enrichissement temps réel des départs** (config par défaut, peut se couper en omettant l'API REST) : la GraphQL OTP2 du réseau M n'a aucun updater GTFS-RT (`realtime:false` partout), mais la proxy legacy REST `data.mobilites-m.fr` expose les mêmes données en live (header `origin` requis). Matching clé : `trip { gtfsId }` == REST `tripId` (byte-identique). Injecte `realtime`, `realtimeDeparture`, `departureDelay` (+ `realtimeState`, `occupancy`).
- **Auto-réparation** des entries openpublictransport « Trip Planner » sans `otp_base_url` (bug upstream config_flow.py `trip_settings` : URL persistée seulement si API key non vide) : détectées au démarrage du proxy, corrigées + reload.
- Sensor status : `realtime_enriched_total`, `last_enriched_at`.

### Non enrichi (limites API)

- `planConnection` : le planner REST legacy renvoie `realTime:false` ⇒ itinéraires restent théoriques.
- `/index/trips/{id}/stoptimes` et `/index/clusters/*/stoptimes` : non exposés par le backend M.
- Aucun feed GTFS-RT public accessible.

## [1.0.0] - 2026-09-30

### Added

- Intégration custom Home Assistant `otp_proxy_m` : vue HTTP aiohttp reverse-proxy vers l'OTP2 du réseau M (`otp.mobilites-m.fr`), sans dépendance pip externe.
- Réécriture GraphQL WAF-safe : `stop(id: "X")` → `stop: stops(ids: ["X"])` + reshape de la réponse (liste → objet), compatible avec toutes les requêtes de `python-openpublictransport==0.2.0` (recherche, nearest, stoptimes, parentStation).
- Emulation `GET /index` (200 + serverInfo) : le config flow d'openpublictransport health-check ce chemin, absent (404) sur l'OTP public.
- Config flow + options flow (upstream modifiable), route key paramétrable (`/otp_proxy_m/{key}/...`).
- Sensor de diagnostic `sensor.otp_proxy_m_status` (compteurs requêtes/rewrites/erreurs/403, last_error, timestamps).
- Translations FR/EN, tests pytest (23 cas, queries réelles comme fixtures), CI Gitea Actions (lint + tests).
- Docs : `docs/architecture.md`, `docs/api.md`, `docs/installation.md`, `docs/waf.md`, `SECURITY.md`.

### Constats d'analyse (réseau M)

- WAF : regex `stop\s*\(` insensible à la casse sur body décodé (JSON, form, URL) — 403 à 100 % sur la requête stoptimes standard, `stops(ids:)` toléré systématiquement.
- API OTP2 2.7.0 ; pas d'updater GTFS-RT (horaires théoriques uniquement).
- `data.mobilites-m.fr` ne sert PAS l'API OTP (SPA web) ; endpoint valide : `https://otp.mobilites-m.fr/otp/routers/default`.

[1.0.0]: https://github.com/Devloupio/otp-proxy-m/releases/tag/v1.0.0