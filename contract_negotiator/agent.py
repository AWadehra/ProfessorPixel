from google.adk.agents import SequentialAgent, ParallelAgent
from .agents.clause_extractor import clause_extractor
from .agents.buyer_lawyer import buyer_lawyer
from .agents.seller_lawyer import seller_lawyer
from .agents.debate_tracker import debate_loop
from .agents.mediator import mediator
from .agents.redliner import redliner

# Step 2: Both lawyers analyze in parallel
dual_analysis = ParallelAgent(
    name="DualAnalysis",
    description="Buyer and seller lawyers analyze the contract simultaneously",
    sub_agents=[buyer_lawyer, seller_lawyer],
)

# The full pipeline
root_agent = SequentialAgent(
    name="ContractNegotiator",
    description="Multi-agent contract analysis with adversarial debate and redlining",
    sub_agents=[
        clause_extractor,
        dual_analysis,
        debate_loop,
        mediator,
        redliner,
    ],
)
