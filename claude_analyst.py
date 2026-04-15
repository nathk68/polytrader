"""
Claude Analyst — Le cerveau du bot.
Utilise l'API Claude + web_search pour analyser chaque marché
et estimer une probabilité fondée sur des données réelles.
"""
import json
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"

ANALYST_SYSTEM_PROMPT = """Tu es un expert en marchés de prédiction, spécialisé sur Polymarket.
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


def analyze_market(
    question: str,
    outcome: str,
    current_price: float,
    days_left: float,
    volume_24h: float,
) -> Optional[dict]:
    user_prompt = f"""Analyse ce marché Polymarket et estime la probabilité que l'outcome se réalise.

MARCHÉ : {question}
OUTCOME À ÉVALUER : {outcome}
PRIX ACTUEL DU MARCHÉ : {current_price:.2%} (= probabilité implicite actuelle)
JOURS AVANT RÉSOLUTION : {days_left:.1f} jours
VOLUME 24H : ${volume_24h:,.0f}

Recherche les informations les plus récentes sur ce sujet.
Estime si le prix actuel ({current_price:.2%}) est correct, sous-évalué ou sur-évalué.
Si notre estimation est > {current_price:.2%} + 6%, le trade est intéressant.

Réponds en JSON uniquement."""

    payload = {
        "model": MODEL,
        "max_tokens": 1000,
        "system": ANALYST_SYSTEM_PROMPT,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": user_prompt}],
    }

    try:
        resp = requests.post(ANTHROPIC_API_URL, json=payload, timeout=45)
        resp.raise_for_status()
        data = resp.json()

        text_blocks = [
            block["text"]
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]

        if not text_blocks:
            logger.warning(f"Pas de réponse texte de Claude pour: {question[:50]}")
            return None

        raw_text = text_blocks[-1].strip()

        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        raw_text = raw_text.strip()

        analysis = json.loads(raw_text)

        logger.info(
            f"🧠 Claude: {outcome[:30]} | "
            f"Est: {analysis.get('prob_estimate', 0):.2%} vs Mkt: {current_price:.2%} | "
            f"Confiance: {analysis.get('confidence','?')} | "
            f"Trade: {'✅' if analysis.get('should_trade') else '❌'}"
        )
        return analysis

    except json.JSONDecodeError as e:
        logger.error(f"Erreur parsing JSON Claude: {e}")
        return None
    except requests.RequestException as e:
        logger.error(f"Erreur API Claude: {e}")
        return None
    except Exception as e:
        logger.error(f"Erreur inattendue: {e}")
        return None


def batch_analyze(opportunities: list[dict], max_analyses: int = 5) -> list[dict]:
    enriched = []
    analyzed = 0

    logger.info(f"🧠 Analyse Claude sur {min(len(opportunities), max_analyses)} marchés...")

    for opp in opportunities[:max_analyses]:
        analysis = analyze_market(
            question=opp["question"],
            outcome=opp["outcome"],
            current_price=opp["price"],
            days_left=opp["days_left"],
            volume_24h=opp["volume_24h"],
        )

        if analysis is None:
            opp["claude_analyzed"] = False
            opp["should_trade"] = False
            enriched.append(opp)
            continue

        analyzed += 1
        claude_prob = float(analysis.get("prob_estimate", opp["prob_estimate"]))
        real_edge = round(claude_prob - opp["price"], 4)

        opp.update({
            "claude_analyzed":   True,
            "prob_estimate":     claude_prob,
            "edge":              real_edge,
            "claude_confidence": analysis.get("confidence", "low"),
            "claude_reasoning":  analysis.get("reasoning", ""),
            "claude_signals":    analysis.get("key_signals", []),
            "should_trade":      analysis.get("should_trade", False),
            "risk_flags":        analysis.get("risk_flags", []),
        })
        opp["score"] = _recompute_score(opp)
        enriched.append(opp)

    tradeable = [o for o in enriched if o.get("should_trade") and o.get("edge", 0) > 0.05]
    tradeable.sort(key=lambda x: x["score"], reverse=True)

    logger.info(f"✅ {analyzed} analyses | {len(tradeable)} opportunités validées")
    return tradeable


def _recompute_score(opp: dict) -> float:
    base_score = opp.get("score", 0)
    confidence = opp.get("claude_confidence", "low")
    edge = opp.get("edge", 0)
    days_left = opp.get("days_left", 99)
    conf_mult = {"high": 1.5, "medium": 1.0, "low": 0.4}.get(confidence, 0.4)
    return round(
        base_score * conf_mult
        + edge * 200
        + (20 if days_left <= 3 else 5)
        - (len(opp.get("risk_flags", [])) * 10),
        2
    )


def log_analysis_report(opportunities: list[dict]):
    if not opportunities:
        logger.info("📊 Aucune opportunité validée par Claude ce cycle")
        return

    logger.info("\n" + "═" * 60)
    logger.info("  📊 RAPPORT ANALYSE CLAUDE")
    logger.info("═" * 60)

    for i, opp in enumerate(opportunities[:5]):
        logger.info(
            f"\n  #{i+1} [{opp.get('strategy','?')}] "
            f"Confiance: {opp.get('claude_confidence','?').upper()}"
        )
        logger.info(f"  Q: {opp['question'][:65]}")
        logger.info(f"  Outcome : {opp['outcome']}")
        logger.info(f"  Prix mkt: {opp['price']:.2%} → Claude: {opp['prob_estimate']:.2%} (edge: {opp['edge']:+.2%})")
        logger.info(f"  Raison  : {opp.get('claude_reasoning','N/A')}")
        signals = opp.get("claude_signals", [])
        if signals:
            logger.info(f"  Signaux : {' | '.join(signals[:3])}")
        flags = opp.get("risk_flags", [])
        if flags:
            logger.warning(f"  ⚠️  Risques: {', '.join(flags)}")

    logger.info("\n" + "═" * 60)
