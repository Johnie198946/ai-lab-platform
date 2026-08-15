"""
backend/services/knowledge_access_guard.py
==========================================
租户写权限 403 物理隔离门禁、Master Admin 独家运营流控制与黄色知识审批流管理器。
"""

from __future__ import annotations
import time
import uuid
from typing import Optional

from backend.models.tenant_agent_schema import TenantContext
from backend.models.knowledge_subscription_schema import (
    KnowledgeItemMetadata,
    KnowledgeSubscriptionRecord,
    SecurityLevel,
    SubscriptionStatus,
)


class AccessDeniedException(Exception):
    """
    权限拒绝异常（对应 HTTP 403 Forbidden 门禁拦截）
    """

    def __init__(self, status_code: int = 403, detail: str = "Access denied"):
        self.status_code = status_code
        self.detail = detail
        self.message = detail
        super().__init__(f"[{status_code}] {detail}")


class KnowledgeAccessGuard:
    """
    知识库访问与写权限安全门禁
    严格贯彻：
    1. 租户只写私有（RED）
    2. 公共知识与其他租户知识禁写（403 阻断）
    3. Master Admin 独家运营与审批主权
    """

    @classmethod
    def check_write_permission(
        cls,
        context: TenantContext,
        item: KnowledgeItemMetadata,
        action: str = "update",
        new_security_level: Optional[SecurityLevel] = None,
    ) -> bool:
        """
        校验租户写权限（新增/修改/删除）
        - Master Admin: 允许写任何知识与设置任何安全定级；
        - 普通租户:
          - 仅允许写 `item.tenant == context.tenant_id` 且自身为 RED 的私有知识；
          - 试图写 `tenant == 'public'` 或其他租户知识 ➔ 403 阻断；
          - 试图将知识标记为 YELLOW 或 GREEN ➔ 403 阻断（防止私权越级升格）。
        """
        if context.is_master_admin:
            return True

        # 1. 租户物理边界校验：禁止写公共知识与跨租户篡改
        if item.tenant == "public" or item.tenant != context.tenant_id:
            raise AccessDeniedException(
                status_code=403,
                detail=f"Forbidden: Tenant '{context.tenant_id}' cannot write to '{item.tenant}' knowledge (target ID: '{item.id}', action: '{action}')",
            )

        # 2. 定级越权校验：普通租户不可自行标记 YELLOW / GREEN
        if item.security_level in (SecurityLevel.YELLOW, SecurityLevel.GREEN):
            raise AccessDeniedException(
                status_code=403,
                detail="Forbidden: Only master admin can assign YELLOW/GREEN security levels",
            )

        if new_security_level in (SecurityLevel.YELLOW, SecurityLevel.GREEN):
            raise AccessDeniedException(
                status_code=403,
                detail="Forbidden: Only master admin can elevate security level to YELLOW/GREEN",
            )

        # 3. 租户修改自身 RED 私有知识 ➔ 放行
        if item.tenant == context.tenant_id and item.security_level == SecurityLevel.RED:
            return True

        return True

    @classmethod
    def check_master_admin_operation(
        cls, context: TenantContext, operation_name: str
    ) -> bool:
        """
        主权操作门禁拦截
        全局公共知识库新增/修改、领域归属、红黄绿定级变更、公共池上架、审批授权等，
        非 Master Admin 调用一律 403 拦截。
        """
        if not context.is_master_admin:
            raise AccessDeniedException(
                status_code=403,
                detail=f"Forbidden: Operation '{operation_name}' requires Master Admin privilege",
            )
        return True

    @classmethod
    def apply_yellow_subscription(
        cls,
        context: TenantContext,
        item: KnowledgeItemMetadata,
        reason: Optional[str] = None,
    ) -> KnowledgeSubscriptionRecord:
        """
        租户发起黄色受限知识订阅申请（生成 PENDING 记录）
        """
        if item.security_level != SecurityLevel.YELLOW:
            raise ValueError(
                f"Knowledge item '{item.id}' is not YELLOW (current: {item.security_level}). "
                "Only YELLOW items require subscription application."
            )

        record_id = f"sub_{uuid.uuid4().hex[:12]}"
        record = KnowledgeSubscriptionRecord(
            subscription_id=record_id,
            tenant_id=context.tenant_id,
            knowledge_id=item.id,
            status=SubscriptionStatus.PENDING,
            applied_at=time.time(),
            reason=reason,
        )
        return record

    @classmethod
    def approve_yellow_subscription(
        cls,
        context: TenantContext,
        record: KnowledgeSubscriptionRecord,
        item: KnowledgeItemMetadata,
    ) -> bool:
        """
        Master Admin 审批通过黄色知识订阅申请
        并将租户加入该知识的 subscribers 白名单。
        """
        cls.check_master_admin_operation(context, "approve_yellow_subscription")

        if record.knowledge_id != item.id:
            raise ValueError(
                f"Subscription record knowledge_id '{record.knowledge_id}' mismatch with item id '{item.id}'"
            )

        record.status = SubscriptionStatus.APPROVED
        record.approved_by = context.user_id
        record.approved_at = time.time()

        if record.tenant_id not in item.subscribers:
            item.subscribers.append(record.tenant_id)

        return True

    @classmethod
    def reject_yellow_subscription(
        cls,
        context: TenantContext,
        record: KnowledgeSubscriptionRecord,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Master Admin 驳回黄色知识订阅申请
        """
        cls.check_master_admin_operation(context, "reject_yellow_subscription")

        record.status = SubscriptionStatus.REJECTED
        record.approved_by = context.user_id
        record.approved_at = time.time()
        if reason:
            record.reason = reason

        return True
