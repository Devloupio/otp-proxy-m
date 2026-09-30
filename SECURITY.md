# Politique de sécurité

## Signalement

Signalez les vulnérabilités en créant une issue privée sur <https://github.com/Devloupio/otp-proxy-m/issues> (compte requis) ou en contactant le mainteneur. Réponse visée : 7 jours.

## Périmètre

- `custom_components/otp_proxy_m/` (vue HTTP, réécriture GraphQL, config flow).

## Menaces prises en compte

- **Exposition** : la vue `/otp_proxy_m/{key}/...` est volontairement **sans authentification** (les clients OTP2 comme openpublictransport n'envoient pas de token HA). Elle ne doit être joignable que depuis un réseau de confiance ; n'exposez jamais 8123 vers Internet sans reverse proxy authentifiant.
- **SSRF limité** : l'upstream est fixé à la configuration de l'entry (défaut `otp.mobilites-m.fr`) ; le chemin forwardé est suffixé à cette base, aucune URL arbitraire n'est construite depuis la requête client.
- **Headers** : seuls `accept`, `x-api-key`, `user-agent` du client sont forwardés ; les cookies/authorizations sont supprimés.
- **Réécriture** : les requêtes contenant un motif non sûr (variables `stop(id: $id)`, ids non-littéraux) sont **rejetées en 400** sans transmettre au serveur distant.
- **Secrets** : l'intégration n'en stocke aucun (pas de clé API requise par le réseau M).
- **Journalisation** : jamais le body complet en log — seulement URL + statut/erreur ; les ids d'arrêt apparaissent dans les logs uniquement en debug.

## Versions supportées

| Version | Support |
|---|---|
| 1.0.x | ✅ |