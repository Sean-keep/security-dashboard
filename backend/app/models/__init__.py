"""Security Dashboard Backend - Models Module

Every model must be imported here. ``Base.metadata.create_all()`` only creates
tables for models that have been imported — a fresh install would silently miss
``ingest_logs`` / ``remote_executions`` / ``scripts`` … until some API module
happened to pull them in, and then the first write would 500.
"""
from .base import Base, engine, SessionLocal, get_db
from .user import User, LoginLog
from .address import Address
from .rule import Rule
from .alert import Alert
from .config import SystemConfig
from .execution_log import RuleExecutionLog
from .operation_log import OperationLog
from .ingest_endpoint import IngestEndpoint
from .ingest_log import IngestLog
from .ingest_sender import IngestSender
from .remote_execution import RemoteExecution
from .remote_host import RemoteHost
from .script import Script
from .script_run import ScriptRunLog
from .custom_metric import CustomMetric
from .inspection_report import InspectionReport

__all__ = [
    "Base", "engine", "SessionLocal", "get_db",
    "User", "LoginLog",
    "Address",
    "Rule",
    "Alert",
    "SystemConfig",
    "RuleExecutionLog",
    "OperationLog",
    "IngestEndpoint",
    "IngestLog",
    "IngestSender",
    "RemoteExecution",
    "RemoteHost",
    "Script",
    "ScriptRunLog",
    "CustomMetric",
    "InspectionReport",
]
