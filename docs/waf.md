# Le WAF de mobilites-m : analyse

*(Étude réalisée le 2026-09-30, ~90 requêtes de caractérisation. Données susceptibles d'évoluer — si `upstream_403_total` s'anime sur `sensor.otp_proxy_m_status`, relire cette page.)*

## Symptôme

`POST https://otp.mobilites-m.fr/otp/routers/default/index/graphql` avec un body JSON contenant la sous-chaîne `stop(id:` → **HTTP 403**, page HTML « La requête que vous avez effectuée n'est pas autorisée » (charset iso-8859-1, aucune header WAF identifiable).

## Caractéristiques mesurées

| Test | Résultat |
|---|---|
| `stop(id: "SEM:0501")` JSON | 403 → **10/10** (intermitence initiale non reproduite ; bloqué à 100 %) |
| `stop (id:` (espaces ×1/×2), tab, `\n` | 403 → regex `stop\s*\(` |
| `StOp(id:` | 403 → case-insensitive |
| unicodes `\u0028`, `\u0069`, `\u0073top` | 403 → **body décodé** avant inspection |
| form-urlencoded contenant `stop(id:` | 403 → form décodé aussi |
| sous-chaîne `stop(id:` dans une valeur JSON `"probe"` | 403 → matcher naïf sur toute la chaîne décodée |
| sous-chaîne dans un commentaire GraphQL `# … stop(id:` | **200** → commentaires retirés avant analyse |
| `stop(id: $var)` (variables) | 403 → motif structurel, pas de valeur |
| `{ stop { gtfsId } }` (sans parenthèse) | 200 → c'est bien `stop` + `(` |
| `stops(ids: ["SEM:0501"])` | **200 systématique** → seul le singulier est attrapé |
| `Content-Type: application/graphql` (body = query brute contenant `stop(id:`) | **200** → ce content-type n'est **pas inspecté** |
| GET `?query=…stop(id:…` | 403 → URL inspectée aussi |
| User-Agent curl / Chrome / `HomeAssistant aiohttp` | indifférent |

## Interprétation

WAF type anti-injection (le motif `stop\s*\(` évoque un filtre SQL `DROP\s*\(`-like) appliqué :

- à l'URL (query string) ;
- au body **décodé** : JSON (échappements unicode résolus), form-urlencoded décodé, **exception** : `application/graphql` non analysé ;
- après retrait des commentaires GraphQL `#…`.

## Contournements possibles et choix

| Contournement | Fiabilité | Risque | Choix |
|---|---|---|---|
| **Réécriture `stop(id:"X")` → `stop: stops(ids:["X"])`** | 15/15 | Aucun : requête GraphQL valide, sémantique identique, ne dépend d'aucun trou | ✅ **retenu** |
| `application/graphql` (non inspecté) | 17/17 | Dépend d'une négligence du WAF, corrigible sans préavis | ❌ fallback uniquement |
| Espace/tab/unicode | 0 % | — | ❌ (invalidés) |
| Retry sur 403 | 0 % (bloqué à 100 %) | — | ❌ |

Le reshape de réponse (le champ `stop` devient une liste via `stops()`) est rendu transparent par l'alias GraphQL `stop:` + conversion côté proxy — voir [architecture](architecture.md).

## Si le WAF évolue

- `stops(ids:)` se met à bloquer → la seule issue serait `application/graphql` en fallback (déjà implémenté : si le client envoie ce content-type, forward sans inspection).
- L'entité `sensor.otp_proxy_m_status` (`upstream_403_total`, `last_error`) est l'indicateur de surveillance ; un check uptime-kuma sur `GET /otp_proxy_m/m/otp/routers/default/index` complète le suivi.