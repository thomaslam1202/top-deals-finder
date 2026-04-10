"""
product_scorer.py  —  Block 2: AI Product Selection
─────────────────────────────────────────────────────
Reads product_data_raw.json from Block 1.
Scores each product across 5 dimensions and selects the top picks.
Outputs scored_products.json → ready for Block 3 (Content Intelligence).

Run:
    python product_scorer.py

No API keys needed — pure Python logic.
"""

import json
import math


# ══════════════════════════════════════════════════════════════════════════════
# 1. SCORING WEIGHTS
#    Adjust these to change what your pipeline prioritises.
#    All weights must add up to 1.0
# ══════════════════════════════════════════════════════════════════════════════

WEIGHTS = {
    "commission_value":  0.25,   # estimated $ earned per sale
    "demand":            0.30,   # review count = market demand signal
    "rating":            0.20,   # product quality
    "bsr_rank":          0.15,   # best seller rank = sales velocity
    "review_sentiment":  0.10,   # ratio of 5★ vs low reviews
}


# ══════════════════════════════════════════════════════════════════════════════
# 2. HARD FILTERS  —  products that fail these are excluded before scoring
# ══════════════════════════════════════════════════════════════════════════════

FILTERS = {
    "min_rating":         4.0,    # below 4★ = hard sell on video
    "min_reviews":        500,    # too few = unproven demand
    "min_price_usd":      15.0,   # too cheap = commission not worth it
    "max_price_usd":      200.0,  # too expensive = low impulse purchase rate
    "min_commission_usd": 0.80,   # minimum $ earned per sale
}


# ══════════════════════════════════════════════════════════════════════════════
# 3. NORMALISATION HELPERS
#    Convert raw values into 0.0–1.0 scores for fair comparison
# ══════════════════════════════════════════════════════════════════════════════

def normalise_commission(value: float, max_val: float = 5.0) -> float:
    """$0 → 0.0, $5+ → 1.0. Cap at max_val to prevent one outlier dominating."""
    return min(value / max_val, 1.0)


def normalise_demand(review_count: int, max_val: int = 30000) -> float:
    """
    Log-scale normalisation — the difference between 100 and 1,000 reviews
    matters more than the difference between 20,000 and 30,000.
    """
    if not review_count or review_count <= 0:
        return 0.0
    return min(math.log10(review_count) / math.log10(max_val), 1.0)


def normalise_rating(rating: float) -> float:
    """3.5★ → 0.0, 5.0★ → 1.0. Products below 3.5 already filtered out."""
    if not rating:
        return 0.0
    return max((rating - 3.5) / 1.5, 0.0)


def normalise_bsr(bsr_rank: int, max_rank: int = 10000) -> float:
    """
    Inverted — rank 1 = best = 1.0, rank 10000+ = 0.0.
    Products not on the BSR list get a neutral 0.3 score.
    """
    if not bsr_rank:
        return 0.3
    return max(1.0 - (bsr_rank / max_rank), 0.0)


def normalise_sentiment(reviews: list) -> float:
    """
    Ratio of 5★ reviews vs 1–2★ reviews.
    Returns 0.0–1.0 where 1.0 = all reviews are 5★.
    """
    if not reviews:
        return 0.5   # neutral if no reviews

    positive = sum(1 for r in reviews if r.get("rating", 0) >= 4)
    negative = sum(1 for r in reviews if r.get("rating", 0) <= 2)
    total = len(reviews)

    sentiment_ratio = (positive - negative) / total
    return max(min((sentiment_ratio + 1) / 2, 1.0), 0.0)   # map -1..1 to 0..1


# ══════════════════════════════════════════════════════════════════════════════
# 4. MAIN SCORING FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def score_product(product: dict) -> dict:
    """
    Score a single product across all 5 dimensions.
    Returns the product dict enriched with score breakdown and final score.
    """
    commission_usd = product.get("commission", {}).get("estimated_usd", 0)
    commission_rate = product.get("commission", {}).get("rate_pct", 0)
    review_count = product.get("review_count", 0)
    rating = product.get("rating", 0)
    bsr_rank = product.get("bsr_rank")
    reviews = product.get("reviews", [])

    # Individual dimension scores (each 0.0–1.0)
    scores = {
        "commission_value":  normalise_commission(commission_usd),
        "demand":            normalise_demand(review_count),
        "rating":            normalise_rating(rating),
        "bsr_rank":          normalise_bsr(bsr_rank),
        "review_sentiment":  normalise_sentiment(reviews),
    }

    # Weighted final score
    final_score = sum(scores[dim] * WEIGHTS[dim] for dim in WEIGHTS)

    return {
        **product,
        "score_breakdown": {k: round(v, 3) for k, v in scores.items()},
        "final_score": round(final_score, 4),
        "estimated_monthly_revenue": estimate_monthly_revenue(
            commission_usd, review_count
        ),
    }


def estimate_monthly_revenue(commission_usd: float, review_count: int) -> float:
    """
    Rough monthly revenue estimate based on commission and demand.
    Formula: estimated conversions per 1000 views × expected views × commission.
    Conservative estimate — adjust conversion_rate as you get real data.
    """
    base_views_per_month = 10000     # conservative starting estimate
    ctr = 0.03                       # 3% click-through from video to landing page
    conversion_rate = 0.05           # 5% of landing page visitors buy

    # Demand multiplier — more reviews = more social proof = better conversion
    demand_multiplier = min(math.log10(max(review_count, 1)) / 4, 1.5)

    sales = base_views_per_month * ctr * conversion_rate * demand_multiplier
    revenue = round(sales * commission_usd, 2)
    return revenue


# ══════════════════════════════════════════════════════════════════════════════
# 5. FILTER + SCORE + RANK PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def apply_filters(products: list) -> tuple[list, list]:
    """
    Apply hard filters. Returns (passed, rejected) lists.
    Logs the rejection reason for transparency.
    """
    passed = []
    rejected = []

    for p in products:
        reasons = []

        if (p.get("rating") or 0) < FILTERS["min_rating"]:
            reasons.append(f"rating {p.get('rating')} < {FILTERS['min_rating']}")

        if (p.get("review_count") or 0) < FILTERS["min_reviews"]:
            reasons.append(f"reviews {p.get('review_count')} < {FILTERS['min_reviews']}")

        if (p.get("price_usd") or 0) < FILTERS["min_price_usd"]:
            reasons.append(f"price ${p.get('price_usd')} < ${FILTERS['min_price_usd']}")

        if (p.get("price_usd") or 0) > FILTERS["max_price_usd"]:
            reasons.append(f"price ${p.get('price_usd')} > ${FILTERS['max_price_usd']}")

        commission_usd = p.get("commission", {}).get("estimated_usd", 0)
        if commission_usd < FILTERS["min_commission_usd"]:
            reasons.append(f"commission ${commission_usd} < ${FILTERS['min_commission_usd']}")

        if reasons:
            rejected.append({**p, "rejected_reasons": reasons})
        else:
            passed.append(p)

    return passed, rejected


def run_scorer(input_path: str = "product_data_raw.json",
               output_path: str = "scored_products.json",
               top_n: int = 3) -> list:
    """
    Full Block 2 pipeline:
      Load → Filter → Score → Rank → Save top N products
    """
    print("=" * 60)
    print("  BLOCK 2: AI PRODUCT SCORING")
    print("=" * 60)

    # Load
    with open(input_path) as f:
        products = json.load(f)
    print(f"\n📦 Loaded {len(products)} products from {input_path}")

    # Filter
    passed, rejected = apply_filters(products)
    print(f"\n🔍 Hard filter results:")
    print(f"   ✅ Passed: {len(passed)}")
    print(f"   ❌ Rejected: {len(rejected)}")

    if rejected:
        print("\n   Rejected products:")
        for p in rejected:
            reasons = ", ".join(p["rejected_reasons"])
            print(f"   • {p['title'][:45]}... → {reasons}")

    # Score
    scored = [score_product(p) for p in passed]

    # Rank
    scored.sort(key=lambda x: x["final_score"], reverse=True)

    # Display results
    print(f"\n{'─'*60}")
    print(f"  RANKED RESULTS")
    print(f"{'─'*60}")

    for i, p in enumerate(scored, 1):
        score = p["final_score"]
        breakdown = p["score_breakdown"]
        est_rev = p["estimated_monthly_revenue"]

        print(f"\n  #{i}  {p['title'][:52]}...")
        print(f"       Score: {score:.4f} / 1.0000")
        print(f"       Price: ${p['price_usd']}  |  "
              f"Rating: {p['rating']}★  |  "
              f"Reviews: {p['review_count']:,}")
        print(f"       Commission: ${p['commission']['estimated_usd']} "
              f"({p['commission']['rate_pct']}%)")
        print(f"       Est. monthly revenue: ${est_rev}")
        print(f"       Breakdown:")
        for dim, val in breakdown.items():
            bar = "█" * int(val * 10) + "░" * (10 - int(val * 10))
            print(f"         {dim:<20} {bar} {val:.3f}")

    # Select top N
    top_products = scored[:top_n]
    print(f"\n{'─'*60}")
    print(f"  ✅ TOP {top_n} SELECTED FOR CONTENT GENERATION")
    print(f"{'─'*60}")
    for p in top_products:
        print(f"  • {p['title'][:55]}...")

    # Save
    with open(output_path, "w") as f:
        json.dump(top_products, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Saved to {output_path}")
    print(f"   Next step: feed scored_products.json into Block 3 "
          f"(Content Intelligence)\n")

    return top_products


# ══════════════════════════════════════════════════════════════════════════════
# 6. RUN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    run_scorer(
        input_path="product_data_raw.json",
        output_path="scored_products.json",
        top_n=3,        # how many products to pass to content generation
    )
