from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NodeType = Literal[
    "trigger.command",
    "trigger.message",
    "trigger.callback",
    "action.message",
    "action.edit_message",
    "action.delete_message",
    "action.http",
    "action.delay",
    "condition.if",
    "data.set",
    "data.get",
]


class WorkflowNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    type: NodeType
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=100)
    condition: str | None = Field(default=None, max_length=1000)


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    nodes: list[WorkflowNode] = Field(default_factory=list, max_length=500)
    edges: list[WorkflowEdge] = Field(default_factory=list, max_length=1000)
    variables: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_graph(self) -> WorkflowDefinition:
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("workflow node ids must be unique")
        known = set(ids)
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError("workflow edges must reference existing nodes")
        if self.nodes and not any(node.type.startswith("trigger.") for node in self.nodes):
            raise ValueError("workflow must contain at least one trigger node")
        return self
