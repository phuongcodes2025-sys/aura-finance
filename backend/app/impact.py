from dataclasses import dataclass

from .models import Area, EconomicEvent, Impact, Profile, Risk

EVENTS = [
    EconomicEvent(
        id=1, title="Inflation up", category="Inflation",
        description="Demo scenario: consumer prices rise faster, putting pressure on purchasing power.",
    ),
    EconomicEvent(
        id=2, title="Interest rate increase", category="Interest rates",
        description="Demo scenario: policy rates rise, potentially increasing new and variable-rate borrowing costs.",
    ),
    EconomicEvent(
        id=3, title="Strong jobs report", category="Employment",
        description="Demo scenario: employment and wage growth strengthen. This is not a live report.",
    ),
    EconomicEvent(
        id=4, title="Housing slowdown", category="Housing",
        description="Demo scenario: housing demand and transaction activity weaken.",
   
    ),
    EconomicEvent(
        id=5, title="Federal Reserve Rate Hike", category="Interest Rates",
        description="Federal Reserve rate hike impacting borrowing costs and consumer debt.",
    ),
]
]


@dataclass(frozen=True)
class Rule:
    id: str
    events: tuple[int, ...]
    area: Area
    risk: Risk
    summary: str
    explanation: str
    considerations: tuple[str, ...]


# Exactly one rule matches each active area for every supported event.
RULES = (
    Rule("income-inflation", (1,), "income", "high",
         "Purchasing power may fall",
         "If prices rise faster than your pay, the same income buys less. The profile does not include wage growth or expenses.",
         ("Compare essential expenses with income growth.", "Review your budget using actual costs.")),
    Rule("income-demand", (2, 4), "income", "moderate",
         "Slower demand may affect earnings",
         "Higher financing costs or weaker housing activity can slow hiring in exposed industries. Your occupation alone cannot predict job security.",
         ("Review your emergency savings needs.", "Watch hiring trends in your own industry.")),
    Rule("income-jobs", (3,), "income", "low",
         "Stronger hiring may create opportunities",
         "A strong labor market can support wages and job options, but national trends may not match your industry or location.",
         ("Compare local job openings and compensation.", "Consider building skills relevant to your career.")),
    Rule("business-costs", (1, 2), "business", "high",
         "Costs and cash flow deserve attention",
         "Inflation can raise operating costs; rate increases can raise variable-rate or new loan costs. Effects depend on contracts, debt, and customer demand.",
         ("Review cash flow and essential operating costs.", "Check whether business loans are fixed or variable rate.")),
    Rule("business-jobs", (3,), "business", "moderate",
         "Demand and staffing costs may both rise",
         "More employment can support customer spending while a tighter labor market can increase hiring costs.",
         ("Compare sales trends with staffing costs.", "Plan hiring around actual demand.")),
    Rule("business-housing", (4,), "business", "moderate",
         "Housing-linked demand may weaken",
         "Businesses connected to construction, moving, or home purchases may see softer demand. Other businesses may be less exposed.",
         ("Identify customers tied to housing activity.", "Review cash flow under a slower-sales scenario.")),
    Rule("investments-rates", (1, 2), "investments", "moderate",
         "Rate-sensitive investments may face pressure",
         "Inflation and higher discount rates can pressure valuations. Outcomes depend on expectations, diversification, and individual holdings; no tickers were collected.",
         ("Review diversification and time horizon.", "Understand exposure before making any investment decision.")),
    Rule("investments-growth", (3, 4), "investments", "moderate",
         "Sector effects can differ",
         "Strong jobs can support earnings but also change rate expectations. A housing slowdown can weigh on housing-linked firms. Neither scenario predicts market direction.",
         ("Compare sector exposure with your risk tolerance.", "Avoid treating a single economic signal as a trading instruction.")),
    Rule("property-financing", (1, 2), "realEstate", "moderate",
         "New financing may become more expensive",
         "Higher rates can affect new or variable-rate mortgages. Existing fixed-rate payments do not automatically increase; inflation may also raise maintenance costs.",
         ("Check mortgage terms and renewal dates.", "Review maintenance costs and cash reserves.")),
    Rule("property-demand", (3, 4), "realEstate", "moderate",
         "Local housing conditions matter",
         "Strong employment may support housing demand; a slowdown may reduce transactions or pricing power. Location, vacancies, and property type determine actual exposure.",
         ("Compare local rents, vacancies, and sale activity.", "Stress-test cash flow without assuming price appreciation.")),
    Rule("income-demand", (2, 4, 5), "income", "moderate",
         "Slower demand may affect earnings",
         "Higher financing costs or weaker housing activity can slow hiring in exposed industries. Your occupation alone cannot predict job security.",
         ("Review your emergency savings needs.", "Watch hiring trends in your own industry.")),
    // ...existing code...
    Rule("business-costs", (1, 2, 5), "business", "high",
         "Costs and cash flow deserve attention",
         "Inflation can raise operating costs; rate increases can raise variable-rate or new loan costs. Effects depend on contracts, debt, and customer demand.",
         ("Review cash flow and essential operating costs.", "Check whether business loans are fixed or variable rate.")),
    // ...existing code...
    Rule("investments-rates", (1, 2, 5), "investments", "moderate",
         "Rate-sensitive investments may face pressure",
         "Inflation and higher discount rates can pressure valuations. Outcomes depend on expectations, diversification, and individual holdings; no tickers were collected.",
         ("Review diversification and time horizon.", "Understand exposure before making any investment decision.")),
    // ...existing code...
    Rule("property-financing", (1, 2, 5), "realEstate", "high",
         "New financing may become more expensive",
         "Higher rates can affect new or variable-rate mortgages. Existing fixed-rate payments do not automatically increase; inflation may also raise maintenance costs.",
         ("Check mortgage terms and renewal dates.", "Review maintenance costs and cash reserves.")),

)

ASSUMPTIONS = [
    "These four events are hypothetical demo scenarios, not live economic news.",
    "Risk labels are qualitative rule-based attention indicators, not probabilities, loss estimates, or personalized forecasts.",
    "Income range and occupation provide context only; no dollar impacts, wage changes, or investment returns are calculated.",
    "Debt terms, expenses, specific holdings, and location are unknown. Suggested considerations are educational, not financial advice.",
]


def analyze(profile: Profile, event: EconomicEvent) -> list[Impact]:
    active = {
        "income": True,
        "business": profile.business_owner,
        "investments": profile.investor,
        "realEstate": profile.property_owner,
    }
    impacts = []
    for area, applicable in active.items():
        if not applicable:
            impacts.append(Impact(
                area=area, risk="notApplicable",
                summary="No exposure selected",
                explanation="Your demo profile does not include this financial exposure.",
                considerations=[], ruleId=None,
            ))
            continue
        matches = [rule for rule in RULES if rule.area == area and event.id in rule.events]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one rule for event {event.id}, area {area}")
        rule = matches[0]
        impacts.append(Impact(
            area=rule.area, risk=rule.risk, summary=rule.summary,
            explanation=rule.explanation, considerations=list(rule.considerations),
            ruleId=rule.id,
        ))
    return impacts
