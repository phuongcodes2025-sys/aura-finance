# Aura Finance

**Finance Impact Copilot | HackUTD**

Aura Finance is a proposed AI-powered financial decision support platform that
translates economic events into personalized insights for income, businesses,
investment portfolios, and real estate.

> Economic news tells you what happened. Aura Finance helps you understand what
> it could mean for your money.

**Theme:** Artificial Intelligence + Financial Literacy + Economic Intelligence
+ Personalized Decision Support.

**Status:** Planning and documentation. The features and architecture below are
proposed; no working application has been implemented in this repository yet.

## The problem

Inflation announcements, Federal Reserve decisions, employment reports, GDP
trends, and housing developments are widely reported, but the information is
often technical, scattered, and difficult to connect to personal circumstances.

An employee, small business owner, investor, or home buyer may hear the same news
but face very different questions about wages, borrowing costs, customer demand,
investments, and property financing.

## Our solution

Aura Finance combines a simplified financial profile, economic event analysis,
rule-based impact models, and AI explanations to make economic intelligence
more accessible.

Instead of asking only "What is inflation?", a user can ask:

> How might rising inflation affect my income, my nail salon business, my stock
> portfolio, and my rental home?

The proposed dashboard presents potential impacts, risk indicators, sector
context, and suggested considerations in plain language, with assumptions and
uncertainty made explicit.

## Target users

| Audience | Primary need |
|---|---|
| College students | Understand economic news and build financial literacy |
| Retail investors | Connect macroeconomic conditions to portfolio exposure |
| Small business owners | Understand potential changes in costs and customer demand |
| First-time home buyers and property owners | Understand housing and financing conditions |
| Bloomberg Trading Challenge teams | Explore macroeconomic scenarios and sector impacts |

## Weekend MVP

| Feature | Planned capability |
|---|---|
| Economic Event Analyzer | Explain a selected or manually entered economic event |
| Personal Financial Profile | Capture income, occupation, business, stocks, and real estate exposure |
| Personalized Impact Engine | Assess potential impacts across income, business, investments, and property |
| Impact Dashboard | Display explanations, risk indicators, and suggested considerations |
| AI Q&A | Answer follow-up questions using the selected event and profile |
| Economic Knowledge Base | Explain inflation, interest rates, jobs reports, GDP, housing, and recession |

The MVP will prioritize an end-to-end demo using synthetic profiles and curated
economic scenarios. Live market feeds, production financial integrations, and
commercial deployment are outside the weekend scope.

### Example scenario

**Event:** Interest rates increase.

**Demo profile:** A small business owner with rental property exposure.

| Area | Possible impact |
|---|---|
| Income | Wage growth and employment conditions may change as demand slows |
| Business | Variable-rate borrowing costs may rise; discretionary spending may weaken |
| Investments | Rate-sensitive holdings may face valuation pressure |
| Real estate | New financing may become more expensive; existing fixed-rate loans may be unaffected |

These are illustrative relationships, not predictions. Actual outcomes depend
on market expectations, loan terms, timing, and the user's circumstances.

## Planned technology stack

| Component | Technology |
|---|---|
| Frontend | React |
| Backend | Python + FastAPI |
| Database | SQLite |
| AI integration | OpenAI-compatible AI services |
| Impact logic | Rule-based models supported by educational knowledge content |

## MVP user flow

```text
Landing page
    |
Select economic event
    |
Create demo financial profile
    |
Run personalized analysis
    |
View impact dashboard
    |
Ask follow-up questions
    |
Review explanations and suggested considerations
```

## Proposed architecture

```text
React interface
    |
FastAPI API
    |
Profile engine + Economic event engine
    |
Rule-based impact models + Educational knowledge
    |
AI analysis layer
    |
Recommendation engine
    |
Impact dashboard + Contextual Q&A
```

Rule-based models provide explicit economic assumptions. The AI layer explains
those assumptions in the context of the user's profile rather than presenting
generated claims as guaranteed financial outcomes.

### Proposed folder structure

This layout is a development plan; these directories do not exist yet.

```text
aura-finance/
├── README.md
└── src/
    ├── app/                  # React application
    ├── api/                  # FastAPI routes: analyze, profile, events, chat
    ├── components/           # Dashboard, ChatBox, ImpactCard, ProfileForm
    ├── knowledge/            # Inflation, jobs, rates, GDP, housing, recession
    ├── data/                 # Business, stock, housing, and income rules
    ├── lib/                  # Profile, impact, AI, and recommendation engines
    └── tests/
```

## Stretch goals

- Market sector analysis and an educational watchlist builder.
- Bloomberg Trading Challenge mode for macroeconomic scenario exploration.
- Portfolio upload and personalized exposure analysis using demo data.
- Alternative data integration, such as spending or hiring trends.
- Retrieval-augmented generation (RAG) over economic reports and Fed statements.

Stretch goals are secondary to delivering a reliable, understandable MVP.

## Business value and success criteria

The project aims to reduce the gap between access to economic news and the
ability to interpret its personal implications. The hackathon prototype will
demonstrate educational value, usable AI integration, and a clear business case
for future development.

MVP success means a user can select an event, enter a demo profile, and receive
coherent explanations across the four financial areas, then ask a contextual
follow-up question. The demo should distinguish general economic relationships
from uncertain predictions and make its assumptions visible.

ROI at this stage focuses on learning, hackathon competitiveness, and potential
future commercialization, not immediate revenue or investment returns.

## Planned hackathon deliverables

- Source code and working prototype.
- README with setup instructions once implementation is available.
- Architecture diagram.
- Presentation slide deck of 8-10 slides.
- Business impact explanation.
- Optional demo video.

## Responsible use

Aura Finance is an educational prototype, not a licensed financial advisor.
AI-generated outputs may be incomplete or inaccurate and must not be treated as
personalized investment advice, trading instructions, or guaranteed outcomes.

Use synthetic financial profiles for the hackathon. Do not commit personal
financial records, API keys, or other secrets. AI credentials should remain on
the backend and be configured through environment variables when implemented.

## Getting started

The repository currently contains documentation only. Installation commands,
environment configuration, and instructions for running the frontend, backend,
and tests will be added with the working implementation.

## Project planning

[Aura Finance GitHub Project](https://github.com/users/phuongcodes2025-sys/projects/3/views/2).
