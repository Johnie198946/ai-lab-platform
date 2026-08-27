export function splitSseFrames(buffer, flush = false) {
  const normalized = String(buffer || "").replace(/\r\n/g, "\n");
  const chunks = normalized.split("\n\n");
  let remainder = chunks.pop() ?? "";
  if (flush && remainder.trim()) {
    chunks.push(remainder);
    remainder = "";
  }
  return { frames: chunks, remainder };
}

export function parseSseFrame(frame) {
  const data = String(frame || "")
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .join("\n");
  if (!data) return null;
  try {
    return JSON.parse(data);
  } catch {
    return null;
  }
}
