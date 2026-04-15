# 🤖 PolyBot v2 — Polymarket + Claude AI

Bot de trading automatique pour Polymarket avec analyse Claude + web search.

## Fichiers

| Fichier | Rôle |
|---|---|
| `main.py` | Boucle principale + orchestration |
| `scanner.py` | Scan marchés Polymarket + filtrage |
| `claude_analyst.py` | Analyse Claude API + web_search |
| `risk.py` | Kelly Criterion + position sizing |
| `trader.py` | Client CLOB + exécution ordres |
| `config.py` | Configuration centralisée |

## Démarrage

```bash
cp .env.example .env
# Remplis PRIVATE_KEY et ANTHROPIC_API_KEY

pip install -r requirements.txt
python main.py   # DRY RUN par défaut
```

## Déploiement Railway

1. Push sur GitHub
2. New Project → Deploy from GitHub
3. Ajoute les variables dans Railway → Variables :
   - `PRIVATE_KEY`
   - `ANTHROPIC_API_KEY`
   - `DRY_RUN=false`
   - `BANKROLL_USDC=20`

## ⚠️ Avertissement

Trading = risque de perte totale. Commence toujours en DRY RUN.
