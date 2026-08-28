import { FileText, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { platformApi } from "../../services/platformApi";

export function ProjectDocuments({ projectId, onRevisionChange }) {
  const [payload, setPayload] = useState({ process_revision: 0, documents: [] });
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState({ title: "", content: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    const value = await platformApi.listProjectDocuments(projectId);
    setPayload(value);
    const selected = value.documents.find((item) => item.id === selectedId) || value.documents[0];
    if (selected) { setSelectedId(selected.id); setDraft({ title: selected.title || "未命名文档", content: selected.content || "" }); }
  };
  useEffect(() => { load().catch((reason) => setError(reason.message)); }, [projectId]);
  const select = (document) => { setSelectedId(document.id); setDraft({ title: document.title || "未命名文档", content: document.content || "" }); };
  const create = () => { const id = `doc-${crypto.randomUUID()}`; setSelectedId(id); setDraft({ title: "新项目文档", content: "# 新项目文档\n\n" }); };
  const save = async () => {
    setBusy(true); setError("");
    try {
      const result = await platformApi.saveProjectDocument(projectId, selectedId, { expected_revision: payload.process_revision, ...draft });
      setPayload((current) => ({ process_revision: result.process_revision, documents: [...current.documents.filter((item) => item.id !== selectedId), result.document] }));
      onRevisionChange?.(result.process_revision);
    } catch (reason) { setError(reason.status === 409 ? "项目版本已变化，请刷新后再保存。" : reason.message); } finally { setBusy(false); }
  };
  return <section className="qw-documents">
    <aside><div><span className="qw-eyebrow">Project documents</span><button type="button" onClick={create}>新建</button></div>{payload.documents.map((document) => <button type="button" key={document.id} className={selectedId === document.id ? "active" : ""} onClick={() => select(document)}><FileText size={15} /><span><strong>{document.title}</strong><small>{document.status || "draft"}</small></span></button>)}{!payload.documents.length && <p>蓝图尚未生成文档，可新建后编辑。</p>}</aside>
    <div className="qw-document-editor"><header><input aria-label="文档标题" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /><button className="qw-button primary" type="button" disabled={!selectedId || busy} onClick={save}><Save size={14} />{busy ? "保存中…" : "保存文档"}</button></header>{error && <p className="qw-error" role="alert">{error}</p>}<textarea aria-label="Markdown 文档正文" value={draft.content} onChange={(event) => setDraft({ ...draft, content: event.target.value })} placeholder="使用 Markdown 编辑项目文档…" /></div>
  </section>;
}
