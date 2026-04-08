#!/usr/bin/env python3
"""
Extract research themes from the 18 futurology domains.
Analyzes card content to identify clustered research areas,
then scores them using backcasting methodology.
"""

import json
import re
from collections import defaultdict
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "app-launcher" / "data" / "futurology" / "futurology_data.json"
OUTPUT_PATH = Path(__file__).parent / "data" / "research_themes.json"


def load_data():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_time_horizon(nen_str: str) -> int:
    """Convert time horizon string like '〜2030' to a year number."""
    match = re.search(r"(\d{4})", nen_str or "")
    if match:
        return int(match.group(1))
    return 2050  # default if unclear


def extract_research_themes(data: dict) -> list[dict]:
    """
    Extract research themes from each domain's sub-categories.
    Each 中項目 becomes a research theme, enriched with card data.
    """
    themes = []
    theme_id = 0

    for dai in data["dai_items"]:
        domain_no = dai["no"]
        domain_name = dai["name"]
        map_theme = dai["mapTheme"]
        card_count = dai["cardCount"]

        # Extract themes from 中項目 (sub-categories)
        for chu_info in dai.get("chuFromYosoSheet", []):
            chu_name = chu_info["chuKomoku"]
            sho_items = chu_info.get("shoKomoku", [])

            # Get cards for this 中項目
            cards = dai.get("cardsByChu", {}).get(chu_name, [])

            # Analyze time horizons
            years = [parse_time_horizon(c.get("nen", "")) for c in cards]
            earliest = min(years) if years else 2050
            latest = max(years) if years else 2050

            # Collect source books
            source_books = set()
            all_summaries = []
            for card in cards:
                all_summaries.append(card.get("summary", ""))
                for src in card.get("sources", []):
                    source_books.add(src.get("book", ""))

            theme_id += 1
            themes.append({
                "id": theme_id,
                "domainNo": domain_no,
                "domainName": domain_name,
                "mapTheme": map_theme,
                "themeName": chu_name,
                "subTopics": sho_items,
                "cardCount": len(cards),
                "earliestYear": earliest,
                "latestYear": latest,
                "sourceBooks": sorted(source_books),
                "summaries": all_summaries,
            })

    return themes


def compute_backcasting_scores(themes: list[dict], target_year: int = 2035) -> list[dict]:
    """
    Score each research theme using backcasting methodology.

    Scoring dimensions:
    1. Temporal Urgency: how soon predictions materialize relative to target
    2. Evidence Density: number of supporting prediction cards
    3. Cross-domain Relevance: how the theme connects to other domains
    4. Transformation Potential: based on time span and scope of predictions
    """
    # Build keyword index for cross-domain analysis
    theme_keywords = {}
    for t in themes:
        words = set()
        for s in t["subTopics"]:
            words.update(s.replace("の", " ").replace("が", " ").replace("を", " ").split())
        for s in t["summaries"]:
            words.update(s.replace("の", " ").replace("が", " ").replace("を", " ").split())
        theme_keywords[t["id"]] = words

    # Compute cross-domain similarity
    domain_themes = defaultdict(list)
    for t in themes:
        domain_themes[t["domainNo"]].append(t["id"])

    max_cards = max(t["cardCount"] for t in themes) if themes else 1

    for t in themes:
        # 1. Temporal Urgency (0-100): earlier = more urgent
        years_until = t["earliestYear"] - 2026
        if years_until <= 0:
            urgency = 100  # already happening
        elif years_until <= 5:
            urgency = 90
        elif years_until <= 10:
            urgency = 70
        elif years_until <= 20:
            urgency = 50
        elif years_until <= 30:
            urgency = 30
        else:
            urgency = 10
        t["temporalUrgency"] = urgency

        # 2. Evidence Density (0-100): more cards = more evidence
        t["evidenceDensity"] = round((t["cardCount"] / max_cards) * 100) if max_cards > 0 else 0

        # 3. Cross-domain Relevance (0-100)
        my_words = theme_keywords[t["id"]]
        related_domains = set()
        for other_t in themes:
            if other_t["domainNo"] != t["domainNo"]:
                other_words = theme_keywords[other_t["id"]]
                overlap = len(my_words & other_words)
                if overlap >= 3:
                    related_domains.add(other_t["domainNo"])
        t["crossDomainRelevance"] = min(100, len(related_domains) * 10)
        t["relatedDomains"] = sorted(related_domains)

        # 4. Transformation Potential (0-100): long time span + many sub-topics
        time_span = t["latestYear"] - t["earliestYear"]
        sub_count = len(t["subTopics"])
        t["transformationPotential"] = min(100, (time_span * 2) + (sub_count * 15))

        # Overall backcasting score (weighted average)
        t["backcastingScore"] = round(
            t["temporalUrgency"] * 0.30 +
            t["evidenceDensity"] * 0.25 +
            t["crossDomainRelevance"] * 0.25 +
            t["transformationPotential"] * 0.20
        )

    return themes


def generate_domain_summary(data: dict, themes: list[dict]) -> list[dict]:
    """Generate summary data for each of the 18 domains."""
    domains = []
    for dai in data["dai_items"]:
        domain_themes = [t for t in themes if t["domainNo"] == dai["no"]]
        avg_score = (
            round(sum(t["backcastingScore"] for t in domain_themes) / len(domain_themes))
            if domain_themes else 0
        )
        top_theme = max(domain_themes, key=lambda x: x["backcastingScore"]) if domain_themes else None

        domains.append({
            "no": dai["no"],
            "name": dai["name"],
            "mapTheme": dai["mapTheme"],
            "cardCount": dai["cardCount"],
            "themeCount": len(domain_themes),
            "avgBackcastingScore": avg_score,
            "topTheme": top_theme["themeName"] if top_theme else "",
            "topThemeScore": top_theme["backcastingScore"] if top_theme else 0,
        })

    return domains


def main():
    data = load_data()
    themes = extract_research_themes(data)
    themes = compute_backcasting_scores(themes)
    domains = generate_domain_summary(data, themes)

    # Clean summaries for output size (keep first 3 per theme)
    for t in themes:
        t["summaries"] = t["summaries"][:3]

    output = {
        "generatedAt": "2026-04-08",
        "targetYear": 2035,
        "totalThemes": len(themes),
        "totalCards": data["stats"]["cards_count"],
        "domains": domains,
        "themes": sorted(themes, key=lambda x: -x["backcastingScore"]),
        "books": data["books"],
        "scoringWeights": {
            "temporalUrgency": 0.30,
            "evidenceDensity": 0.25,
            "crossDomainRelevance": 0.25,
            "transformationPotential": 0.20,
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Extracted {len(themes)} research themes from {len(domains)} domains")
    print(f"Output written to {OUTPUT_PATH}")

    # Print top 10 themes
    print("\n--- Top 10 Research Themes by Backcasting Score ---")
    for i, t in enumerate(output["themes"][:10], 1):
        print(f"{i}. [{t['backcastingScore']}] {t['themeName']} (Domain: {t['domainName']})")


if __name__ == "__main__":
    main()
