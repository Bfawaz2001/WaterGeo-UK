export async function verifiedJson<T>(response: Response, evidence: { bytes?: number; sha256: string }): Promise<T> {
  if (!response.ok || Number(response.headers.get("content-length")) > 10 * 1024 * 1024) throw new Error("Asset unavailable");
  const reader = response.body?.getReader();
  if (!reader) throw new Error("Missing asset stream");
  const chunks: Uint8Array[] = []; let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > (evidence.bytes ?? 10 * 1024 * 1024) || size > 10 * 1024 * 1024) { await reader.cancel(); throw new Error("Oversized asset"); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), (n) => n.toString(16).padStart(2, "0")).join("");
  if ((evidence.bytes !== undefined && size !== evidence.bytes) || hash !== evidence.sha256) throw new Error("Bundle checksum mismatch");
  return JSON.parse(new TextDecoder().decode(bytes)) as T;
}
