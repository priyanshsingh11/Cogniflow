from app.workflows.steps.agent import execute_agent_step
from app.workflows.steps.approval import execute_approval_step
from app.workflows.steps.base import StepExecutionContext, StepResult
from app.workflows.steps.condition import execute_condition_step
from app.workflows.steps.coordinator import execute_coordinator_step
from app.workflows.steps.knowledge import execute_knowledge_step
from app.workflows.steps.llm import execute_llm_step
from app.workflows.steps.mcp import execute_mcp_step

STEP_HANDLERS = {
    "llm": execute_llm_step,
    "knowledge_search": execute_knowledge_step,
    "mcp_tool": execute_mcp_step,
    "condition": execute_condition_step,
    "agent": execute_agent_step,
    "coordinator": execute_coordinator_step,
    "approval": execute_approval_step,
}

__all__ = [
    "StepExecutionContext",
    "StepResult",
    "STEP_HANDLERS",
    "execute_llm_step",
    "execute_knowledge_step",
    "execute_mcp_step",
    "execute_condition_step",
    "execute_agent_step",
    "execute_coordinator_step",
    "execute_approval_step",
]

