import { InvestigationMemory, mergeEntities } from "../context/memory.js";
import { callQptmTool, type QptmToolResult } from "../mcp/hub.js";

function isResidueToken(token: string): boolean {
  return /^[STYKR]\d{2,5}$/i.test(token.trim());
}

export function applyResolvedIdentity(
  memory: InvestigationMemory,
  result: Pick<QptmToolResult, "resolved" | "data">,
): void {
  const blob =
    result.resolved && typeof result.resolved === "object"
      ? result.resolved
      : result.data && typeof result.data === "object"
        ? (result.data as Record<string, unknown>)
        : null;
  if (!blob) return;

  const gene = blob.gene != null ? String(blob.gene).trim() : "";
  const uniprot = blob.uniprot_ac != null ? String(blob.uniprot_ac).trim().toUpperCase() : "";
  const positionRaw = blob.position;
  const position =
    typeof positionRaw === "number"
      ? positionRaw
      : positionRaw != null && String(positionRaw).trim()
        ? Number(positionRaw)
        : NaN;
  const ptm = blob.ptm_type != null ? String(blob.ptm_type) : "";

  const patch: Parameters<typeof mergeEntities>[1] = {};
  if (gene && !isResidueToken(gene)) {
    // Do not clobber a good gene with a worse one unless we also gained UniProt.
    if (!memory.gene || isResidueToken(memory.gene) || uniprot) {
      patch.gene = gene;
    }
  }
  if (uniprot) patch.uniprot_ac = uniprot;
  if (Number.isFinite(position) && position > 0) patch.position = position;
  if (ptm) patch.ptm_type = ptm;
  mergeEntities(memory, patch);
}

/** Resolve gene/site → UniProt once per turn before batch tool calls. */
export async function resolveSessionTarget(
  memory: InvestigationMemory,
  query: string,
): Promise<QptmToolResult> {
  if (memory.uniprot_ac && memory.gene && !isResidueToken(memory.gene)) {
    return {
      success: true,
      summary: `Target ${memory.gene} UniProt=${memory.uniprot_ac}${memory.position ? ` site=${memory.position}` : ""}`,
      data: {
        gene: memory.gene,
        uniprot_ac: memory.uniprot_ac,
        position: memory.position,
        ptm_type: memory.ptm_type,
      },
      error_kind: null,
      resolved: {
        gene: memory.gene,
        uniprot_ac: memory.uniprot_ac,
        position: memory.position,
        ptm_type: memory.ptm_type,
      },
    };
  }

  const result = await callQptmTool("qptm_resolve", {
    query,
    gene: memory.gene && !isResidueToken(memory.gene) ? memory.gene : "",
    position: memory.position || 0,
    uniprot_ac: memory.uniprot_ac || "",
    ptm_type: memory.ptm_type || "",
  });
  applyResolvedIdentity(memory, result);
  return result;
}

export function invokeArgumentsJson(memory: InvestigationMemory, query: string): string {
  return JSON.stringify({
    gene: memory.gene && !isResidueToken(memory.gene) ? memory.gene : "",
    position: memory.position || 0,
    uniprot_ac: memory.uniprot_ac || "",
    ptm_type: memory.ptm_type || "phosphorylation",
    query,
  });
}
