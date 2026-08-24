const text = (value) => value === null || value === undefined ? "" : String(value).trim();

const PRESENTATIONS = {
  markdown: { type: "markdown", label: "Markdown", tone: "blue" },
  word: { type: "word", label: "Word 文档", tone: "indigo" },
  chart: { type: "chart", label: "数据图表", tone: "cyan" },
  topology: { type: "topology", label: "拓扑图", tone: "violet" },
  flowchart: { type: "flowchart", label: "流程图", tone: "amber" },
  image: { type: "image", label: "图像", tone: "green" },
  data: { type: "data", label: "结构化数据", tone: "slate" },
  file: { type: "file", label: "文件", tone: "slate" },
};

const TYPE_ALIASES = {
  md: "markdown", markdown: "markdown", txt: "markdown", "text/markdown": "markdown",
  doc: "word", docx: "word", word: "word", document: "word",
  chart: "chart", graph: "chart", plot: "chart", analytics: "chart",
  topology: "topology", network: "topology",
  flow: "flowchart", flowchart: "flowchart", process: "flowchart",
  png: "image", jpg: "image", jpeg: "image", webp: "image", gif: "image", svg: "image",
  json: "data", csv: "data", yaml: "data", yml: "data",
};

const typeFromHint = (hint) => {
  const normalized = text(hint).toLowerCase().replace(/^\./, "");
  if (!normalized) return "";
  if (TYPE_ALIASES[normalized]) return TYPE_ALIASES[normalized];
  return Object.entries(TYPE_ALIASES).find(([alias]) => normalized.includes(alias))?.[1] || "";
};

export function artifactPresentation(artifact = {}) {
  const metadata = artifact?.metadata && typeof artifact.metadata === "object" ? artifact.metadata : {};
  const path = text(artifact.relative_path || artifact.published_path);
  const filename = path.split(/[\\/]/).pop()?.split(/[?#]/)[0] || "";
  const pathExtension = filename.includes(".") && !filename.endsWith(".") ? filename.split(".").pop().toLowerCase() : "";
  const extension = text(metadata.extension || artifact.extension) || pathExtension;
  const explicit = [metadata.render_type, metadata.artifact_type, metadata.format, artifact.artifact_type, artifact.mime_type]
    .map(typeFromHint).find(Boolean);
  const type = explicit || typeFromHint(extension) || "file";
  return { ...PRESENTATIONS[type], extension: extension || null };
}

export function parseStructuredArtifact(content) {
  if (typeof content !== "string" || !content.trim() || content.length > 512_000) return null;
  try {
    const parsed = JSON.parse(content);
    return parsed && !Array.isArray(parsed) && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}
