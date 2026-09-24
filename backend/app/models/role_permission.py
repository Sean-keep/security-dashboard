"""
RolePermission Model - 角色 → 权限点矩阵（系统管理员可勾选分配）
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.models.base import Base


class RolePermission(Base):
    """每个角色持有哪些权限点。

    存成逗号分隔的名字串而不是 JSON：五个权限点，逗号串在 SQL 里肉眼可读，
    也方便手工 INSERT IGNORE 修数据。空串 = 该角色什么都不持有。
    """
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(String(32), unique=True, nullable=False, index=True)
    permissions = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    updated_by = Column(String(64), default="")

    def __repr__(self):
        return f"<RolePermission(role='{self.role}', permissions='{self.permissions}')>"
