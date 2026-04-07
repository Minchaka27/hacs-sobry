# Sobry Energy

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Intégration Home Assistant pour le fournisseur d'électricité **Sobry**.

Cette intégration vous permet de récupérer les prix de l'électricité day-ahead pour la France via l'API publique Sobry.

## Caractéristiques

- Prix en temps réel pour aujourd'hui et demain
- Support des options TURPE (CU, CU4, MU4, MUDT, LU)
- Affichage HT ou TTC (pour les particuliers)
- Segments C5 (≤36kVA) et C4 (>36kVA)
- Capteurs : prix actuel, min, max, moyen, médian, prochaine heure
- Service pour récupérer l'historique des prix
- Pas d'authentification requise

## Installation

### Via HACS (recommandé)

1. Allez dans **HACS** > **Intégrations** > **Menu (3 points)** > **Dépôts personnalisés**
2. Ajoutez l'URL de ce dépôt
3. Sélectionnez **Catégorie : Intégration**
4. Cliquez sur **Ajouter**
5. Recherchez "Sobry" et installez
6. Redémarrez Home Assistant

### Manuellement

1. Copiez le dossier `custom_components/sobry` dans votre répertoire `config/custom_components/`
2. Redémarrez Home Assistant

## Configuration

1. Allez dans **Paramètres** > **Appareils et services** > **Ajouter une intégration**
2. Recherchez "Sobry Energy"
3. Sélectionnez votre configuration :
   - **Segment** : C5 (≤36kVA) ou C4 (>36kVA)
   - **Option TURPE** : selon votre contrat
   - **Profil** : Particulier ou Pro
   - **Affichage** : HT ou TTC

## Capteurs disponibles

| Capteur | Description |
|---------|-------------|
| `sensor.sobry_current_price` | Prix actuel (€/kWh) |
| `sensor.sobry_min_price` | Prix minimum du jour |
| `sensor.sobry_max_price` | Prix maximum du jour |
| `sensor.sobry_avg_price` | Prix moyen du jour |
| `sensor.sobry_median_price` | Prix médian du jour |
| `sensor.sobry_next_hour_price` | Prix de l'heure prochaine |

Chaque capteur inclut des attributs avec le détail du calcul (TURPE, accise, etc.).

## Options TURPE

### C5 (BT ≤ 36kVA)

| Option | Description |
|--------|-------------|
| CU | Courte Utilisation - prix constant |
| CU4 | 4 plages horaires (HP/HC × Haute/Basse saison) |
| MU4 | Moyenne Utilisation 4 plages |
| MUDT | Moyenne Utilisation Double Tarif |
| LU | Longue Utilisation - prix constant bas |

### C4 (BT > 36kVA)

| Option | Description |
|--------|-------------|
| CU | Courte Utilisation |
| LU | Longue Utilisation |

## Accès aux prix du jour

Le capteur **Prix actuel** inclut un attribut `all_prices` contenant les 24 prix horaires de la journée :

```yaml
# Exemple d'attributs sur sensor.sobry_current_price
all_prices:
  - hour: 0
    timestamp: "2025-01-15T00:00:00+01:00"
    price: 0.156
    spot_price: 0.089
  - hour: 1
    timestamp: "2025-01-15T01:00:00+01:00"
    price: 0.142
    spot_price: 0.078
  # ... etc pour les 24h
prices_count: 24
```

## Services

### `sobry.get_all_prices`

Récupère tous les prix du jour (24h) dès qu'ils sont disponibles (~13h).

**Paramètres :**

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `config_entry_id` | string | Non | ID config à utiliser |
| `segment` | string | Non | C5 ou C4 (défaut: C5) |
| `turpe` | string | Non | CU, CU4, MU4, MUDT, LU |
| `profil` | string | Non | particulier ou pro |
| `display` | string | Non | HT ou TTC |

**Exemple d'utilisation :**

```yaml
service: sobry.get_all_prices
data: {}
```

**Réponse :**

```json
{
  "success": true,
  "date": "2025-01-15",
  "count": 24,
  "prices": [
    {"hour": 0, "timestamp": "...", "price_eur_kwh": 0.156, ...},
    ...
  ],
  "statistics": {"min": 0.12, "max": 0.28, "average": 0.18}
}
```

### `sobry.get_price_history`

Récupère l'historique des prix entre deux dates.

**Paramètres :**

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `start_date` | string | Oui | Date début (YYYY-MM-DD) |
| `end_date` | string | Oui | Date fin (YYYY-MM-DD) |
| `config_entry_id` | string | Non | ID config à utiliser |
| `segment` | string | Non | C5 ou C4 (défaut: C5) |
| `turpe` | string | Non | CU, CU4, MU4, MUDT, LU |
| `profil` | string | Non | particulier ou pro |
| `display` | string | Non | HT ou TTC |
| `granularity` | string | Non | hourly ou daily (défaut: hourly) |

**Exemple d'utilisation dans une automatisation :**

```yaml
service: sobry.get_price_history
data:
  start_date: "2025-01-01"
  end_date: "2025-01-31"
  granularity: daily
```

## Notes

- Les données sont mises à jour automatiquement toutes les heures
- Les prix day-ahead sont publiés vers 13h CET pour le lendemain
- Limite de 100 requêtes/minute sur l'API

## Licence

MIT
