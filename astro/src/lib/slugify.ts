export function slugify(text: string, id: string): string {
  const slug = text
    .toLowerCase()
    .replace(/['']/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .substring(0, 80)
    .replace(/-$/, "");
  const shortId = id.substring(0, 8);
  return slug ? `${slug}-${shortId}` : shortId;
}
