# Scanner multisports — Dropping odds

## Ce que fait cette première version
- Récupère les sports actifs et leurs cotes via The Odds API v4.
- Enregistre les observations dans SQLite.
- Compare les premières et dernières cotes observées pour chaque sélection/bookmaker.
- Signale les baisses qui atteignent le seuil configuré chez plusieurs bookmakers.
- Affiche l'historique et les signaux dans un tableau de bord Streamlit.

## Limites importantes
- Ce n'est pas un prédicteur de résultats et cela ne garantit aucun bénéfice.
- Une baisse de cote ne prouve pas qu'il s'agit de "sharp money".
- Le scan est manuel dans cette version : il faut cliquer sur « Scanner maintenant » à chaque relevé.
- Le premier relevé sert de base. Les signaux deviennent pertinents après plusieurs relevés.
- La couverture dépend des sports, marchés et bookmakers inclus dans votre forfait et de la région demandée.
- Le code ne place aucun pari et ne gère aucune bankroll.

## Installation
Python 3.10+ recommandé.

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate
# macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
```

Créer une clé sur https://the-odds-api.com/ puis configurer la variable d'environnement `ODDS_API_KEY`.
Copier `.env.example` en `.env` et renseigner la clé. Streamlit ne charge pas automatiquement `.env` sans python-dotenv ; le plus simple est de définir la variable dans le terminal :

Windows PowerShell:
```powershell
$env:ODDS_API_KEY="VOTRE_CLE"
streamlit run app.py
```

macOS/Linux:
```bash
export ODDS_API_KEY="VOTRE_CLE"
streamlit run app.py
```

## Configuration facultative
- `ODDS_REGIONS=eu` (défaut)
- `ODDS_MARKETS=h2h` (défaut)
- `DROP_THRESHOLD=7` (baisse en pourcentage, défaut)
- `MIN_BOOKMAKERS=2` (défaut)
- `POLL_SECONDS=300` (valeur indicative ; cette version ne planifie pas le scan automatiquement)

## Coûts API
The Odds API facture les requêtes selon le nombre de régions et de marchés demandés. Le coût et la disponibilité varient selon le forfait. Commencer avec une seule région et un seul marché, puis vérifier les en-têtes de quota renvoyés par l'API.

Documentation : https://the-odds-api.com/liveapi/guides/v4/
