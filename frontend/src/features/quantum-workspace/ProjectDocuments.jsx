import { FileText, Link2, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { platformApi } from "../../services/platformApi";

const emptyDraft = { title: "", content: "", status: "DRAFT", source_refs: [], tags: [] };
const lines = (value) => String(value || "").split("\n").map((item) => item.trim()).filter(Boolean);

export function ProjectDocuments({ projectId, onRevisionChange }) {
  const [payload, setPayload] = useState({ process_revision: 0, documents: [], document_structure: [], graph: { backlinks: {}, broken_links: [] } });
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState(emptyDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    const value = await platformApi.listProjectDocuments(projectId);
    setPayload(value);
    const selected = value.documents.find((item) => item.id === selectedId) || value.documents[0];
    if (selected) {
      setSelectedId(selected.id);
      setDraft({
        title: selected.title || "未命名文档",
        content: selected.content || "",
        status: String(selected.status || "DRAFT").toUpperCase(),
        source_refs: selected.source_refs || [],
        tags: selected.tags || [],
      });
    }
  };
  useEffect(() => { load().catch((reason) => setError(reason.message)); }, [projectId]);
  const select = (document) => {
    setSelectedId(document.id);
    setDraft({
      title: document.title || "未命名文档",
      content: document.content || "",
      status: String(document.status || "DRAFT").toUpperCase(),
      source_refs: document.source_refs || [],
      tags: document.tags || [],
    });
  };
  const create = () => {
    const id = `doc-${crypto.randomUUID()}`;
    setSelectedId(id);
    setDraft({ ...emptyDraft, title: "新项目文档", content: "# 新项目文档\n\n" });
  };
  const save = async () => {
    setBusy(true); setError("");
    try {
      const result = await platformApi.saveProjectDocument(projectId, selectedId, {
        expected_revision: payload.process_revision,
        ...draft,
      });
      await load();
      onRevisionChange?.(result.process_revision);
    } catch (reason) {
      setError(reason.status === 409 ? "项目版本已变化，请刷新后再保存。" : reason.message);
    } finally { setBusy(false); }
  };
  const wikilinks = useMemo(
    () => [...draft.content.matchAll(/\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]/g)].map((match) => match[1]),
    [draft.content],
  );
  const backlinks = payload.graph?.backlinks?.[selectedId] || [];
  const selectedDocument = payload.documents.find((item) => item.id === selectedId);
  const masterReadOnly = selectedDocument?.document_type === "PROJECT_MASTER";
  return <section className="qw-documents">
    <aside>
      <div><span className="qw-eyebrow">Project documents</span><button type="button" onClick={create}>新建</button></div>
      <small>Obsidian-compatible · readable projection</small>
      {payload.document_structure.map((folder) => {
        const folderDocuments = payload.documents.filter((document) => document.category === folder.key);
        return <section className="qw-document-folder" key={folder.key}><header><strong>{folder.name}</strong><small>{folder.purpose}</small></header>{folderDocuments.map((document) => <button type="button" key={document.id} className={selectedId === document.id ? "active" : ""} onClick={() => select(document)}><FileText size={15} /><span><strong>{document.title}</strong><small>{document.document_type === "PROJECT_MASTER" ? "唯一参照 · " : ""}{document.status || "DRAFT"} · r{document.revision || 1}</small></span></button>)}</section>;
      })}
      {!payload.document_structure.length && payload.documents.map((document) => <button type="button" key={document.id} className={selectedId === document.id ? "active" : ""} onClick={() => select(document)}><FileText size={15} /><span><strong>{document.title}</strong><small>{document.status || "DRAFT"} · r{document.revision || 1}</small></span></button>)}
      {!payload.documents.length && <p>蓝图尚未生成文档，可新建后编辑。</p>}
    </aside>
    <div className="qw-document-editor">
      <header>
        <input aria-label="文档标题" disabled={masterReadOnly} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
        <select aria-label="文档状态" disabled={masterReadOnly} value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}>
          <option value="DRAFT">草稿</option><option value="PUBLISHED">发布投影</option><option value="ARCHIVED">归档</option>
        </select>
        <button className="qw-button primary" type="button" disabled={!selectedId || busy || masterReadOnly} onClick={save}><Save size={14} />{masterReadOnly ? "只读顶设" : busy ? "保存中…" : "保存文档"}</button>
      </header>
      {error && <p className="qw-error" role="alert">{error}</p>}
      {masterReadOnly && <p className="qw-document-readonly">顶设由已确认的项目意图自动生成；请通过项目变更提案修改。</p>}
      <label>Source refs（每行一个；发布态必填且服务端验证）<textarea aria-label="文档来源" disabled={masterReadOnly} value={draft.source_refs.join("\n")} onChange={(event) => setDraft({ ...draft, source_refs: lines(event.target.value) })} /></label>
      <label>Tags（每行一个）<textarea aria-label="文档标签" disabled={masterReadOnly} value={draft.tags.join("\n")} onChange={(event) => setDraft({ ...draft, tags: lines(event.target.value) })} /></label>
      <textarea className="qw-document-body" aria-label="Markdown 文档正文" readOnly={masterReadOnly} value={draft.content} onChange={(event) => setDraft({ ...draft, content: event.target.value })} placeholder="使用 Markdown、[[wikilinks]] 与 Obsidian callouts 编辑项目文档…" />
      <section className="qw-document-links" aria-label="文档链接诊断">
        <strong><Link2 size={14} />链接</strong>
        <span>出链：{wikilinks.length ? wikilinks.join("、") : "无"}</span>
        <span>反链：{backlinks.length ? backlinks.join("、") : "无"}</span>
        {!!payload.graph?.broken_links?.filter((item) => item.source_document_id === selectedId).length && <span className="qw-error">存在未解析 wikilink</span>}
      </section>
    </div>
  </section>;
}
