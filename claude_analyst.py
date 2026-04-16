"""
Claude Analyst — Génère les prompts d'analyse pour chaque opportunité.
Les prompts sont loggés pour analyse manuelle via claude.ai.
"""
import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un expert en marchés de prédiction, spécialisé sur Polymarket.
Tu analyses des marchés et estimes des probabilités avec une précision maximale.

Pour chaque marché, tu dois :
1. Rechercher les informations les plus récentes sur le sujet
2. Analyser objectivement tous les signaux disponibles
3. Retourner une estimation de probabilité fondée sur les faits

RÈGLES ABSOLUES :
- Sois factuel et objectif, jamais partisan
- Si l'information est insuffisante, reflète-le dans la confidence
- Ne jamais inventer des faits ou des sources
- Prendre en compte les biais des marchés de prédiction

RÉPONSE : JSON uniquement, aucun texte avant ou après, aucun markdown.
Format exact :
{
  "prob_estimate": 0.XX,
  "confidence": "high" | "medium" | "low",
  "reasoning": "Explication courte et factuelle (2-3 phrases max)",
  "key_signals": ["signal 1", "signal 2", "signal 3"],
  "should_trade": true | false,
  "risk_flags": ["flag éventuel"]
}"""


def build_user_prompt(question: str, outcome: str, current_price: float,
                      days_left: float, volume_24h: float) -> str:
    return f"""Analyse ce marché Polymarket et estime la probabilité que l'outcome se réalise.

MARCHÉ : {question}
OUTCOME À ÉVALUER : {outcome}
PRIX ACTUEL DU MARCHÉ : {current_price:.2%} (= probabilité implicite actuelle)
JOURS AVANT RÉSOLUTION : {days_left:.1f} jours
VOLUME 24H : ${volume_24h:,.0f}

Recherche les informations les plus récentes sur ce sujet.
Estime si le prix actuel ({current_price:.2%}) est correct, sous-évalué ou sur-évalué.
Si notre estimation est > {current_price:.2%} + 6%, le trade est intéressant.

Réponds en JSON uniquement."""


def log_prompts_for_manual_analysis(opportunities: list[dict], max_prompts: int = 5):
    """Affiche les prompts prêts à copier-coller dans claude.ai."""
    top = opportunities[:max_prompts]
    if not top:
        logger.info("😴 Aucune opportunité à analyser ce cycle")
        return

    logger.info("\n" + "█" * 60)
    logger.info(f"  📋 {len(top)} PROMPTS À ANALYSER MANUELLEMENT SUR claude.ai")
    logger.info("█" * 60)
    logger.info("  ► Copie le SYSTEM PROMPT une seule fois dans le projet Claude,")
    logger.info("    puis envoie chaque USER PROMPT séparément.\n")

    logger.info("━" * 60)
    logger.info("  SYSTEM PROMPT (à mettre dans les instructions du projet) :")
    logger.info("━" * 60)
    logger.info(SYSTEM_PROMPT)

    for i, opp in enumerate(top):
        user_prompt = build_user_prompt(
            question=opp["question"],
            outcome=opp["outcome"],
            current_price=opp["price"],
            days_left=opp["days_left"],
            volume_24h=opp["volume_24h"],
        )

        logger.info("\n" + "━" * 60)
        logger.info(
            f"  USER PROMPT #{i+1} — {opp['outcome'][:40]} "
            f"@ {opp['price']:.0%} | {opp['days_left']:.0f}j | vol ${opp['volume_24h']:,.0f}"
        )
        logger.info("━" * 60)
        logger.info(user_prompt)

    logger.info("\n" + "█" * 60)
    logger.info("  ℹ️  Pour trader manuellement : polymarket.com")
    logger.info("█" * 60 + "\n")


def log_analysis_report(opportunities: list[dict]):
    pass
