import { ClipboardPaste, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { pictureFile, pictureFromData, readClipboardPicture } from "@/lib/pasteImage";

const NOT_A_PICTURE = "There's no picture on the clipboard. In the AI app, press and hold the picture (or right-click it) and choose Copy.";
const UNREADABLE = "That picture couldn't be used (it may be too big or in a format this browser can't open). Save it and use Upload file instead.";

function pasteHint(): string {
  if (window.matchMedia?.("(pointer: coarse)").matches) return "Press and hold here, then tap Paste";
  return `Press ${/Mac|iPhone|iPad/.test(navigator.userAgent) ? "⌘V" : "Ctrl+V"} here, or drop the picture`;
}

/**
 * "Paste picture": reads the clipboard directly where the browser allows it, otherwise opens a
 * box to paste into (works over plain http too). Renders a button plus, when open, a full-width
 * box on its own row after the other buttons, in a grid or a wrapping flex row.
 */
export function PastePicture({
  onPicture,
  disabled,
  name,
  label = "Paste picture",
  ...buttonProps
}: {
  onPicture: (file: File) => void;
  disabled?: boolean;
  name?: string;
  label?: string;
} & Pick<React.ComponentProps<typeof Button>, "size" | "variant" | "className">) {
  const [open, setOpen] = React.useState(false);
  const box = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (open) box.current?.focus();
  }, [open]);

  const use = async (blob: Blob | null) => {
    const file = blob ? await pictureFile(blob, name) : null;
    if (!file) {
      toast.error(blob?.type.startsWith("image/") ? UNREADABLE : NOT_A_PICTURE);
      return;
    }
    setOpen(false);
    onPicture(file);
  };

  return (
    <>
      <Button
        {...buttonProps}
        disabled={disabled}
        onClick={async () => {
          const result = await readClipboardPicture();
          if (result === "unavailable") setOpen(true);
          else void use(result);
        }}
      >
        <ClipboardPaste /> {label}
      </Button>
      {open && (
        // Its own full-width row after the buttons, in a grid (col-span-full) or a wrapping flex row (basis-full).
        <div className="relative order-last col-span-full w-full basis-full">
          <div
            ref={box}
            contentEditable
            suppressContentEditableWarning
            inputMode="none"
            role="textbox"
            aria-label="Paste the picture here"
            className="flex h-24 w-full items-center justify-center rounded-xl border-2 border-dashed border-primary/50 bg-primary-soft/40 text-transparent caret-transparent outline-none focus:border-primary"
            onPaste={(e) => {
              e.preventDefault();
              void use(pictureFromData(e.clipboardData));
            }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              void use(pictureFromData(e.dataTransfer));
            }}
            // Keep the box empty whatever gets typed into it.
            onInput={(e) => {
              e.currentTarget.textContent = "";
            }}
          />
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center px-10 text-center text-sm font-medium text-primary">
            {pasteHint()}
          </div>
          <button
            type="button"
            className="absolute right-2 top-2 rounded-lg p-1 text-muted-foreground hover:bg-muted"
            onClick={() => setOpen(false)}
            aria-label="Close paste box"
          >
            <X className="size-4" />
          </button>
        </div>
      )}
    </>
  );
}
