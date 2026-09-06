// Managed-section handling. Pure; unit-tested with node.

export const SECTION_START = "%% polar:start %%";
export const SECTION_END = "%% polar:end %%";

/**
 * Replace the managed section in `content`, or append one if none exists.
 * Everything the user wrote outside the markers is preserved byte-for-byte.
 */
export function mergeManagedSection(content: string, section: string): string {
  const startIdx = content.indexOf(SECTION_START);
  const endIdx = content.indexOf(SECTION_END, startIdx + 1);
  if (startIdx !== -1 && endIdx !== -1) {
    return content.slice(0, startIdx) + section + content.slice(endIdx + SECTION_END.length);
  }
  const body = content.trimEnd();
  return body ? `${body}\n\n${section}\n` : `${section}\n`;
}

export function wrapSection(lines: string[]): string {
  return [SECTION_START, ...lines, SECTION_END].join("\n");
}

/** Render frontmatter for a brand-new note. Strings are quoted, numbers bare. */
export function renderFrontmatter(values: Record<string, string | number | null>): string {
  const lines = Object.entries(values)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => (typeof v === "number" ? `${k}: ${v}` : `${k}: "${String(v).replace(/"/g, '\\"')}"`));
  return ["---", ...lines, "---"].join("\n");
}
