"""
tests/test_multi_tenant_backend.py
==================================
全量单元测试套件：覆盖多租户切片、写权限 403 阻断、Master 主权审批流、
红黄绿 ABAC Pre-filter 检索隔离（支持 PostgreSQL 与 SQLite 方言）、DSL 安全编译器与 Kahn 算法 DAG 无环拓扑排序。
"""

import time
import pytest
from typing import Dict, Any

from backend.models.tenant_agent_schema import (
    TenantRole,
    TenantContext,
    BaseAgentSlice,
    TenantAgentDelta,
    TenantAgentConfig,
    WorkflowNodeType,
    WorkflowDSLNode,
    WorkflowDSLEdge,
    WorkflowDSLPlan,
)
from backend.models.knowledge_subscription_schema import (
    SecurityLevel,
    DomainEnum,
    SubscriptionStatus,
    KnowledgeItemMetadata,
    KnowledgeSubscriptionRecord,
    MerkleDAGNode,
)
from backend.services.tenant_isolation_middleware import (
    TenantContextExtractor,
    ABACPreFilterGenerator,
)
from backend.services.knowledge_access_guard import (
    AccessDeniedException,
    KnowledgeAccessGuard,
)
from backend.services.dsl_safety_compiler import (
    DSLSafetyCompiler,
    DSLValidationError,
    InvalidEdgeReferenceError,
    CyclicDependencyError,
)


# ==============================================================================
# 1. 租户切片与 Agent Delta 组合测试
# ==============================================================================

class TestTenantAgentSlicing:
    """测试 Base Slice 与 Tenant Delta 的组装及不可变性"""

    def test_base_slice_and_delta_composition(self):
        base = BaseAgentSlice(
            base_agent_id="coder",
            name="AI Lab Coder",
            immutable_system_prompt="You are a senior python engineer.",
            allowed_tools=["terminal", "read_file", "write_file"],
            version="1.0.0",
        )

        delta = TenantAgentDelta(
            tenant_id="tenant_alpha",
            base_agent_id="coder",
            custom_name="Alpha Private Coder",
            custom_avatar="https://img.example.com/avatar1.png",
            private_prompt_delta="Strictly follow PEP8 and add Chinese docstrings.",
            subscribed_knowledge_packs=["pack_manufacturing_01"],
            is_active=True,
        )

        config = TenantAgentConfig.from_slice_and_delta(base, delta)

        assert config.tenant_id == "tenant_alpha"
        assert config.base_agent_id == "coder"
        assert config.effective_name == "Alpha Private Coder"
        assert config.effective_avatar == "https://img.example.com/avatar1.png"
        assert "You are a senior python engineer." in config.effective_prompt
        assert "[Tenant Context: tenant_alpha]" in config.effective_prompt
        assert "Strictly follow PEP8" in config.effective_prompt
        assert config.allowed_tools == ["terminal", "read_file", "write_file"]
        assert config.subscribed_knowledge_packs == ["pack_manufacturing_01"]
        assert config.is_active is True

    def test_delta_mismatch_raises_value_error(self):
        base = BaseAgentSlice(
            base_agent_id="coder",
            name="AI Lab Coder",
            immutable_system_prompt="Prompt A",
        )
        delta = TenantAgentDelta(
            tenant_id="tenant_alpha",
            base_agent_id="supervision",
            custom_name="Invalid Delta",
        )
        with pytest.raises(ValueError, match="Base agent ID mismatch"):
            TenantAgentConfig.from_slice_and_delta(base, delta)

    def test_tenant_context_jwt_extractor(self):
        claims = {
            "tenant_id": "tenant_99",
            "user_id": "user_42",
            "role": "tenant_admin",
            "permissions": ["read_kb", "write_private"],
        }
        ctx = TenantContextExtractor.from_jwt_claims(claims)
        assert ctx.tenant_id == "tenant_99"
        assert ctx.user_id == "user_42"
        assert ctx.role == TenantRole.TENANT_ADMIN
        assert ctx.permissions == ["read_kb", "write_private"]
        assert ctx.is_master_admin is False

    def test_tenant_context_header_extractor_and_master(self):
        headers = {
            "X-Tenant-ID": "master",
            "X-User-ID": "admin_01",
            "X-User-Role": "master_admin",
        }
        ctx = TenantContextExtractor.from_headers(headers)
        assert ctx.tenant_id == "master"
        assert ctx.user_id == "admin_01"
        assert ctx.role == TenantRole.MASTER_ADMIN
        assert ctx.is_master_admin is True

    def test_tenant_context_extractor_missing_fields_raises(self):
        with pytest.raises(ValueError, match="must contain 'X-Tenant-ID'"):
            TenantContextExtractor.from_headers({"X-User-ID": "user_1"})

        with pytest.raises(ValueError, match="must contain 'tenant_id'"):
            TenantContextExtractor.from_jwt_claims({"user_id": "user_1"})


# ==============================================================================
# 2. 写权限 403 物理隔离硬锁测试
# ==============================================================================

class TestWritePermissionHardLock:
    """测试租户写权限隔离与 403 Forbidden 门禁"""

    @pytest.fixture
    def normal_tenant_context(self):
        return TenantContext(tenant_id="tenant_A", user_id="user_A1", role=TenantRole.TENANT_MEMBER)

    @pytest.fixture
    def other_tenant_context(self):
        return TenantContext(tenant_id="tenant_B", user_id="user_B1", role=TenantRole.TENANT_MEMBER)

    @pytest.fixture
    def master_admin_context(self):
        return TenantContext(tenant_id="master", user_id="root_user", role=TenantRole.MASTER_ADMIN)

    def test_tenant_cannot_write_public_knowledge(self, normal_tenant_context):
        pub_item = KnowledgeItemMetadata(
            id="kb_pub_001",
            title="Industry Standard",
            domain="manufacturing",
            tenant="public",
            security_level=SecurityLevel.GREEN,
        )
        with pytest.raises(AccessDeniedException) as exc_info:
            KnowledgeAccessGuard.check_write_permission(normal_tenant_context, pub_item, action="update")
        assert exc_info.value.status_code == 403
        assert "cannot write to 'public' knowledge" in exc_info.value.detail

    def test_tenant_cannot_write_other_tenant_knowledge(self, normal_tenant_context):
        other_item = KnowledgeItemMetadata(
            id="kb_priv_B",
            title="Tenant B Secret",
            domain="finance",
            tenant="tenant_B",
            security_level=SecurityLevel.RED,
        )
        with pytest.raises(AccessDeniedException) as exc_info:
            KnowledgeAccessGuard.check_write_permission(normal_tenant_context, other_item, action="delete")
        assert exc_info.value.status_code == 403
        assert "cannot write to 'tenant_B' knowledge" in exc_info.value.detail

    def test_tenant_cannot_elevate_security_level_to_yellow_or_green(self, normal_tenant_context):
        own_item = KnowledgeItemMetadata(
            id="kb_priv_A",
            title="Tenant A Private Code",
            domain="tokenops",
            tenant="tenant_A",
            security_level=SecurityLevel.RED,
        )
        with pytest.raises(AccessDeniedException) as exc_info:
            KnowledgeAccessGuard.check_write_permission(
                normal_tenant_context, own_item, new_security_level=SecurityLevel.YELLOW
            )
        assert exc_info.value.status_code == 403
        assert "Only master admin can elevate security level" in exc_info.value.detail

    def test_tenant_can_write_own_red_knowledge(self, normal_tenant_context):
        own_item = KnowledgeItemMetadata(
            id="kb_priv_A_02",
            title="Tenant A Notes",
            domain="audit",
            tenant="tenant_A",
            security_level=SecurityLevel.RED,
        )
        assert KnowledgeAccessGuard.check_write_permission(normal_tenant_context, own_item, action="update") is True

    def test_master_admin_can_write_any_knowledge(self, master_admin_context):
        pub_item = KnowledgeItemMetadata(
            id="kb_pub_001",
            title="Global Architecture",
            tenant="public",
            security_level=SecurityLevel.GREEN,
        )
        other_item = KnowledgeItemMetadata(
            id="kb_priv_B",
            title="Tenant B Private",
            tenant="tenant_B",
            security_level=SecurityLevel.RED,
        )
        assert KnowledgeAccessGuard.check_write_permission(master_admin_context, pub_item) is True
        assert KnowledgeAccessGuard.check_write_permission(
            master_admin_context, other_item, new_security_level=SecurityLevel.YELLOW
        ) is True


# ==============================================================================
# 3. Master Admin 运营主权与黄色知识审批流测试
# ==============================================================================

class TestMasterAdminSovereigntyAndApproval:
    """测试超级管理员独家运营权与黄色知识审批"""

    def test_non_master_admin_operation_blocked(self):
        tenant_ctx = TenantContext(tenant_id="tenant_X", user_id="user_X", role=TenantRole.TENANT_ADMIN)
        with pytest.raises(AccessDeniedException) as exc_info:
            KnowledgeAccessGuard.check_master_admin_operation(tenant_ctx, "publish_global_kb")
        assert exc_info.value.status_code == 403
        assert "requires Master Admin privilege" in exc_info.value.detail

    def test_yellow_subscription_lifecycle(self):
        tenant_ctx = TenantContext(tenant_id="tenant_app", user_id="user_app", role=TenantRole.TENANT_MEMBER)
        master_ctx = TenantContext(tenant_id="master", user_id="super_admin", role=TenantRole.MASTER_ADMIN)

        yellow_item = KnowledgeItemMetadata(
            id="kb_yellow_best_practice",
            title="High-level Auditing Methodology",
            domain="audit",
            tenant="public",
            security_level=SecurityLevel.YELLOW,
            subscribers=[],
        )

        # 1. 租户申请订阅
        record = KnowledgeAccessGuard.apply_yellow_subscription(
            tenant_ctx, yellow_item, reason="Need for Q3 financial audit"
        )
        assert record.status == SubscriptionStatus.PENDING
        assert record.tenant_id == "tenant_app"
        assert record.knowledge_id == "kb_yellow_best_practice"

        # 2. 普通租户无权审批
        with pytest.raises(AccessDeniedException):
            KnowledgeAccessGuard.approve_yellow_subscription(tenant_ctx, record, yellow_item)

        # 3. Master Admin 审批通过
        success = KnowledgeAccessGuard.approve_yellow_subscription(master_ctx, record, yellow_item)
        assert success is True
        assert record.status == SubscriptionStatus.APPROVED
        assert record.approved_by == "super_admin"
        assert "tenant_app" in yellow_item.subscribers

        # 4. 测试驳回流
        record2 = KnowledgeAccessGuard.apply_yellow_subscription(
            TenantContext(tenant_id="tenant_reject", user_id="u_r"), yellow_item
        )
        rej_success = KnowledgeAccessGuard.reject_yellow_subscription(
            master_ctx, record2, reason="Security review failed"
        )
        assert rej_success is True
        assert record2.status == SubscriptionStatus.REJECTED
        assert record2.reason == "Security review failed"
        assert "tenant_reject" not in yellow_item.subscribers


# ==============================================================================
# 4. 红黄绿 ABAC Pre-Filter 与隔离检索断言测试
# ==============================================================================

class TestABACPreFilterAndIsolation:
    """测试红黄绿知识分类在 SQL 生成与内存断言中的严格隔离"""

    @pytest.fixture
    def sample_multi_tenant_corpus(self):
        return [
            # 1. 红色私有知识
            KnowledgeItemMetadata(
                id="k_red_A", title="Secret A", domain="finance", tenant="tenant_A", security_level=SecurityLevel.RED
            ),
            KnowledgeItemMetadata(
                id="k_red_B", title="Secret B", domain="finance", tenant="tenant_B", security_level=SecurityLevel.RED
            ),
            # 2. 黄色受限知识
            KnowledgeItemMetadata(
                id="k_yellow_01",
                title="Special Framework",
                domain="audit",
                tenant="public",
                security_level=SecurityLevel.YELLOW,
                subscribers=["tenant_A"],
            ),
            # 3. 绿色公开知识
            KnowledgeItemMetadata(
                id="k_green_01",
                title="Universal Standards",
                domain="general",
                tenant="public",
                security_level=SecurityLevel.GREEN,
            ),
            KnowledgeItemMetadata(
                id="k_green_audit",
                title="Public Audit Guidelines",
                domain="audit",
                tenant="public",
                security_level=SecurityLevel.GREEN,
            ),
            # 4. 存量无标签条目（字典形式）
            {
                "id": "k_legacy_01",
                "title": "Legacy Public Note",
            },
        ]

    def test_sql_filter_generation(self):
        ctx = TenantContext(tenant_id="tenant_123", user_id="user_1")
        
        # PostgreSQL 方言（默认）
        sql_pg, params_pg = ABACPreFilterGenerator.build_sql_filter(ctx, domain="manufacturing", dialect="postgresql")
        assert "tenant = :current_tenant" in sql_pg
        assert "security_level = 'green'" in sql_pg
        assert ":current_tenant = ANY(subscribers)" in sql_pg
        assert "domain = :req_domain OR domain = 'general'" in sql_pg
        assert params_pg["current_tenant"] == "tenant_123"
        assert params_pg["req_domain"] == "manufacturing"

        # SQLite 方言
        sql_sqlite, params_sqlite = ABACPreFilterGenerator.build_sql_filter(ctx, domain="manufacturing", dialect="sqlite")
        assert "tenant = :current_tenant" in sql_sqlite
        assert "security_level = 'green'" in sql_sqlite
        assert "EXISTS (SELECT 1 FROM json_each(subscribers) WHERE value = :current_tenant)" in sql_sqlite
        assert "domain = :req_domain OR domain = 'general'" in sql_sqlite
        assert params_sqlite["current_tenant"] == "tenant_123"
        assert params_sqlite["req_domain"] == "manufacturing"

        # Master Admin 全局穿透
        ctx_master = TenantContext(tenant_id="master", user_id="root", role=TenantRole.MASTER_ADMIN)
        sql_master, params_master = ABACPreFilterGenerator.build_sql_filter(ctx_master, domain="finance")
        assert "(1 = 1)" in sql_master

    def test_red_knowledge_isolation(self, sample_multi_tenant_corpus):
        ctx_a = TenantContext(tenant_id="tenant_A", user_id="u_a")
        ctx_b = TenantContext(tenant_id="tenant_B", user_id="u_b")

        # 租户 A 可见自己的 RED 知识，不可见租户 B 的 RED 知识
        assert ABACPreFilterGenerator.matches_in_memory(ctx_a, sample_multi_tenant_corpus[0]) is True
        assert ABACPreFilterGenerator.matches_in_memory(ctx_a, sample_multi_tenant_corpus[1]) is False

        # 租户 B 可见自己的 RED 知识，不可见租户 A 的 RED 知识
        assert ABACPreFilterGenerator.matches_in_memory(ctx_b, sample_multi_tenant_corpus[0]) is False
        assert ABACPreFilterGenerator.matches_in_memory(ctx_b, sample_multi_tenant_corpus[1]) is True

    def test_yellow_subscription_filtering(self, sample_multi_tenant_corpus):
        ctx_a = TenantContext(tenant_id="tenant_A", user_id="u_a")
        ctx_b = TenantContext(tenant_id="tenant_B", user_id="u_b")
        yellow_item = sample_multi_tenant_corpus[2]  # subscribers: ["tenant_A"]

        # 租户 A 已在 subscribers 列表中 ➔ 可见
        assert ABACPreFilterGenerator.matches_in_memory(ctx_a, yellow_item, domain="audit") is True

        # 租户 B 未订阅 ➔ 召回严格恒为 False (不可见)
        assert ABACPreFilterGenerator.matches_in_memory(ctx_b, yellow_item, domain="audit") is False

    def test_green_knowledge_visibility(self, sample_multi_tenant_corpus):
        ctx_a = TenantContext(tenant_id="tenant_A", user_id="u_a")
        ctx_b = TenantContext(tenant_id="tenant_B", user_id="u_b")
        green_item = sample_multi_tenant_corpus[3]

        assert ABACPreFilterGenerator.matches_in_memory(ctx_a, green_item) is True
        assert ABACPreFilterGenerator.matches_in_memory(ctx_b, green_item) is True

    def test_domain_filtering_mechanism(self, sample_multi_tenant_corpus):
        ctx = TenantContext(tenant_id="tenant_A", user_id="u_a")
        audit_green = sample_multi_tenant_corpus[4]

        # 检索 audit 域 ➔ 命中
        assert ABACPreFilterGenerator.matches_in_memory(ctx, audit_green, domain="audit") is True
        # 检索 healthcare 域 ➔ 过滤掉
        assert ABACPreFilterGenerator.matches_in_memory(ctx, audit_green, domain="healthcare") is False
        # 通用 general 域知识在任何 domain 检索时均可见
        general_green = sample_multi_tenant_corpus[3]
        assert ABACPreFilterGenerator.matches_in_memory(ctx, general_green, domain="healthcare") is True

    def test_legacy_fallback_no_key_error(self, sample_multi_tenant_corpus):
        ctx = TenantContext(tenant_id="tenant_A", user_id="u_a")
        legacy_dict = sample_multi_tenant_corpus[5]
        # 无标签条目安全回退为 public/general/green
        assert ABACPreFilterGenerator.matches_in_memory(ctx, legacy_dict) is True


# ==============================================================================
# 5. DSL 语法校验与 Kahn 算法 DAG 拓扑检测测试
# ==============================================================================

class TestDSLSafetyAndKahnDAG:
    """测试 DSL 安全编译、节点白名单与 Kahn 拓扑排序"""

    def test_valid_linear_dag(self):
        plan_dict = {
            "plan_id": "linear_workflow_01",
            "name": "Linear LLM Task",
            "nodes": [
                {"id": "node_retrieval", "node_type": "KNOWLEDGE_RETRIEVAL", "parameters": {}},
                {"id": "node_transform", "node_type": "PROMPT_TRANSFORM", "parameters": {}},
                {"id": "node_inference", "node_type": "LLM_INFERENCE", "parameters": {"temperature": 0.7}},
                {"id": "node_output", "node_type": "OUTPUT_FORMAT", "parameters": {}},
            ],
            "edges": [
                {"source": "node_retrieval", "target": "node_transform"},
                {"source": "node_transform", "target": "node_inference"},
                {"source": "node_inference", "target": "node_output"},
            ],
        }
        plan = DSLSafetyCompiler.compile_and_validate(plan_dict)
        order = DSLSafetyCompiler.check_dag_cycle_kahn(plan)
        assert order == ["node_retrieval", "node_transform", "node_inference", "node_output"]

    def test_valid_diamond_dag(self):
        plan_dict = {
            "plan_id": "diamond_workflow_02",
            "name": "Parallel Aggregation",
            "nodes": [
                {"id": "start", "node_type": "PROMPT_TRANSFORM"},
                {"id": "branch_a", "node_type": "LLM_INFERENCE", "parameters": {"temperature": 0.2}},
                {"id": "branch_b", "node_type": "LLM_INFERENCE", "parameters": {"temperature": 0.5}},
                {"id": "join_agg", "node_type": "AGGREGATION"},
            ],
            "edges": [
                {"source": "start", "target": "branch_a"},
                {"source": "start", "target": "branch_b"},
                {"source": "branch_a", "target": "join_agg"},
                {"source": "branch_b", "target": "join_agg"},
            ],
        }
        plan = DSLSafetyCompiler.compile_and_validate(plan_dict)
        order = DSLSafetyCompiler.check_dag_cycle_kahn(plan)
        assert order[0] == "start"
        assert order[-1] == "join_agg"
        assert set(order[1:3]) == {"branch_a", "branch_b"}

    def test_cycle_detection_kahn(self):
        # A -> B -> C -> A 环路
        plan_dict = {
            "plan_id": "cyclic_workflow",
            "name": "Invalid Cyclic Plan",
            "nodes": [
                {"id": "node_a", "node_type": "LLM_INFERENCE"},
                {"id": "node_b", "node_type": "PROMPT_TRANSFORM"},
                {"id": "node_c", "node_type": "FILTER_PASS"},
            ],
            "edges": [
                {"source": "node_a", "target": "node_b"},
                {"source": "node_b", "target": "node_c"},
                {"source": "node_c", "target": "node_a"},
            ],
        }
        with pytest.raises(CyclicDependencyError) as exc_info:
            DSLSafetyCompiler.compile_and_validate(plan_dict)
        assert set(exc_info.value.cycle_nodes) == {"node_a", "node_b", "node_c"}

    def test_dangling_edge_detection(self):
        plan_dict = {
            "plan_id": "dangling_plan",
            "nodes": [
                {"id": "node_1", "node_type": "LLM_INFERENCE"},
            ],
            "edges": [
                {"source": "node_1", "target": "node_non_existent"},
            ],
        }
        with pytest.raises(InvalidEdgeReferenceError, match="does not exist"):
            DSLSafetyCompiler.compile_and_validate(plan_dict)

    def test_illegal_node_type_rejection(self):
        plan_dict = {
            "plan_id": "attack_plan",
            "nodes": [
                {"id": "node_evil", "node_type": "SHELL_EXEC", "parameters": {"cmd": "rm -rf /"}},
            ],
            "edges": [],
        }
        with pytest.raises(DSLValidationError, match="Disallowed node_type 'SHELL_EXEC'"):
            DSLSafetyCompiler.compile_and_validate(plan_dict)

    def test_parameter_boundary_validation(self):
        plan_dict = {
            "plan_id": "invalid_param_plan",
            "nodes": [
                {"id": "node_inf", "node_type": "LLM_INFERENCE", "parameters": {"temperature": 4.5}},
            ],
            "edges": [],
        }
        with pytest.raises(DSLValidationError, match="must be in range"):
            DSLSafetyCompiler.compile_and_validate(plan_dict)


# ==============================================================================
# 6. Merkle DAG 因果血缘校验测试
# ==============================================================================

class TestMerkleDAGLineage:
    """测试知识条目 Merkle 因果血缘指纹生成与防投毒校验"""

    def test_merkle_dag_hash_calculation(self):
        item = KnowledgeItemMetadata(
            id="kb_item_100",
            title="Analysis Methodology",
            domain="tokenops",
            tenant="tenant_01",
            security_level=SecurityLevel.RED,
            upstream_ids=["kb_item_090", "kb_item_091"],
        )
        h1 = item.compute_lineage_hash(raw_content="Content payload v1")
        assert item.lineage_hash == h1
        assert len(h1) == 64

        # 内容变动导致 Hash 变更
        h2 = item.compute_lineage_hash(raw_content="Content payload v2 - altered")
        assert h1 != h2

    def test_merkle_node_integrity(self):
        node = MerkleDAGNode(
            node_id="node_dag_1",
            data_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            parent_hashes=["parent_hash_alpha", "parent_hash_beta"],
        )
        digest = node.calculate_merkle_hash()
        assert len(digest) == 64


# ==============================================================================
# 7. 性能基准测试 (< 1.0s)
# ==============================================================================

class TestPerformanceBenchmark:
    """性能基准：断言 1000 次 ABAC 匹配与 500 次 Kahn 拓扑排序耗时 < 1.0s"""

    def test_execution_performance(self):
        ctx = TenantContext(tenant_id="tenant_speed", user_id="u_speed")
        item = KnowledgeItemMetadata(
            id="kb_perf_01",
            title="Performance Test Doc",
            domain="general",
            tenant="public",
            security_level=SecurityLevel.GREEN,
        )

        plan_dict = {
            "plan_id": "perf_plan",
            "nodes": [
                {"id": "n1", "node_type": "PROMPT_TRANSFORM"},
                {"id": "n2", "node_type": "KNOWLEDGE_RETRIEVAL"},
                {"id": "n3", "node_type": "LLM_INFERENCE"},
                {"id": "n4", "node_type": "OUTPUT_FORMAT"},
            ],
            "edges": [
                {"source": "n1", "target": "n2"},
                {"source": "n2", "target": "n3"},
                {"source": "n3", "target": "n4"},
            ],
        }

        t_start = time.perf_counter()

        # 1000 次 ABAC 过滤断言
        for _ in range(1000):
            ABACPreFilterGenerator.matches_in_memory(ctx, item)

        # 500 次 Kahn 算法编译与无环检测
        for _ in range(500):
            DSLSafetyCompiler.compile_and_validate(plan_dict)

        duration = time.perf_counter() - t_start
        assert duration < 1.0, f"Benchmark took {duration:.4f}s, exceeding 1.0s limit"
