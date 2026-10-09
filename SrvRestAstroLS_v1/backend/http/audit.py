"""Audit temporary operations explicitly, before acknowledging them to the caller.

Durable file writes use FileRepository's own transaction, not this helper.
No annual reconciliation decisions are persisted here.
"""
from uuid import uuid4


async def audit_temporary(request, action, resource, result='SUCCESS', reason='in_memory_only; not a durable financial decision'):
    correlation = getattr(request.state, 'correlation_id', None) or uuid4()
    request.state.correlation_id = correlation
    await request.app.state.security.audit_operation(
        request.state.principal.id, action, str(resource), result, correlation, reason)
