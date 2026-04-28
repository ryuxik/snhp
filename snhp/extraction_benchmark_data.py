"""
SNHP Extraction Benchmark — 200 Synthetic Negotiation Emails
==============================================================
Stratified: 40 per category (web_dev, design, consulting, writing, mixed)

Each email has ground truth labels for:
  - rate (hourly or flat), duration, hours, total_min, total_ideal,
    revisions, urgency, payment_terms, category

Usage:
    from extraction_benchmark_data import BENCHMARK_EMAILS
    for entry in BENCHMARK_EMAILS:
        email = entry['client_email']
        constraints = entry['freelancer_constraints']
        truth = entry['ground_truth']
"""

import random
import json

random.seed(42)

# ──────────────────────────────────────────────
# Template generators per category
# ──────────────────────────────────────────────

def _jitter(base, pct=0.15):
    """Add ±pct random jitter to a base number."""
    return round(base * random.uniform(1 - pct, 1 + pct), 2)

def _pick(*options):
    return random.choice(options)


# ───── WEB DEVELOPMENT ─────

WEB_DEV_TEMPLATES = [
    {
        "client_tpl": "Hi, I need a {scope} built. My budget is around ${budget}. Timeline is {days} days. Looking for someone who can start this week.",
        "freelancer_tpl": "I charge ${rate}/hr, can work up to {hrs_day}hrs/day for {weeks} weeks. My minimum total is ${min_total}.",
        "scope_options": ["React dashboard", "Next.js e-commerce site", "landing page with CMS", "admin panel", "API backend in Node.js", "portfolio website", "SaaS MVP", "mobile-responsive web app"],
        "params": lambda: {
            "rate": _pick(75, 85, 95, 100, 110, 125, 150),
            "budget": _pick(2000, 3000, 4000, 5000, 6000, 8000, 10000, 12000),
            "days": _pick(7, 10, 14, 21, 28, 30, 45),
            "hrs_day": _pick(3, 4, 5, 6, 8),
            "weeks": _pick(1, 2, 3, 4),
            "revisions": _pick(1, 2, 3),
            "urgency": round(random.uniform(0.3, 0.9), 2),
        }
    },
    {
        "client_tpl": "We're looking for a developer for a {scope}. We can pay ${rate_offer}/hr. Expecting about {hours} hours of work. {urgency_note}",
        "freelancer_tpl": "My rate is ${rate}/hr, absolute minimum ${batna_rate}/hr. I want no more than {revisions} revision rounds.",
        "scope_options": ["WordPress plugin", "Shopify theme customization", "Vue.js frontend", "REST API refactor", "database migration", "CI/CD pipeline setup"],
        "urgency_notes": ["Need it ASAP.", "No rush, whenever you can get to it.", "Ideally done by end of month.", "This is blocking our launch."],
        "params": lambda: {
            "rate": _pick(80, 90, 100, 120, 140),
            "batna_rate": _pick(60, 65, 70, 75, 80),
            "rate_offer": _pick(50, 60, 70, 80, 90, 100),
            "hours": _pick(20, 30, 40, 50, 60, 80),
            "revisions": _pick(1, 2, 3),
            "urgency": round(random.uniform(0.2, 1.0), 2),
        }
    },
]

# ───── DESIGN ─────

DESIGN_TEMPLATES = [
    {
        "client_tpl": "I need {scope} designed. Total budget is ${budget}. I'd like {revisions} rounds of revisions. Timeline: {days} days.",
        "freelancer_tpl": "I charge ${rate}/hr for design work. I can commit {hrs_day} hours per day. Minimum project fee ${min_total}.",
        "scope_options": ["a brand identity package", "UI/UX for a mobile app", "a logo and business cards", "social media templates", "a pitch deck", "product packaging", "an icon set"],
        "params": lambda: {
            "rate": _pick(60, 75, 85, 95, 100, 120),
            "budget": _pick(1500, 2000, 2500, 3000, 4000, 5000, 7500),
            "days": _pick(5, 7, 10, 14, 21),
            "hrs_day": _pick(3, 4, 5, 6),
            "revisions": _pick(2, 3, 4, 5),
            "urgency": round(random.uniform(0.2, 0.8), 2),
        }
    },
    {
        "client_tpl": "Looking for a designer for {scope}. Our rate is ${rate_offer}/hr for approximately {hours} hours. We need {revisions} revision rounds included.",
        "freelancer_tpl": "My desired rate is ${rate}/hr. Minimum I'll accept is ${batna_rate}/hr. I prefer projects under {max_days} days.",
        "scope_options": ["website redesign", "app UI screens", "marketing collateral", "presentation design", "infographic series"],
        "params": lambda: {
            "rate": _pick(70, 80, 90, 100, 110, 125),
            "batna_rate": _pick(50, 55, 60, 65, 70),
            "rate_offer": _pick(40, 50, 60, 70, 80),
            "hours": _pick(15, 20, 25, 30, 40),
            "revisions": _pick(2, 3, 4),
            "max_days": _pick(10, 14, 21, 30),
            "urgency": round(random.uniform(0.3, 0.9), 2),
        }
    },
]

# ───── CONSULTING ─────

CONSULTING_TEMPLATES = [
    {
        "client_tpl": "We need a {scope} consultant for {weeks} weeks. Budget is ${budget} total. {urgency_note}",
        "freelancer_tpl": "My consulting rate is ${rate}/hr. I can do {hrs_day} hours per day, {days_week} days per week. Walk-away total is ${min_total}.",
        "scope_options": ["data strategy", "product management", "growth marketing", "DevOps", "security audit", "AI/ML", "business process optimization"],
        "urgency_notes": ["We're in crisis mode.", "Planning for next quarter.", "Ongoing engagement possible.", "Fixed scope, one-time."],
        "params": lambda: {
            "rate": _pick(125, 150, 175, 200, 225, 250, 300),
            "budget": _pick(5000, 7500, 10000, 12000, 15000, 20000),
            "weeks": _pick(1, 2, 3, 4, 6, 8),
            "hrs_day": _pick(2, 3, 4, 5, 6),
            "days_week": _pick(3, 4, 5),
            "urgency": round(random.uniform(0.3, 1.0), 2),
        }
    },
    {
        "client_tpl": "Hi, I'm looking for someone to help with {scope}. I can offer ${rate_offer}/hr for about {hours} hours. Payment within {pay_days} days.",
        "freelancer_tpl": "I want ${rate}/hr minimum, ideally ${ideal_rate}/hr. Maximum engagement {max_weeks} weeks. No more than {revisions} deliverable rounds.",
        "scope_options": ["go-to-market strategy", "technical architecture review", "team coaching", "process audit", "vendor evaluation"],
        "params": lambda: {
            "rate": _pick(100, 125, 150, 175, 200),
            "ideal_rate": _pick(150, 175, 200, 225, 250),
            "rate_offer": _pick(80, 100, 120, 140, 160),
            "hours": _pick(10, 20, 30, 40, 60),
            "max_weeks": _pick(2, 3, 4, 6),
            "revisions": _pick(1, 2, 3),
            "pay_days": _pick(15, 30, 45, 60),
            "urgency": round(random.uniform(0.2, 0.9), 2),
        }
    },
]

# ───── WRITING ─────

WRITING_TEMPLATES = [
    {
        "client_tpl": "I need {scope} written. Budget: ${budget}. Deadline: {days} days. {revisions} rounds of edits included.",
        "freelancer_tpl": "I charge ${rate}/hr for writing. I expect about {hours} hours total. My floor is ${min_total} for the project.",
        "scope_options": ["a whitepaper (3000 words)", "10 blog posts", "website copy for 5 pages", "an e-book (10k words)", "product descriptions for 50 items", "a case study series", "technical documentation"],
        "params": lambda: {
            "rate": _pick(40, 50, 60, 75, 85, 100),
            "budget": _pick(800, 1000, 1500, 2000, 2500, 3000, 5000),
            "days": _pick(5, 7, 10, 14, 21, 30),
            "hours": _pick(10, 15, 20, 25, 30, 40),
            "revisions": _pick(1, 2, 3),
            "urgency": round(random.uniform(0.2, 0.8), 2),
        }
    },
    {
        "client_tpl": "Looking for a writer for {scope}. We pay ${rate_offer} per {unit}. Need it in {days} days. {urgency_note}",
        "freelancer_tpl": "I want ${rate} per {unit}, minimum ${batna_rate} per {unit}. I can handle up to {max_items} {unit}s per week.",
        "scope_options": ["blog content", "email sequences", "landing page copy", "social media posts", "press releases"],
        "units": ["article", "piece", "post", "page"],
        "urgency_notes": ["Urgent!", "Flexible timeline.", "Part of a bigger campaign.", "Ongoing work if this goes well."],
        "params": lambda: {
            "rate": _pick(100, 150, 200, 250, 300, 400, 500),
            "batna_rate": _pick(75, 100, 125, 150, 200),
            "rate_offer": _pick(50, 75, 100, 125, 150),
            "days": _pick(3, 5, 7, 10, 14),
            "max_items": _pick(3, 5, 7, 10),
            "urgency": round(random.uniform(0.3, 1.0), 2),
        }
    },
]

# ───── MIXED / UNUSUAL ─────

MIXED_TEMPLATES = [
    {
        "client_tpl": "Hey, I have a {scope} project. It's a bit unusual. I'm thinking ${budget} for the whole thing, done in {days} days. Let me know if that works.",
        "freelancer_tpl": "I'd want at least ${min_total} for something like this. Ideally ${ideal_total}. No more than {revisions} revisions.",
        "scope_options": ["video editing + thumbnail design", "data scraping + visualization dashboard", "chatbot development + knowledge base", "AR prototype + demo video", "music production + mixing", "3D modeling + rendering", "podcast editing + show notes"],
        "params": lambda: {
            "ideal_total": _pick(2000, 3000, 4000, 5000, 6000, 8000),
            "budget": _pick(1500, 2000, 2500, 3000, 4000, 5000),
            "days": _pick(7, 10, 14, 21, 30),
            "revisions": _pick(1, 2, 3, 4),
            "urgency": round(random.uniform(0.2, 0.9), 2),
        }
    },
    {
        "client_tpl": "I need help with {scope}. This is a flat-fee project, I'm offering ${budget}. {urgency_note} Payment on completion.",
        "freelancer_tpl": "For this type of work I typically charge ${ideal_total}. My absolute minimum is ${min_total}. Timeline should be {max_days} days max.",
        "scope_options": ["translation (5000 words EN→ES)", "voiceover recording (30 min)", "photo retouching (50 images)", "spreadsheet automation", "survey design + analysis", "event planning consultation", "patent illustration"],
        "urgency_notes": ["Need it yesterday.", "Next month is fine.", "Flexible but sooner is better.", "Part of an ongoing relationship."],
        "params": lambda: {
            "ideal_total": _pick(1500, 2000, 3000, 4000, 5000),
            "min_total": _pick(800, 1000, 1200, 1500, 2000),
            "budget": _pick(500, 750, 1000, 1500, 2000, 2500),
            "max_days": _pick(5, 7, 10, 14, 21),
            "urgency": round(random.uniform(0.2, 1.0), 2),
        }
    },
]


def _generate_from_template(template, category, idx):
    """Generate a single email + constraints + ground truth from a template."""
    p = template["params"]()
    
    scope = random.choice(template.get("scope_options", ["project"]))
    urgency_note = random.choice(template.get("urgency_notes", [""]))
    unit = random.choice(template.get("units", ["item"]))
    
    # Build client email
    client_email = template["client_tpl"].format(
        scope=scope, 
        budget=p.get("budget", "TBD"),
        days=p.get("days", 14),
        weeks=p.get("weeks", 2),
        hours=p.get("hours", 20),
        revisions=p.get("revisions", 2),
        rate_offer=p.get("rate_offer", "negotiable"),
        urgency_note=urgency_note,
        unit=unit,
        pay_days=p.get("pay_days", 30),
    )
    
    # Build freelancer constraints
    freelancer_constraints = template["freelancer_tpl"].format(
        rate=p.get("rate", p.get("ideal_rate", 100)),
        batna_rate=p.get("batna_rate", int(p.get("rate", 100) * 0.75)),
        hrs_day=p.get("hrs_day", 4),
        hours=p.get("hours", 20),
        weeks=p.get("weeks", 2),
        days_week=p.get("days_week", 5),
        min_total=p.get("min_total", int(p.get("rate", 100) * p.get("hours", 20) * 0.75)),
        ideal_total=p.get("ideal_total", int(p.get("rate", 100) * p.get("hours", 20))),
        revisions=p.get("revisions", 2),
        max_days=p.get("max_days", 14),
        max_weeks=p.get("max_weeks", 4),
        max_items=p.get("max_items", 5),
        unit=unit,
        ideal_rate=p.get("ideal_rate", p.get("rate", 100)),
    )
    
    # Compute ground truth
    rate = p.get("rate", p.get("ideal_rate"))
    batna_rate = p.get("batna_rate")
    hours = p.get("hours")
    hrs_day = p.get("hrs_day")
    weeks = p.get("weeks")
    days = p.get("days")
    
    # Total hours derivation
    total_hours = None
    if hours:
        total_hours = hours
    elif hrs_day and weeks:
        total_hours = hrs_day * weeks * 5  # 5 working days/week
    elif hrs_day and days:
        total_hours = hrs_day * days
    
    # Ideal total
    ideal_total = p.get("ideal_total")
    if ideal_total is None and rate and total_hours:
        ideal_total = rate * total_hours
    elif ideal_total is None and p.get("budget"):
        ideal_total = p.get("budget")  # flat fee
    
    # Compute the min_total that was ACTUALLY rendered in the text
    # (this matches what the LLM will read)
    rendered_min_total = p.get("min_total")
    if rendered_min_total is None:
        rendered_min_total = int(p.get("rate", 100) * p.get("hours", 20) * 0.75)
    
    # Min total: use what was rendered in the text (what the LLM sees)
    min_total = rendered_min_total

    # Duration in days
    duration_days = days
    if duration_days is None and weeks:
        duration_days = weeks * 7
    
    ground_truth = {
        "free_hourly_rate": rate,
        "free_hourly_batna": batna_rate,
        "free_total_hours": total_hours,
        "free_ideal_total": ideal_total,
        "free_min_total": min_total,
        "free_duration_days": duration_days,
        "free_max_hours_per_day": hrs_day,
        "free_revisions": p.get("revisions"),
        "client_budget": p.get("budget"),
        "client_rate_offer": p.get("rate_offer"),
        "client_timeline_days": days,
        "client_urgency": p.get("urgency"),
        "category": category,
    }
    
    return {
        "id": f"{category}_{idx:03d}",
        "category": category,
        "client_email": client_email,
        "freelancer_constraints": freelancer_constraints,
        "ground_truth": ground_truth,
    }


def generate_benchmark_dataset(n_per_category=40):
    """Generate the full 200-email benchmark dataset."""
    categories = {
        "web_dev": WEB_DEV_TEMPLATES,
        "design": DESIGN_TEMPLATES,
        "consulting": CONSULTING_TEMPLATES,
        "writing": WRITING_TEMPLATES,
        "mixed": MIXED_TEMPLATES,
    }
    
    dataset = []
    for cat_name, templates in categories.items():
        for i in range(n_per_category):
            tpl = templates[i % len(templates)]
            entry = _generate_from_template(tpl, cat_name, i)
            dataset.append(entry)
    
    return dataset


# Pre-generate the dataset
BENCHMARK_EMAILS = generate_benchmark_dataset(40)


if __name__ == "__main__":
    print(f"Generated {len(BENCHMARK_EMAILS)} benchmark emails")
    print(f"Categories: {set(e['category'] for e in BENCHMARK_EMAILS)}")
    
    # Show a few examples
    for i in [0, 40, 80, 120, 160]:
        e = BENCHMARK_EMAILS[i]
        print(f"\n{'='*60}")
        print(f"[{e['id']}] Category: {e['category']}")
        print(f"Client: {e['client_email']}")
        print(f"Freelancer: {e['freelancer_constraints']}")
        print(f"Truth: {json.dumps(e['ground_truth'], indent=2)}")
