# Installation

## Prérequis

- Home Assistant ≥ 2024.6 (HAOS recommandé)
- HACS installé (pour la voie HACS)
- Accès réseau sortant HTTPS vers `otp.mobilites-m.fr`
- Intégration [openpublictransport](https://github.com/NerdySoftPaw/openpublictransport) ≥ v2026.9.0 (HACS)

## Voie HACS (recommandée)

1. **HACS → ⋮ → Custom repositories**
2. URL : `https://github.com/devloupio/otp-proxy-m` — catégorie : **Integration**
3. **Download** « OTP Proxy M » (dernière release)
4. **Redémarrer HA**

## Voie manuelle (SSH)

```bash
# depuis la machine hébergeant /config (ou via addon SSH HAOS)
cd /config/custom_components
wget https://github.com/devloupio/otp-proxy-m/releases/latest/download/otp-proxy-m.zip
unzip otp-proxy-m.zip   # → otp_proxy_m/
# restart HA : UI, ou `ha core restart` en SSH HAOS
```

## Configuration

### 1. Proxy

Settings → Devices & Services → **Add Integration** → **OTP Proxy M**

| Champ | Valeur |
|---|---|
| Nom | `OTP Proxy M` |
| Upstream | `https://otp.mobilites-m.fr/otp/routers/default` |
| Clé de route | `m` |

Vérifier : `sensor.otp_proxy_m_status` = `ok` après le premier appel (test : curl `http://127.0.0.1:8123/otp_proxy_m/m/otp/routers/default/index` ou ouvrir `http://<ha>:8123/otp_proxy_m/m/otp/routers/default/index`).

### 2. Départs (openpublictransport)

Settings → Add Integration → **Public Transport Departures**

1. Entry type : **Departure Monitor** (Abfahrtsanzeige)
2. Provider : **OTP2 — Eigene Instanz (URL + optionaler API Key)**
3. Base URL : `http://127.0.0.1:8123/otp_proxy_m/m/otp/routers/default` — le suffixe `/index/graphql` est ajouté automatiquement
4. API key : laisser vide
5. Arrêt : `Saint-Martin-d'Hères Village` (fuzzy : `Saint-Martin-d'Heres Village` marche aussi) — les plateformes `SEM:0501`/`SEM:0502` sont fusionnées
6. Settings : nombre de départs, types (Bus…), scan interval (60 s défaut), filtres ligne/destination optionnels

## Vérification finale

```bash
# depuis un LAN trusted (sinon 401) :
curl -s "http://127.0.0.1:8123/otp_proxy_m/m/otp/routers/default/index" | jq
```

Dans HA → Outils de développement → États : `sensor.<arrêt>_departures` → attribut `departures` rempli (horaires théoriques C7 …).

## Mise à jour

HACS → OTP Proxy M → Update (via mirror GitHub) ; ou re-télécharger la release (voie manuelle).

## Désinstallation

1. Supprimer les entries openpublictransport qui pointent vers le proxy
2. Supprimer l'entry OTP Proxy M
3. HACS → supprimer le repository → restart HA