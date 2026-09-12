"""Local research handoff; PluginState projection, existing Vault writer only.

Settings (ctx.get_config('research_deposit', {})): enabled (default False),
deployment_mode (local_single_tenant), vault_root, pipeline_module (absolute
trusted Python file). Owner identity reuses capability_router's authority.
No model-selected paths.
Hooks are advisory in current Hermes. verify_completion is the task-scoped
finalizer adapter; a host must call it even on interrupt/error for a hard gate.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
import threading
from urllib.parse import urlsplit, parse_qsl, unquote

POLICY_VERSION = "local-research-v1"
STORAGE_SCOPE = "user_vault_existing_sync"
_IMPORT_LOCK = threading.Lock()
NO_SAVE = re.compile(r"只看看|(?:先)?不(?:要)?(?:保存|入库|落盘|归档|存储|存(?!在)|记录)|别(?:保存|入库)|do\s+not\s+(?:save|store|archive|record)|don['’]t\s+(?:save|store|record)|no[ -]save|view\s+only", re.I)
RESEARCH = re.compile(r"https?://|研究|调研|研读|research|investigate|literature review", re.I)
NOT_RESEARCH = re.compile(r"^\s*(?:请(?:帮我)?\s*|please\s+)?(?:翻译|仅摘要|只(?:做)?摘要|仅(?:做)?总结|只回答|仅回答|translate\b|translation\b|summari[sz]e\b|answer\s+only)", re.I)
CONTINUATION = re.compile(r"^(?:继续|接着|接续|continue\b|carry on\b)", re.I)
WRITER_CONTROL = re.compile(r"wiki[ _-]?writer|wiki\s*编译|编译.*manifest|沉淀补偿", re.I)
DEPOSIT_CONTROL = re.compile(r"^(?:请)?(?:(?:查看|核验|恢复|补偿).{0,12}(?:沉淀|入库)|(?:沉淀|入库).{0,12}(?:状态|恢复|补偿)|research_deposit\s+action\s*[=:]\s*(?:status|recover))", re.I)
SENSITIVE_QUERY = re.compile(r"^(?:token|access_token|refresh_token|api_key|apikey|key|secret|password|auth|authorization|signature|x-amz-signature|code)$", re.I)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def is_research(text):
    return bool(RESEARCH.search(text or "")) and not NOT_RESEARCH.search(text or "")


class ResearchDeposit:
    def __init__(self, ctx):
        self.ctx = ctx

    def config(self):
        value = self.ctx.get_config("research_deposit", {}) if hasattr(self.ctx, "get_config") else {}
        return value if isinstance(value, dict) else {}

    def enabled(self):
        cfg = self.config()
        return (getattr(self.ctx, "profile_name", "") == "default"
                and cfg.get("enabled", False) is True
                and cfg.get("deployment_mode") == "local_single_tenant"
                and os.environ.get("AI_LAB_AGENT_OS_MODE") != "cloud_multi_tenant")

    def allowed(self, scope, *, stored=None, read_only=False):
        cfg = self.config()
        if getattr(self.ctx, "profile_name", "") != "default" or (not read_only and not self.enabled()):
            return False
        if cfg.get("deployment_mode") != "local_single_tenant":
            return False
        # Legacy deployment switch is a denial only, never an authorization.
        if os.environ.get("AI_LAB_AGENT_OS_MODE") == "cloud_multi_tenant":
            return False
        if scope.get("parent_session_id") or scope.get("sensitivity", "public") != "public":
            return False
        if stored is not None:
            return stored.get("owner") == "local_owner" and stored.get("policy_version") == POLICY_VERSION
        platform = str(getattr(scope.get("platform"), "value", scope.get("platform")) or "").casefold()
        sender = str(scope.get("sender_id") or "")
        from .capability_router import _resolve_principal
        return _resolve_principal(platform, sender, str(scope.get("user_message") or "")) == "local_owner"

    def scope(self, kw):
        # kwargs are host registry callbacks, NOT the model's inputs object.
        return {k: str(kw.get(k) or "") for k in ("session_id", "turn_id", "task_id")}

    def tool_scope(self, kw):
        scope = self.scope(kw)
        from tools import approval
        getter = getattr(approval, "get_current_observability_context", None)
        # Current SDK only exposes set/reset, so read its native contextvars.
        observed = getter() if getter else {"session_id": approval._approval_session_id.get(),
                                            "turn_id": approval._approval_turn_id.get()}
        if observed.get("session_id"):
            if observed["session_id"] != scope["session_id"]:
                raise ValueError("host_observability_session_mismatch")
            if scope["turn_id"] and scope["turn_id"] != observed.get("turn_id"):
                raise ValueError("host_observability_turn_mismatch")
            scope["turn_id"] = str(observed.get("turn_id") or "")
        return scope

    def key(self, scope):
        if not all(scope.values()):
            raise ValueError("host_session_turn_task_required")
        # Task veto spans retry turns; revisions/receipts retain exact turn binding.
        return "research:" + digest([scope["session_id"], scope["task_id"]])

    def item_id(self, payload):
        # Identity is a source, NEVER a body/revision/title hash. URL-less legacy
        # records share one explicit slot until corrected with a real source.
        urls = payload.get("source_urls") or []
        return "item:" + digest(["primary_source", urls[0] if urls else None])

    def migrate(self, record):
        """Lossless in-place v1 -> task/items projection; never mint authority."""
        if "items" in record or not record.get("obligation") or record.get("veto"):
            return record
        legacy = dict(record)
        record.clear()
        for field in ("scope", "owner", "policy_version", "obligation"):
            if field in legacy:
                record[field] = legacy[field]
        record.update(schema_version=2, items={}, stage="research", migrated_from="single_record_v1")
        if legacy.get("payload") or legacy.get("source_revision") or legacy.get("receipt"):
            identity = self.item_id(legacy.get("payload") or {})
            legacy["item_id"] = identity
            record["items"][identity] = legacy
        else:
            # Preserve even unknown legacy fields; no silent loss on migration.
            record["legacy_metadata"] = legacy
            record["stage"] = legacy.get("stage", "research")
            if legacy.get("reason"):
                record["reason"] = legacy["reason"]
        return record

    def lock(self, key):
        from hermes_cli.plugins import _locked_plugin_state
        # Native host lock, separate from state.json's atomic read/write lock.
        return _locked_plugin_state(self.ctx.state.data_dir / (key.replace(":", "-") + ".transaction"))

    def pre(self, user_message="", **kw):
        scope = self.scope(kw)
        if not all(scope.values()):
            return None
        key = self.key(scope)
        with self.lock(key):
            old = self.ctx.state.get(key, {})
            # Opt-out BEFORE copying any title, URL, body or message digest.
            if NO_SAVE.search(user_message or ""):
                old.update(veto=True, stage="blocked", reason="no_save")
                self.ctx.state.set(key, old)
                return {"context": "[Research deposit blocked: no_save] No save permitted. Lifting requires verified same-material host consent; this host has no supported consent association."}
            if old.get("veto"):
                return {"context": "[Research deposit blocked: no_save] Same-material consent association unavailable; explicit text alone cannot lift this veto."}
            if not self.allowed(dict(kw, user_message=user_message), read_only=True):
                return None  # Policy is an overlay, never replace recovery evidence.
            platform = str(getattr(kw.get("platform"), "value", kw.get("platform")) or "").casefold()
            if (old.get("control") or kw.get("task_purpose") in {"wiki_compile", "research_recovery"}
                    or (platform == "cron" and WRITER_CONTROL.search(re.split(r"[\n。；;，,]", (user_message or "").strip(), maxsplit=1)[0]))
                    or DEPOSIT_CONTROL.search(user_message or "")):
                if not old.get("obligation"):
                    self.ctx.state.set(key, {"scope": scope, "owner": "local_owner", "policy_version": POLICY_VERSION,
                                            "control": True, "stage": "not_applicable"})
                return {"context": "[Research maintenance] This is Writer/recovery work, not a research-save obligation. Use research_deposit action=status for bounded pending scope references, then action=recover. Writer remains manifest-only. New evidence is blocked (research_task_association_required): a separate host-authorized research task must explicitly hand off adopted material; control text cannot grant it."}
            if not self.enabled():
                return None
            if not is_research(user_message) and not old.get("obligation"):
                if CONTINUATION.search(user_message or ""):
                    self.ctx.state.set(key, {"stage": "blocked", "reason": "continuation_scope_required"})
                    return {"context": "[Research deposit blocked] Continuation lacks a canonical task relationship; do not reuse another task's receipt. Continue the useful answer without claiming saved."}
                return None
            if NOT_RESEARCH.search(user_message or ""):
                # An unrelated request cannot destroy an existing obligation.
                if not old.get("obligation"):
                    self.ctx.state.set(key, {"stage": "not_applicable", "reason": "nonresearch_request"})
                return None
            if old.get("obligation"):
                if not self.allowed(kw, stored=old):
                    return None  # Migration/continuation cannot re-recognize an owner.
                self.migrate(old)
                old["scope"] = scope  # Items retain the exact original receipt scope.
            else:
                old = {"scope": scope, "owner": "local_owner", "policy_version": POLICY_VERSION,
                       "stage": "research", "obligation": True, "schema_version": 2, "items": {}}
            self.ctx.state.set(key, old)
        return {"context": "[Local research contract] Before final delivery call ai_lab_execute "
                "capability=research_deposit with title, body (or analysis), source_urls, confidence "
                "(null if unreviewed), source_kind=research_analysis. Submit the FULL adopted research "
                "body directly, separately from the brief user-facing summary: at least 800 characters, "
                "Markdown headings ## 事实, ## 分析, ## 启示 with actual newline characters (not literal "
                "backslash-n), substantive sections of at least 20 characters, source URLs in body. "
                "One task supports multiple research items: call once per item, keep its primary source "
                "URL first and stable across corrections. A quality rejection with no durable raw can "
                "be corrected and resubmitted; an immutable saved revision cannot be replaced. "
                "Parent adopts evidence; child "
                "execution receipts are NOT storage receipts. Report research/saved/queued separately; "
                "never claim compiled without Writer verification. Missing handoff remains pending, not done."}

    def pipeline(self):
        with _IMPORT_LOCK:
            return self._pipeline_unlocked()

    def _pipeline_unlocked(self):
        filename = self.config().get("pipeline_module")
        if not filename or not Path(filename).is_absolute():
            raise ValueError("trusted_pipeline_module_not_configured")
        path = Path(filename).resolve(strict=True)
        name = "_ai_lab_deposit_pipeline_" + digest(str(path))[:16]
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise ValueError("invalid_pipeline_module")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(name, None)
                raise
        return sys.modules[name]

    def vault(self):
        value = self.config().get("vault_root")
        if not value or not Path(value).is_absolute():
            raise ValueError("trusted_vault_root_not_configured")
        return Path(value).resolve(strict=True)

    def payload(self, inputs):
        # Fail closed for extra authority-bearing fields and source impersonation.
        if set(inputs) - {"title", "body", "analysis", "source_urls", "confidence", "source_kind"}:
            raise ValueError("unsupported_input_fields")
        title, body = inputs.get("title"), inputs.get("body") or inputs.get("analysis")
        if not isinstance(title, str) or not title.strip() or len(title) > 300:
            raise ValueError("invalid_title")
        if not isinstance(body, str) or not body.strip() or len(body) > 100000:
            raise ValueError("invalid_body")
        from agent.redact import redact_sensitive_text
        material = json.dumps(inputs, ensure_ascii=False)
        if redact_sensitive_text(material, force=True, redact_url_credentials=True) != material:
            raise ValueError("secret_detected_before_projection")
        # Reuse the deterministic Vault intake's extra vendor-token detector.
        if self.pipeline()._research_has_secrets(title + "\n" + body):
            raise ValueError("secret_detected_before_projection")
        if inputs.get("source_kind") != "research_analysis":
            raise ValueError("research_analysis_only_parent_adoption_required")
        urls = inputs.get("source_urls", [])
        if not isinstance(urls, list) or len(urls) > 50:
            raise ValueError("invalid_source_urls")
        for url in urls:
            if not isinstance(url, str) or len(url) > 2048:
                raise ValueError("invalid_source_url")
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("invalid_source_url")
            if any(SENSITIVE_QUERY.fullmatch(name) for name, _ in parse_qsl(parsed.query)):
                raise ValueError("sensitive_or_unknown_source_url")
            if redact_sensitive_text(unquote(url), force=True, redact_url_credentials=True) != unquote(url):
                raise ValueError("secret_source_url")
            import ipaddress
            try:
                addr = ipaddress.ip_address(parsed.hostname)
            except ValueError:
                if "." not in parsed.hostname or parsed.hostname.endswith((".local", ".internal", ".localhost")):
                    raise ValueError("nonpublic_source_url")
            else:
                if not addr.is_global:
                    raise ValueError("nonpublic_source_url")
        confidence = inputs.get("confidence")
        if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                                       or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("invalid_confidence")
        return {"title": title, "body": body, "source_urls": urls,
                "confidence": confidence, "source_kind": "research_analysis"}

    def materialize(self, record):
        payload = dict(record["payload"])
        if "body" not in payload:
            ref = record["body_ref"]
            raw = self.vault() / ref["raw_path"]
            content = raw.read_bytes()
            if hashlib.sha256(content).hexdigest() != ref["sha256"]:
                raise ValueError("source_hash_changed")
            body = content[ref["offset"]:ref["offset"] + ref["length"]]
            if hashlib.sha256(body).hexdigest() != ref["body_sha256"]:
                raise ValueError("body_hash_changed")
            payload["body"] = body.decode()
        return payload

    def compact(self, record, payload):
        """After verified persistence keep hashes + raw reference, not a second body."""
        receipt = record["receipt"]
        root = self.vault()
        raw = Path(receipt["raw_path"])
        raw = raw if raw.is_absolute() else root / raw
        content = raw.read_bytes()
        body = payload["body"].encode()
        if not content.endswith(body + b"\n"):
            raise ValueError("pipeline_body_boundary_changed")
        record["body_ref"] = {"raw_path": raw.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(content).hexdigest(), "offset": len(content) - len(body) - 1,
            "length": len(body), "body_sha256": hashlib.sha256(body).hexdigest()}
        record["payload"] = {k: v for k, v in payload.items() if k != "body"}

    def verify_receipt(self, record):
        receipt = record.get("receipt") or {}
        try:
            payload = self.materialize(record)
        except (OSError, ValueError, KeyError, TypeError):
            return False
        if digest(payload) != record.get("source_revision"):
            return False
        if receipt.get("binding") != {"scope": record["scope"], "policy_version": POLICY_VERSION,
                                      "source_revision": record["source_revision"]}:
            return False
        try:
            root = self.vault()
            raw = Path(receipt["raw_path"])
            unresolved = raw if raw.is_absolute() else root / raw
            if any(p.is_symlink() for p in (unresolved, *unresolved.parents)):
                return False
            path = unresolved.resolve(strict=True)
            if root not in path.parents or (root / "raw") not in path.parents:
                return False
            expected = receipt.get("sha256") or receipt.get("hash") or receipt.get("content_sha256")
            content = path.read_bytes()
            if path.stat().st_nlink != 1 or not expected or hashlib.sha256(content).hexdigest() != expected:
                return False
            import yaml
            metadata = yaml.safe_load(content.decode().split("---", 2)[1])
            expected_metadata = {"task_id": record["scope"]["task_id"], "source_revision": record["source_revision"],
                "policy_version": POLICY_VERSION, "profile": "default", "owner": "local_owner",
                "evidence_status": "research_analysis", "body_sha256": hashlib.sha256(payload["body"].encode()).hexdigest()}
            if any(metadata.get(k) != v for k, v in expected_metadata.items()):
                return False
            if receipt.get("storage_verified") is not True:
                return False
            eligible = receipt.get("compile_eligible") is True
            if eligible:
                if receipt.get("admission_state") != "admitted" or receipt.get("manifest_registered") is not True:
                    return False
                records = json.loads((root / "raw" / "_manifest.json").read_text())
                relative = path.relative_to(root).as_posix()
                if not any(relative in row.get("files", []) and row.get("content_sha256") == expected
                           and row.get("compile_eligible") is True and row.get("admission_state") == "admitted"
                           for row in records):
                    return False
            elif receipt.get("admission_state") != "pending":
                return False
            return True
        except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError):
            return False

    def _write(self, key, record, *, explicit, task=None):
        try:
            if not self.enabled():
                return {"success": False, "complete": False, "stage": "blocked", "error": "policy_denied"}
            payload = self.materialize(record)
            confidence = payload["confidence"]
            previous = record.get("receipt") or {}
            if confidence is None and previous.get("raw_path"):
                raw = Path(previous["raw_path"])
                raw = raw if raw.is_absolute() else self.vault() / raw
                content = raw.read_bytes()
                if hashlib.sha256(content).hexdigest() != previous.get("sha256"):
                    raise ValueError("source_hash_changed")
                import yaml
                metadata = yaml.safe_load(content.decode().split("---", 2)[1])
                if metadata.get("confidence") == 0:
                    confidence = 0  # Legacy immutable null-as-zero raw, repair only.
            receipt = self.pipeline().deposit_research(
                self.vault(), task_id=record["scope"]["task_id"],
                source_revision=record["source_revision"], title=payload["title"], body=payload["body"],
                source_urls=payload["source_urls"], confidence=confidence,
                policy_version=POLICY_VERSION, profile="default", owner="local_owner",
                evidence_status="research_analysis", no_save=False)
            record["receipt"] = dict(receipt, binding={"scope": record["scope"],
                "policy_version": POLICY_VERSION, "source_revision": record["source_revision"]},
                storage_scope=STORAGE_SCOPE)
            if receipt.get("reason") == "quality_rejected":
                reasons = []
                _, _, failed, gate_reason = self.pipeline().evaluate_judge_gate(
                    "⭐", body_text=payload["body"], source_url="\n".join(payload["source_urls"]))
                if failed:
                    reasons.append(gate_reason)
                if not self.pipeline()._research_structure_valid(payload["body"]):
                    reasons.append("missing_substantive_markdown_sections_or_actual_newlines")
                if not all(url in payload["body"] for url in payload["source_urls"]):
                    reasons.append("source_urls_missing_from_body")
                if payload["body"].lstrip().startswith("---"):
                    reasons.append("body_must_not_start_with_frontmatter")
                record.update(stage="pending", reason="quality_rejected",
                    quality_reason="; ".join(reasons) or receipt.get("quality_reason"),
                    required_structure={"headings": ["## 事实", "## 分析", "## 启示"],
                        "actual_newlines": True, "min_section_chars": 20,
                        "source_urls_in_body": True, "authoritative_source": True,
                        "objective_evidence": True}, minchars=800)
                self.ctx.state.set(key, task if task is not None else record)
                return self.status(record)
            if not self.verify_receipt(record):
                raise ValueError(receipt.get("reason") or "fixed_version_readback_failed")
            self.compact(record, payload)
            record["stage"] = "queued" if receipt.get("compile_eligible") else "saved"
            record["explicit_receipt"] = explicit
            for field in ("reason", "quality_reason", "required_structure", "minchars"):
                record.pop(field, None)
        except Exception as exc:
            record["stage"] = "pending"
            record["reason"] = type(exc).__name__ + ": " + str(exc)[:200]
        self.ctx.state.set(key, task if task is not None else record)
        return self.status(record)

    def status(self, record):
        if "items" in record:
            items = [{"item_id": identity, **self.status(item)} for identity, item in record["items"].items()]
            valid = bool(items) and all(item["success"] for item in items)
            complete = bool(items) and all(item["complete"] for item in items)
            stage = ("queued" if all(item["stage"] == "queued" for item in items) else "saved") if complete else "pending"
            # Preserve the single-item response shape for existing callers.
            result = dict(items[0]) if len(items) == 1 else {}
            result.update(success=valid, complete=complete, task_complete=complete,
                stage=stage if len(items) != 1 else items[0]["stage"],
                storage_scope=STORAGE_SCOPE, wiki_compiled=False,
                reason=record.get("reason") or (None if complete else "all_known_items_require_explicit_verified_receipts"),
                items=items, total=len(items))
            if len(items) == 1 and items[0].get("reason"):
                result["reason"] = items[0]["reason"]
            return result
        if record.get("requested_revision", record.get("source_revision")) != record.get("source_revision"):
            return {"success": False, "complete": False, "stage": "pending", "receipt": None,
                    "reason": "source_revision_conflict", "storage_scope": STORAGE_SCOPE, "wiki_compiled": False}
        valid = self.verify_receipt(record) if record.get("receipt") else False
        stage = record.get("stage", "pending") if valid or not record.get("receipt") else "pending"
        complete = valid and record.get("explicit_receipt") is True
        return {"success": valid, "complete": complete, "stage": stage,
                "storage_scope": STORAGE_SCOPE,
                **{k: record[k] for k in ("quality_reason", "required_structure", "minchars") if k in record},
                "admission_state": (record.get("receipt") or {}).get("admission_state"),
                "reason": record.get("reason") or (None if complete else "missing_explicit_verified_receipt"),
                "receipt": record.get("receipt") if valid else None,
                "wiki_compiled": False}

    def execute(self, inputs, **kw):
        try:
            kw = dict(kw, **self.tool_scope(kw))
            if inputs.get("action") in {"status", "recover"}:
                return self.recover(inputs, **kw)
            scope = self.scope(kw)
            key = self.key(scope)
            with self.lock(key):
                record = self.ctx.state.get(key, {})
                if record.get("veto"):
                    return {"success": False, "stage": "blocked", "error": "no_save"}
                if not self.enabled():
                    return {"success": False, "stage": "blocked", "error": "policy_denied"}
                if record.get("control") and record.get("scope") == scope and self.allowed(kw, stored=record):
                    return {"success": False, "stage": "blocked", "error": "research_task_association_required"}
                if not record.get("obligation") or record.get("scope") != scope or not self.allowed(kw, stored=record):
                    return {"success": False, "stage": "blocked", "error": "no_authorized_task_scope"}
                payload = self.payload(inputs)
                revision = digest(payload)
                self.migrate(record)
                identity = self.item_id(payload)
                item = record["items"].get(identity)
                if item and item.get("source_revision") != revision:
                    receipt = item.get("receipt") or {}
                    # Only a definite pre-write quality rejection may be corrected.
                    # Even a failed manifest receipt can point to immutable durable raw.
                    rejected = receipt.get("reason") == "quality_rejected"
                    if not rejected or receipt.get("raw_path") or item.get("body_ref"):
                        item["requested_revision"] = revision
                        self.ctx.state.set(key, record)
                        return {"success": False, "complete": False, "stage": "blocked",
                                "error": "source_revision_conflict", "item_id": identity}
                    item = None
                if item:
                    item.pop("requested_revision", None)  # Explicit identical content acknowledges this revision.
                if item and self.verify_receipt(item):
                    item.update(explicit_receipt=True, explicit_attempt=True)
                else:
                    if item is None:
                        if identity not in record["items"] and len(record["items"]) >= 20:
                            return {"success": False, "complete": False, "stage": "blocked", "error": "task_item_limit_20"}
                        item = {"scope": scope, "owner": record["owner"], "policy_version": record["policy_version"],
                                "item_id": identity, "payload": payload, "source_revision": revision, "stage": "pending"}
                        record["items"][identity] = item
                    item["explicit_attempt"] = True
                    self.ctx.state.set(key, record)  # recovery intent before Vault write
                    self._write(key, item, explicit=True, task=record)
                self.ctx.state.set(key, record)
                result = self.status(item)
                return dict(result, item_id=identity, complete=self.status(record)["complete"],
                            task_complete=self.status(record)["complete"], item_complete=result["complete"])
        except Exception as exc:
            return {"success": False, "stage": "blocked", "error": str(exc)}

    def recover(self, inputs, **kw):
        """Bounded compensation of one known projection; no scan or scheduler.

        A trusted owner callback may target known IDs (e.g. the existing Writer
        cron). Tool callers without an owner surface can only use their exact
        canonical host scope. At most three recovery attempts per item lifetime.
        """
        if set(inputs) - {"action", "session_id", "turn_id", "task_id", "limit", "item_id", "cursor"}:
            raise ValueError("unsupported_recovery_fields")
        read_only = inputs["action"] == "status"
        if not read_only and not self.enabled():
            return {"success": False, "stage": "blocked", "error": "policy_denied"}
        current_scope = self.scope(kw)
        current = self.ctx.state.get(self.key(current_scope), {}) if all(current_scope.values()) else {}
        control_authorized = self.allowed(kw, read_only=read_only) or (current.get("scope") == current_scope
            and (current.get("control") or current.get("obligation")) and self.allowed(kw, stored=current, read_only=read_only))
        has_target = any(inputs.get(k) for k in ("session_id", "turn_id", "task_id"))
        if not has_target and (current.get("control") or not current.get("obligation")):
            if not control_authorized:
                return {"success": False, "stage": "blocked", "error": "local_owner_control_required"}
            return self.pending_projection_batch(inputs, **kw)
        scope = self.scope(inputs) if any(inputs.get(k) for k in ("session_id", "turn_id", "task_id")) else self.scope(kw)
        key = self.key(scope)
        with self.lock(key):
            record = self.ctx.state.get(key, {})
            if record.get("veto"):
                return {"success": False, "stage": "blocked", "error": "no_save"}
            if (not record.get("obligation") or record.get("scope") != scope
                    or not self.allowed(kw, stored=record, read_only=read_only)
                    or not control_authorized):
                return {"success": False, "stage": "blocked", "error": "no_authorized_task_scope"}
            self.migrate(record)  # Status migration stays in memory.
            identity = inputs.get("item_id")
            if identity is not None and identity not in record["items"]:
                return {"success": False, "complete": False, "error": "unknown_item_id", "stage": "blocked"}
            if inputs["action"] == "status":
                return self.status(record["items"][identity] if identity else record)
            targets = [record["items"][identity]] if identity else list(record["items"].values())
            attempts = 0
            exhausted = False
            for item in sorted(targets, key=lambda item: item.get("recovery_attempts", 0)):
                if self.verify_receipt(item):
                    continue
                if self.recovery_blocker(item):
                    exhausted = True
                    continue
                if attempts >= 3:
                    break
                item["recovery_attempts"] = item.get("recovery_attempts", 0) + 1
                self.ctx.state.set(key, record)
                self._write(key, item, explicit=item.get("explicit_attempt", False), task=record)
                attempts += 1
            result = self.status(record["items"][identity] if identity else record)
            if exhausted or not targets:
                result["error"] = "recovery_exhausted_or_missing_payload"
            return result

    def recovery_blocker(self, item):
        if self.verify_receipt(item):
            return "explicit_acknowledgement_required"
        if item.get("requested_revision", item.get("source_revision")) != item.get("source_revision"):
            return "source_revision_conflict"
        if (item.get("receipt") or {}).get("reason") == "quality_rejected":
            return "explicit_quality_correction_required"
        if not item.get("payload"):
            return "explicit_handoff_required"
        if item.get("recovery_attempts", 0) >= 3:
            return "recovery_exhausted"
        return None

    def pending_projection_batch(self, inputs, **kw):
        """Bounded pages of native projections; no session content or new index."""
        limit = inputs.get("limit", 3)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("limit_must_be_1_to_20")
        cursor = inputs.get("cursor", "")
        if not isinstance(cursor, str) or len(cursor) > 200:
            raise ValueError("invalid_cursor")
        read_only = inputs["action"] == "status"
        if not read_only:
            if cursor:
                raise ValueError("cursor_status_only")
            if not self.enabled():
                return {"success": False, "stage": "blocked", "error": "policy_denied"}
            limit = min(limit, 3)
        from hermes_cli.plugins import _locked_plugin_state
        with _locked_plugin_state(self.ctx.state.path):
            snapshot = self.ctx.state._read_unlocked()
        pending = []
        # ponytail: native state quota bounds this scan; no independent index.
        for key, record in sorted(snapshot.items()):
            if not key.startswith("research:") or not isinstance(record, dict):
                continue
            if record.get("obligation") and not record.get("veto") and self.allowed(kw, stored=record, read_only=read_only):
                self.migrate(record)
                for identity, item in sorted((record["items"] or {"": record}).items()):
                    status = self.status(item)
                    if not status["complete"]:
                        blocker = self.recovery_blocker(item)
                        pending.append({"scope": record["scope"], "item_id": identity or None,
                            "cursor": key + "/" + identity, "stage": status["stage"],
                            "reason": status["reason"], "recoverable": blocker is None,
                            "recovery_blocked_reason": blocker,
                            "recovery_attempts": item.get("recovery_attempts", 0)})
        actionable = [item for item in pending if item["recoverable"]]
        candidates = ([item for item in pending if item["cursor"] > cursor] if read_only else
                      sorted(actionable, key=lambda item: (item["recovery_attempts"], item["cursor"])))
        selected = candidates[:limit]
        if not read_only:
            for item in selected:
                item["result"] = self.recover(dict(action="recover", item_id=item["item_id"], **item["scope"]), **kw)
        success = read_only or all(item["result"].get("success") for item in selected)
        return {"success": success, "storage_scope": STORAGE_SCOPE, "pending": selected,
                "total": len(pending), "actionable_total": len(actionable),
                "blocked_total": len(pending) - len(actionable), "returned": len(selected),
                "has_more": len(candidates) > len(selected),
                "next_cursor": selected[-1]["cursor"] if read_only and len(candidates) > len(selected) else None}

    def verify_completion(self, response_text="", **kw):
        """Generic lifecycle adapter: returns status + response, never swallows answer.

        Pass canonical session_id/turn_id/task_id. No writes, even when the
        host omits failed/interrupted flags or invokes both transform and post.
        """
        try:
            scope = self.scope(kw)
            key = self.key(scope)
            with self.lock(key):
                record = self.ctx.state.get(key, {})
                if not record or record.get("veto") or not record.get("obligation"):
                    return {"complete": not record, "stage": record.get("stage", "not_applicable"), "response_text": response_text}
                if record.get("scope") != scope or not self.allowed(kw, stored=record):
                    return {"complete": False, "stage": "blocked", "response_text": response_text + "\n\n[研究沉淀 blocked：任务或策略不匹配；未进 Wiki。]"}
                # Observational only: native finalizer does not reliably supply failed.
                # Explicit deposit/recover owns all persistence and compensation.
                self.migrate(record)
                result = self.status(record)
                note = ("已保存并排队；尚未编译 Wiki。" if result["stage"] == "queued" else
                        "已保存为待审研究；未进 Wiki。" if result["stage"] == "saved" else "保存待恢复；未进 Wiki。")
                if not result["complete"]:
                    note += " 缺显式受控交接回执，任务仍 pending。"
                return dict(result, response_text=response_text + "\n\n[研究沉淀 " + result["stage"] + "：" + note + "]")
        except Exception as exc:
            return {"complete": False, "stage": "blocked", "error": str(exc),
                    "response_text": response_text + "\n\n[研究沉淀 blocked：无法核验保存；未进 Wiki。]"}

    def post(self, assistant_response="", **kw):
        if NO_SAVE.search(kw.get("user_message") or ""):
            self.pre(**kw)
        return self.verify_completion(assistant_response, **kw)

    def transform(self, response_text="", **kw):
        # Never guess the latest task in a session. Host adapter must provide IDs.
        if not kw.get("task_id") or not kw.get("turn_id"):
            return None
        return self.verify_completion(response_text, **kw)["response_text"]

    def install(self):
        self.ctx.register_hook("pre_llm_call", self.pre)
        self.ctx.register_hook("post_llm_call", self.post)
        self.ctx.register_hook("on_session_end", self.session_end)

    def session_end(self, **kw):
        """Record interrupted/failed obligations without inventing an answer."""
        try:
            scope = self.scope(kw)
            key = self.key(scope)
            with self.lock(key):
                record = self.ctx.state.get(key, {})
                if (record.get("obligation") and record.get("scope") == scope and not record.get("veto")
                        and self.allowed(kw, stored=record)):
                    if kw.get("interrupted") or kw.get("failed") or not kw.get("completed", True):
                        record["reason"] = "interrupted_or_failed"
                        self.migrate(record)
                        if not self.status(record)["complete"]:
                            record["stage"] = "pending"
                        self.ctx.state.set(key, record)
                    return self.status(record)
        except Exception as exc:
            return {"success": False, "stage": "blocked", "error": str(exc)}
