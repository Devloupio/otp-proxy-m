# Changelog

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) — versionnement [sémantique](https://semver.org/lang/fr/).

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