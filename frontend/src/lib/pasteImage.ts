/** Getting a picture off the clipboard, for uploading pictures copied from an AI chat. */

const EXTENSIONS: Record<string, string> = { "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif" };

/** Re-encode formats the server doesn't take (e.g. TIFF or HEIC from some apps) as PNG. */
async function toPng(blob: Blob): Promise<Blob | null> {
  try {
    const bitmap = await createImageBitmap(blob);
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0);
    return await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  } catch {
    return null;
  }
}

/** A named file the upload endpoint accepts, or null if `blob` isn't a usable picture. */
export async function pictureFile(blob: Blob, name = "pasted-picture"): Promise<File | null> {
  if (!blob.type.startsWith("image/")) return null;
  let data: Blob | null = blob;
  if (!EXTENSIONS[blob.type]) data = await toPng(blob);
  if (!data) return null;
  return new File([data], `${name}.${EXTENSIONS[data.type] ?? "png"}`, { type: data.type || "image/png" });
}

/** The first picture in pasted or dropped data. */
export function pictureFromData(data: DataTransfer | null): Blob | null {
  if (!data) return null;
  for (const file of Array.from(data.files)) if (file.type.startsWith("image/")) return file;
  for (const item of Array.from(data.items)) {
    if (item.kind === "file" && item.type.startsWith("image/")) return item.getAsFile();
  }
  return null;
}

/**
 * Read a picture straight from the clipboard. That API only exists on HTTPS or localhost
 * (the app is usually opened over plain http), and the browser may refuse; both give
 * "unavailable" so the caller can fall back to a paste box. null = clipboard has no picture.
 */
export async function readClipboardPicture(): Promise<Blob | null | "unavailable"> {
  if (!window.isSecureContext || !navigator.clipboard?.read) return "unavailable";
  try {
    for (const item of await navigator.clipboard.read()) {
      const type = item.types.find((t) => t.startsWith("image/"));
      if (type) return await item.getType(type);
    }
    return null;
  } catch {
    return "unavailable";
  }
}
