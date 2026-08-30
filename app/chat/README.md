# Chat boundaries

`ChatService` owns the chat use case and Manager session setup. `StreamOrchestrator` merges SDK
and nested-agent events. `SafeTraceMapper` is the only place that converts SDK events into the
public, redacted SSE trace format.
