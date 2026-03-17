from google.adk.agents import LlmAgent
from contract_negotiator.models.schemas import ContractClauses

clause_extractor = LlmAgent(
    name="ClauseExtractor",
    model="gemini-2.5-flash",
    output_schema=ContractClauses,
    output_key="clauses",
    description="Parses contracts into structured clauses",
    instruction="""You are a legal document parser. Extract the contract into structured JSON.

RULES:
- Number clauses sequentially starting at 1. Never skip a clause, including recitals and boilerplate.
- Use role names (Buyer, Seller, Client, Provider) if proper names are absent.
- Category must be exactly one of: payment, liability, termination, IP, confidentiality,
  indemnification, warranty, dispute, other
- contract_type must be exactly one of: SaaS, employment, freelance, NDA, lease, other

FEW-SHOT EXAMPLE (short contract fragment):
Input: "3. Payment. Client shall pay Provider $5,000 within 30 days of invoice."
Output clause: {"number": 3, "title": "Payment Terms", "category": "payment",
  "text": "Client shall pay Provider $5,000 within 30 days of invoice."}

Parse the contract in the user message. Be thorough — don't skip any clause.""",
)
