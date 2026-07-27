"""
Rule Schemas
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class FilterNode(BaseModel):
    """Filter node for legacy rule format"""
    type: str = "filter"
    field: str
    operator: str = "equals"
    value: Any = ""
    value_from: Optional[str] = None
    value_to: Optional[str] = None


class AggregationConfig(BaseModel):
    """Aggregation configuration for stage"""
    group_by: List[str] = Field(default_factory=list)
    metric: str = "count"  # count / sum / avg
    alias: str = "count"
    having: Optional[Dict[str, Any]] = None  # {"operator": "gt", "value": 50}


class JoinConfig(BaseModel):
    """Join configuration for stage 2+"""
    from_stage: str
    remote_field: str
    local_field: str


class StageConfig(BaseModel):
    """Stage configuration"""
    id: str
    index: str
    time_window: Optional[Dict[str, int]] = None  # {"minutes": 3}
    filters: List[FilterNode] = Field(default_factory=list)
    aggregation: Optional[AggregationConfig] = None
    join: Optional[JoinConfig] = None


class OutputMapping(BaseModel):
    """Output field mapping"""
    from_stage: str
    field: str


class SeverityCondition(BaseModel):
    """条件判断：满足条件时提升危险等级"""
    field: str = Field(..., description="ES 字段名，如 status, http_status_code")
    operator: str = Field(default="==", pattern="^(==|!=|>|>=|<|<=|contains)$")
    value: Any = Field(..., description="比较值，如 200, 500, 404")
    severity: str = Field(default="high", pattern="^(low|medium|high|critical)$")


class ActionConfig(BaseModel):
    """Action when rule triggers"""
    type: str  # write_mysql / webhook / etc
    table: Optional[str] = None
    mapping: Optional[Dict[str, Any]] = None
    # 危险等级
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    # 条件升級
    severity_conditions: List[SeverityCondition] = Field(default_factory=list)


class RuleCreate(BaseModel):
    """Create rule request"""
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    
    # New format (multi-stage)
    stages: List[StageConfig] = Field(default_factory=list)
    output_mapping: Dict[str, OutputMapping] = Field(default_factory=dict)
    
    # Legacy format (simple filters)
    nodes: List[FilterNode] = Field(default_factory=list)
    
    # ES index (for legacy format)
    es_index: str = "security-logs-*"
    
    # Schedule
    schedule_type: str = Field(default="once", pattern="^(once|interval|cron)$")
    schedule_value: str = ""
    is_enabled: bool = True
    
    # Actions
    actions: List[Dict[str, Any]] = Field(default_factory=list)

    # 危险等级（快捷配置，等效于 actions[0].severity）
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")


class RuleUpdate(BaseModel):
    """Update rule request"""
    name: Optional[str] = None
    description: Optional[str] = None
    stages: Optional[List[StageConfig]] = None
    output_mapping: Optional[Dict[str, OutputMapping]] = None
    nodes: Optional[List[FilterNode]] = None
    es_index: Optional[str] = None
    schedule_type: Optional[str] = None
    schedule_value: Optional[str] = None
    is_enabled: Optional[bool] = None
    actions: Optional[List[Dict[str, Any]]] = None
    severity: Optional[str] = None


class RuleResponse(BaseModel):
    """Rule response"""
    id: int
    name: str
    description: str
    es_index: str
    schedule_type: str
    schedule_value: str
    is_enabled: bool
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    created_at: Optional[datetime] = None
    
    # New format
    stages: List[Dict[str, Any]] = Field(default_factory=list)
    output_mapping: Dict[str, Any] = Field(default_factory=dict)
    
    # Legacy format
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Actions
    actions: List[Dict[str, Any]] = Field(default_factory=list)

    # 危险等级
    severity: str = "medium"

    class Config:
        from_attributes = True
