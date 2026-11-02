from app.rag.retrieval import search
from app.workflows.steps.base import StepExecutionContext, StepResult
from app.workflows.template import render_template


async def execute_knowledge_step(ctx: StepExecutionContext) -> StepResult:
    config = ctx.step_config
    query_raw = config.get("query", "")
    top_k = int(config.get("top_k", 5))

    rendered_query = str(render_template(query_raw, ctx.context))
    passages = await search(
        ctx.session,
        workspace_id=ctx.workspace_id,
        query=rendered_query,
        top_k=top_k,
    )

    passages_data = [
        {
            "chunk_id": str(p.chunk_id),
            "document_id": str(p.document_id),
            "filename": p.filename,
            "chunk_index": p.chunk_index,
            "content": p.content,
            "token_count": p.token_count,
            "score": round(p.score, 4),
        }
        for p in passages
    ]

    return StepResult(
        output={
            "query": rendered_query,
            "passages": passages_data,
            "count": len(passages_data),
        }
    )

