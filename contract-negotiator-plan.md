# Contract Negotiator — Multi-Agent Adversarial Contract Analysis

## What It Does

Paste any contract, agreement, or Terms of Service. Three AI agents analyze it:

1. **Buyer's Lawyer** — advocates for the party receiving the service/product, flags risks, proposes changes
2. **Seller's Lawyer** — advocates for the party providing the service/product, defends clauses, counters buyer's objections
3. **Mediator** — synthesizes both perspectives into a balanced risk assessment

The agents argue with each other over multiple rounds, producing an annotated contract with risks, proposed changes, and a final balanced summary.

**Theme:** Agents for Good (access to legal understanding for people who can't afford lawyers)

---

## Why This Wins

- **Real problem**: Every freelancer, small business, and individual signs contracts they don't understand
- **Architecturally genuine multi-agent**: ParallelAgent, LoopAgent, SequentialAgent — visible to judges
- **Built with ADK**: Google's own framework, deeply integrated with Gemini
- **Visually compelling demo**: Live adversarial debate is engaging to watch
- **Un-promptable**: Multi-round debate with opposing system prompts, state passing between agents, structured output — can't replicate in a single Gemini chat

---

## Architecture

```
User pastes contract text
        ↓
[1] ClauseExtractor (LlmAgent)
    → Parses contract into structured clauses JSON
    → Saves to state["clauses"]
        ↓
[2] ParallelAgent: "DualAnalysis"
    ├── BuyerLawyer (LlmAgent) → state["buyer_analysis"]
    └── SellerLawyer (LlmAgent) → state["seller_analysis"]
        ↓
[3] LoopAgent: "DebateRounds" (3 iterations)
    ├── BuyerRebuttal (LlmAgent)
    │   reads state["seller_analysis"] → state["buyer_rebuttal"]
    ├── SellerRebuttal (LlmAgent)
    │   reads state["buyer_analysis"] → state["seller_rebuttal"]
    └── DebateTracker (Custom Agent)
    │   appends to state["debate_history"], checks if round limit hit → escalate
        ↓
[4] Mediator (LlmAgent)
    → reads all state → produces balanced risk summary
    → state["final_report"]
        ↓
[5] ReportFormatter (LlmAgent)
    → produces the final structured output with risk scores
```

**ADK patterns used:**
- `SequentialAgent` — overall pipeline orchestration
- `ParallelAgent` — buyer/seller analyze simultaneously
- `LoopAgent` — multi-round debate
- `LlmAgent` with `output_key` — state passing between agents
- Custom `BaseAgent` — debate round tracking with escalation
- Structured output via Pydantic models

---

## Project Structure

```
contract_negotiator/
├── agent.py                  # Root agent definition (ADK entry point)
├── agents/
│   ├── clause_extractor.py   # Parses contract into clauses
│   ├── buyer_lawyer.py       # Buyer's advocate agent
│   ├── seller_lawyer.py      # Seller's advocate agent
│   ├── debate_tracker.py     # Custom BaseAgent for debate loop control
│   ├── mediator.py           # Balanced synthesis agent
│   └── report_formatter.py   # Final structured output
├── tools/
│   ├── web_search.py         # Google Search tool for legal references
│   └── clause_tools.py       # Utilities for clause manipulation
├── models/
│   └── schemas.py            # Pydantic models for structured output
├── pyproject.toml
├── .env
└── README.md
```

---

## GCP Setup

```bash
# Enable APIs
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com

# Install ADK
pip install google-adk

# Test the built-in dev UI
adk web contract_negotiator
# Opens at http://localhost:8000 — this IS your demo UI
```

ADK's built-in web UI (`adk web`) is the **fastest possible frontend**. It gives you:
- Chat interface
- Agent execution visualization (shows which agent is active)
- Event/state inspector
- No frontend code needed at all

---

## Phase 1: Data Models (`models/schemas.py`)

```python
# models/schemas.py
from pydantic import BaseModel, Field

class Clause(BaseModel):
    number: int = Field(description="Clause number")
    title: str = Field(description="Short title of the clause")
    text: str = Field(description="Full text of the clause")
    category: str = Field(description="Category: payment, liability, termination, IP, confidentiality, indemnification, warranty, dispute, other")

class ContractClauses(BaseModel):
    contract_type: str = Field(description="Type of contract: SaaS, employment, freelance, NDA, lease, other")
    parties: list[str] = Field(description="Names or roles of the parties involved")
    clauses: list[Clause] = Field(description="Extracted clauses")

class ClauseRisk(BaseModel):
    clause_number: int
    risk_level: str = Field(description="high, medium, low")
    concern: str = Field(description="What's problematic about this clause")
    proposed_change: str = Field(description="Specific suggested rewording or addition")
    legal_reasoning: str = Field(description="Why this matters legally")

class LawyerAnalysis(BaseModel):
    perspective: str = Field(description="buyer or seller")
    overall_risk: str = Field(description="high, medium, low")
    summary: str = Field(description="2-3 sentence overall assessment")
    clause_risks: list[ClauseRisk]
    missing_clauses: list[str] = Field(description="Important clauses that are absent from the contract")

class RebuttalPoint(BaseModel):
    original_concern: str = Field(description="What the other side raised")
    counter_argument: str = Field(description="Why that concern is invalid or overstated")
    concession: str | None = Field(default=None, description="Any point where this side agrees with the other")

class Rebuttal(BaseModel):
    round_number: int
    perspective: str
    points: list[RebuttalPoint]
    new_concerns: list[ClauseRisk] = Field(default_factory=list, description="New issues discovered while reviewing the other side's analysis")

class RiskItem(BaseModel):
    clause_number: int
    clause_title: str
    buyer_risk: str
    seller_risk: str
    buyer_concern: str
    seller_concern: str
    mediator_recommendation: str
    priority: str = Field(description="critical, important, minor")

class FinalReport(BaseModel):
    contract_type: str
    parties: list[str]
    overall_fairness_score: int = Field(description="1-10, where 5 is balanced, <5 favors seller, >5 favors buyer")
    executive_summary: str
    risk_items: list[RiskItem]
    missing_protections_buyer: list[str]
    missing_protections_seller: list[str]
    recommendation: str = Field(description="Final recommendation: sign as-is, negotiate specific clauses, or walk away")
```

---

## Phase 2: Clause Extractor Agent (`agents/clause_extractor.py`)

```python
# agents/clause_extractor.py
from google.adk.agents import LlmAgent

clause_extractor = LlmAgent(
    name="ClauseExtractor",
    model="gemini-2.5-flash",
    instruction="""You are a legal document parser. Your job is to:

1. Identify the type of contract
2. Identify the parties involved (use role names like "Buyer", "Seller", "Client", "Provider" if real names aren't clear)
3. Break the contract into individual clauses, each with a number, title, category, and full text

Categories: payment, liability, termination, IP, confidentiality, indemnification, warranty, dispute, other

Parse the contract provided in the user's message. Be thorough — don't skip any clause, even boilerplate ones.

The contract text is:
{contract_text}""",
    description="Parses contracts into structured clauses",
    output_key="clauses",
)
```

---

## Phase 3: Adversarial Lawyer Agents (`agents/buyer_lawyer.py`, `agents/seller_lawyer.py`)

```python
# agents/buyer_lawyer.py
from google.adk.agents import LlmAgent

buyer_lawyer = LlmAgent(
    name="BuyerLawyer",
    model="gemini-2.5-flash",
    instruction="""You are an aggressive buyer-side attorney with 20 years of contract law experience.
Your client is the BUYER/CLIENT/RECIPIENT in this contract.

Your job: PROTECT YOUR CLIENT. Be adversarial. Find every risk, every unfair term, every missing protection.

Analyze each clause from the buyer's perspective:
- Flag liability limitations that favor the seller
- Find missing warranties or guarantees
- Identify unfair termination clauses
- Look for hidden fees or payment traps
- Check for missing data protection / GDPR clauses
- Flag overly broad IP assignment clauses
- Identify missing SLA commitments
- Look for one-sided indemnification

For each risky clause, provide:
- Risk level (high/medium/low)
- Specific concern
- Proposed rewording that protects the buyer
- Legal reasoning

Also list important clauses that are MISSING from the contract.

The contract clauses are:
{clauses}""",
    description="Buyer-side legal analysis agent",
    output_key="buyer_analysis",
)
```

```python
# agents/seller_lawyer.py
from google.adk.agents import LlmAgent

seller_lawyer = LlmAgent(
    name="SellerLawyer",
    model="gemini-2.5-flash",
    instruction="""You are an aggressive seller-side attorney with 20 years of contract law experience.
Your client is the SELLER/PROVIDER/SERVICE PROVIDER in this contract.

Your job: PROTECT YOUR CLIENT. Be adversarial. Find every risk, every clause that exposes your client, every missing protection.

Analyze each clause from the seller's perspective:
- Flag unlimited liability exposure
- Find missing limitation of liability clauses
- Identify payment terms that are unfavorable (net-90, etc.)
- Look for unreasonable warranty obligations
- Check for missing force majeure clauses
- Flag scope creep risks in service descriptions
- Identify IP clauses that give away too much
- Look for unreasonable termination penalties

For each risky clause, provide:
- Risk level (high/medium/low)
- Specific concern
- Proposed rewording that protects the seller
- Legal reasoning

Also list important clauses that are MISSING from the contract.

The contract clauses are:
{clauses}""",
    description="Seller-side legal analysis agent",
    output_key="seller_analysis",
)
```

---

## Phase 4: Debate Loop (`agents/debate_tracker.py`)

```python
# agents/debate_tracker.py
from google.adk.agents import LlmAgent, BaseAgent, LoopAgent
from google.adk.events import Event, EventActions

MAX_DEBATE_ROUNDS = 3

buyer_rebuttal = LlmAgent(
    name="BuyerRebuttal",
    model="gemini-2.5-flash",
    instruction="""You are the buyer's lawyer in a contract negotiation debate.
The seller's lawyer has made their analysis. Review it and respond:

1. Counter their arguments where they're wrong or self-serving
2. Concede points where they're genuinely fair
3. Raise any NEW concerns you noticed from reading their analysis
4. Stand firm on your most critical issues

Be specific. Reference clause numbers. Don't just repeat yourself — respond to THEIR actual points.

Seller's analysis: {seller_analysis}
Your previous analysis: {buyer_analysis}
Previous debate history: {debate_history}
Current round: {debate_round}""",
    description="Buyer's rebuttal in debate",
    output_key="buyer_rebuttal",
)

seller_rebuttal = LlmAgent(
    name="SellerRebuttal",
    model="gemini-2.5-flash",
    instruction="""You are the seller's lawyer in a contract negotiation debate.
The buyer's lawyer has made their analysis and rebuttal. Review and respond:

1. Counter their arguments where they're wrong or self-serving
2. Concede points where they're genuinely fair
3. Raise any NEW concerns you noticed from reading their analysis
4. Stand firm on your most critical issues

Be specific. Reference clause numbers. Don't just repeat yourself — respond to THEIR actual points.

Buyer's analysis: {buyer_analysis}
Buyer's rebuttal: {buyer_rebuttal}
Your previous analysis: {seller_analysis}
Previous debate history: {debate_history}
Current round: {debate_round}""",
    description="Seller's rebuttal in debate",
    output_key="seller_rebuttal",
)


class DebateTracker(BaseAgent):
    """Custom agent that tracks debate rounds and signals when to stop."""

    name: str = "DebateTracker"
    description: str = "Tracks debate rounds and accumulates debate history"

    async def _run_async_impl(self, ctx):
        # Get current round
        current_round = ctx.session.state.get("debate_round", 0) + 1
        ctx.session.state["debate_round"] = current_round

        # Accumulate debate history
        history = ctx.session.state.get("debate_history", [])
        history.append({
            "round": current_round,
            "buyer_rebuttal": ctx.session.state.get("buyer_rebuttal", ""),
            "seller_rebuttal": ctx.session.state.get("seller_rebuttal", ""),
        })
        ctx.session.state["debate_history"] = history

        # Check if we should stop
        should_stop = current_round >= MAX_DEBATE_ROUNDS

        yield Event(
            author=self.name,
            actions=EventActions(escalate=should_stop),
        )


debate_tracker = DebateTracker()

# The debate loop: buyer rebuts, seller rebuts, tracker checks if done
debate_loop = LoopAgent(
    name="DebateRounds",
    description="Multi-round adversarial debate between buyer and seller lawyers",
    max_iterations=MAX_DEBATE_ROUNDS,
    sub_agents=[buyer_rebuttal, seller_rebuttal, debate_tracker],
)
```

---

## Phase 5: Mediator Agent (`agents/mediator.py`)

```python
# agents/mediator.py
from google.adk.agents import LlmAgent

mediator = LlmAgent(
    name="Mediator",
    model="gemini-2.5-flash",
    instruction="""You are a neutral, senior mediator with expertise in contract law.
Two lawyers have analyzed a contract and debated their positions over multiple rounds.

Your job: Produce a BALANCED, FAIR assessment that helps both parties.

For each disputed clause:
1. Summarize what each side argues
2. Assess who has the stronger legal position
3. Provide a specific recommendation (accept as-is, modify with specific language, or flag as deal-breaker)
4. Assign priority: critical (could cause real harm), important (should negotiate), minor (acceptable risk)

Also provide:
- Overall fairness score (1-10, where 5 is perfectly balanced)
- Executive summary (3-4 sentences)
- Missing protections for each side
- Final recommendation: sign as-is, negotiate (list which clauses), or walk away

Be honest. If the contract is genuinely unfair, say so. If it's reasonable, say that too.

Contract clauses: {clauses}
Buyer's analysis: {buyer_analysis}
Seller's analysis: {seller_analysis}
Debate history: {debate_history}""",
    description="Neutral mediator that synthesizes both perspectives",
    output_key="final_report",
)
```

---

## Phase 6: Root Agent — The Full Pipeline (`agent.py`)

This is the file ADK looks for. It wires everything together.

```python
# agent.py
from google.adk.agents import LlmAgent, SequentialAgent, ParallelAgent
from agents.clause_extractor import clause_extractor
from agents.buyer_lawyer import buyer_lawyer
from agents.seller_lawyer import seller_lawyer
from agents.debate_tracker import debate_loop
from agents.mediator import mediator

# Step 1: Parse the contract
# (clause_extractor saves to state["clauses"])

# Step 2: Both lawyers analyze in parallel
dual_analysis = ParallelAgent(
    name="DualAnalysis",
    description="Buyer and seller lawyers analyze the contract simultaneously",
    sub_agents=[buyer_lawyer, seller_lawyer],
)

# Step 3: Debate loop (already defined in debate_tracker.py)
# (debate_loop runs 3 rounds of rebuttals)

# Step 4: Mediator synthesizes everything
# (mediator reads all state and produces final_report)

# The full pipeline
root_agent = SequentialAgent(
    name="ContractNegotiator",
    description="Multi-agent contract analysis with adversarial debate",
    sub_agents=[
        clause_extractor,
        dual_analysis,
        debate_loop,
        mediator,
    ],
)
```

---

## Phase 7: Configuration

### `pyproject.toml`
```toml
[project]
name = "contract-negotiator"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "google-adk>=1.0.0",
    "google-cloud-aiplatform>=1.70.0",
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
]
```

### `.env`
```
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=TRUE
```

---

## Running It

```bash
# Install
pip install -e .

# Run with ADK's built-in web UI
adk web contract_negotiator

# Opens at http://localhost:8000
# Paste a contract in the chat → watch agents debate
```

ADK's web UI shows:
- Which agent is currently active
- State changes in real-time
- Event log with full agent reasoning
- The final output

This **is** your demo. No frontend needed.

---

## Deployment to Cloud Run

```bash
# ADK has built-in Cloud Run deployment
adk deploy cloud_run \
  --project=your-project-id \
  --region=us-central1 \
  --app_name=contract-negotiator \
  --agent_path=contract_negotiator/

# This gives you a public URL you can share with judges
```

---

## Cost Estimate

| Component | Per contract analysis |
|-----------|---------------------|
| Gemini 2.5 Flash — ClauseExtractor | ~$0.01 |
| Gemini 2.5 Flash — 2x Lawyer analysis | ~$0.02 |
| Gemini 2.5 Flash — 6x Debate rebuttals (3 rounds × 2) | ~$0.06 |
| Gemini 2.5 Flash — Mediator | ~$0.02 |
| **Total** | **~$0.11 per contract** |

With $300 GCP credits → ~2,700 contract analyses. Zero cost concern.

---

## Demo Strategy

### Pre-generate these demo contracts:
1. **Freelance design contract** — classic unfair terms (unlimited revisions, no kill fee, IP assignment)
2. **SaaS Terms of Service** — real-world ToS from a popular service (good test of complexity)
3. **Office lease agreement** — shows it works beyond tech contracts
4. **Employment contract** — resonates with everyone in the room

### Demo script (3 minutes):
1. "Everyone in this room has signed a contract they didn't fully understand." (10 sec)
2. Paste the freelance contract → show agents activate in parallel (30 sec)
3. Point out the debate: "Watch — the buyer's lawyer just found an unlimited liability clause, and the seller's lawyer is defending it" (60 sec)
4. Show the final mediator report with risk scores (30 sec)
5. Show a second contract (SaaS ToS) to prove it generalizes (30 sec)
6. "Built with ADK. 5 specialized agents. ParallelAgent for simultaneous analysis, LoopAgent for multi-round debate. Runs on Gemini 2.5 Flash. Costs 11 cents per analysis." (30 sec)

---

## Implementation Order

| Priority | Task | Who | Hours |
|----------|------|-----|-------|
| 1 | Project scaffold + `pyproject.toml` + `.env` | Person A | 0.5 |
| 2 | `models/schemas.py` — all Pydantic models | Person A | 1 |
| 3 | `agents/clause_extractor.py` — test with real contract | Person B | 1.5 |
| 4 | `agents/buyer_lawyer.py` + `agents/seller_lawyer.py` | Person C+D | 2 |
| 5 | `agents/debate_tracker.py` — LoopAgent with Custom BaseAgent | Person A | 2 |
| 6 | `agents/mediator.py` | Person B | 1 |
| 7 | `agent.py` — wire full pipeline | Person A | 1 |
| 8 | **MILESTONE: First end-to-end run via `adk web`** | All | — |
| 9 | Prompt tuning — make debate feel real and adversarial | Person C+D | 3 |
| 10 | Add structured output (Pydantic models) to agents | Person A+B | 2 |
| 11 | Pre-generate demo contracts + test edge cases | Person C+D | 2 |
| 12 | Deploy to Cloud Run via `adk deploy` | Person A | 1 |
| 13 | README + architecture diagram | Person B | 1.5 |
| 14 | **STOP CODING. Rehearse demo.** | All | 2 |
| | **Total** | | **~18h** |

6 hours of buffer for debugging and unexpected issues.

---

## Bonus Features (if time permits)

### 1. Web Search for Legal References
ADK supports Google Search as a built-in tool. Add it to the lawyer agents so they can cite real legal precedents:
```python
from google.adk.tools import google_search

buyer_lawyer = LlmAgent(
    name="BuyerLawyer",
    model="gemini-2.5-flash",
    instruction="...",
    tools=[google_search],  # Can now search for legal precedents
    output_key="buyer_analysis",
)
```

### 2. Multi-Language Support
Gemini handles translation natively. Add to mediator instruction:
"If the contract is in a language other than English, analyze it in its original language but produce the report in English."

### 3. Custom React Frontend (if someone on the team wants to)
Instead of `adk web`, build a React frontend that:
- Shows the debate as a split-screen chat (buyer left, seller right)
- Highlights risky clauses in the original text
- Has a risk heatmap visualization
- Uses ADK's streaming API for real-time updates

### 4. PDF Upload
Add a tool that extracts text from uploaded PDFs:
```python
def extract_pdf_text(file_path: str) -> str:
    """Extract text from a PDF contract file."""
    import fitz  # PyMuPDF
    doc = fitz.open(file_path)
    return "\n".join(page.get_text() for page in doc)
```

---

## Documentation Checklist for Submission

- [ ] Architecture diagram showing agent hierarchy (use Excalidraw)
- [ ] Demo video/GIF at top of README
- [ ] List every GCP service used: Gemini 2.5 Flash, Vertex AI, Cloud Run, ADK
- [ ] Explain each ADK pattern used: SequentialAgent, ParallelAgent, LoopAgent, Custom BaseAgent
- [ ] "Why multi-agent?" section explaining why this can't be a single prompt
- [ ] "Future Roadmap": jurisdiction-specific analysis, contract comparison, integration with DocuSign
- [ ] Cost analysis showing 11 cents per contract

---

## Key Differentiators for Judges

1. **Uses 4 ADK agent types** (LlmAgent, SequentialAgent, ParallelAgent, LoopAgent) + Custom BaseAgent — shows deep ADK understanding
2. **Adversarial multi-agent debate** — genuinely novel pattern, not just parallel analysis
3. **State passing between agents** via `output_key` — demonstrates ADK's state management
4. **Custom BaseAgent** for debate tracking — shows you understand the framework beyond basic usage
5. **Real problem** — everyone relates to not understanding contracts
6. **Fits "Agents for Good"** — democratizes access to legal understanding
7. **Cheap to run** — 11 cents per analysis, accessible to anyone

---

## Reference

- ADK Python repo: https://github.com/google/adk-python
- ADK multi-agent docs: https://google.github.io/adk-docs/agents/multi-agents/
- ADK multi-agent patterns blog: https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/
- ADK deployment: https://google.github.io/adk-docs/deploy/
