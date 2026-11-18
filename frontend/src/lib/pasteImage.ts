/** Getting a picture off the clipboard, for uploading pictures copied from an AI chat. */

const EXTENSIONS: Record<string, string> = { "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif" };

/** The server's upload limit is 15 MB; stay under it with room to spare. */
const MAX_BYTES = 14 * 1024 * 1024;
/** Longest side of a re-encoded picture: plenty for the app's pictures, and keeps files small. */
const MAX_SIDE = 2400;

function encode(canvas: HTMLCanvasElement, type: string, quality?: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

/**
 * Re-encode a picture the server can't take as is: a format it doesn't accept (e.g. HEIC, AVIF or
 * TIFF from some apps) or a file that's too big. Large photos are scaled down; PNG keeps text
 * sharp, and JPEG is the fallback when the PNG would still be too big.
 */
async function reencode(blob: Blob): Promise<Blob | null> {
  try {
    const bitmap = await createImageBitmap(blob);
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.fillStyle = "#fff"; // JPEG has no transparency
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const png = await encode(canvas, "image/png");
    if (png && png.size <= MAX_BYTES) return png;
    const jpeg = await encode(canvas, "image/jpeg", 0.9);
    return jpeg && jpeg.size <= MAX_BYTES ? jpeg : null;
  } catch {
    return null;
  }
}

/** A named file the upload endpoint accepts, or null if `blob` isn't a usable picture. */
export async function pictureFile(blob: Blob, name = "pasted-picture"): Promise<File | null> {
  if (!blob.type.startsWith("image/")) return null;
  let data: Blob | null = blob;
  if (!EXTENSIONS[blob.type] || blob.size > MAX_BYTES) data = await reencode(blob);
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
