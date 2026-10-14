from dataclasses import dataclass


@dataclass
class RouteDecision:
    workstream: str
    agent: str
    risk_level: str
    approval_required: bool
    reason: str


WORKSTREAMS = {
    "endorsement": {
        "name": "UK Innovator Founder Endorsement",
        "agent": "edsync_strategy_agent",
        "keywords": [
            "innovator", "endorsement", "business plan", "uk visa",
            "market size", "innovation", "scalability", "viability"
        ],
    },
    "edsync_product": {
        "name": "EdSync Product and University Pilots",
        "agent": "edsync_product_agent",
        "keywords": [
            "edsync", "product", "university", "pilot", "portal",
            "mvp", "eligibility", "student", "admissions"
        ],
    },
    "career_rnd": {
        "name": "Career Algorithm R&D",
        "agent": "career_rnd_agent",
        "keywords": [
            "career", "algorithm", "recommendation", "skills", "esco",
            "onet", "o*net", "occupation", "employability", "pathway"
        ],
    },
    "marketing": {
        "name": "EdSync Sales and Marketing",
        "agent": "marketing_agent",
        "keywords": [
            "marketing", "sales", "campaign", "google ads", "social media",
            "content calendar", "linkedin", "seo", "landing page"
        ],
    },
    "applications": {
        "name": "US Graduate Applications",
        "agent": "applications_agent",
        "keywords": [
            "graduate", "application", "university application", "sop",
            "recommendation", "scholarship", "masters", "upenn"
        ],
    },
    "investors_grants": {
        "name": "Investors, Grants and Partnerships",
        "agent": "fundraising_agent",
        "keywords": [
            "investor", "grant", "accelerator", "pitch", "fundraising",
            "partnership", "startup", "deck"
        ],
    },
    "legal_ops": {
        "name": "Legal and Operations",
        "agent": "legal_ops_agent",
        "keywords": [
            "legal", "case", "court", "evidence", "fir", "application",
            "operations", "compliance", "document review"
        ],
    },
    "writing": {
        "name": "Mahnoor Writing DNA",
        "agent": "writer_agent",
        "keywords": [
            "write", "rewrite", "content", "article", "caption", "email",
            "storytelling", "voice", "tone", "copy"
        ],
    },
}


def route_task(title: str, details: str = "") -> RouteDecision:
    text = f"{title} {details}".lower()

    scores = {}
    for key, config in WORKSTREAMS.items():
        score = 0
        for keyword in config["keywords"]:
            if keyword in text:
                score += 1
        scores[key] = score

    best_key = max(scores, key=scores.get)

    if scores[best_key] == 0:
        best_key = "edsync_product"

    config = WORKSTREAMS[best_key]

    approval_required = any(
        phrase in text
        for phrase in [
            "send email",
            "publish",
            "submit",
            "spend",
            "pay",
            "sign",
            "file application",
            "contact investor",
        ]
    )

    risk_level = "medium" if approval_required else "low"

    return RouteDecision(
        workstream=best_key,
        agent=config["agent"],
        risk_level=risk_level,
        approval_required=approval_required,
        reason=f"Matched task to {config['name']} using keyword and intent routing.",
    )
