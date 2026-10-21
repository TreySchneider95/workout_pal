import { Dumbbell, Maximize2, X } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

interface Props {
  thumbUrl: string | null;
  imageUrl: string | null;
  alt: string;
  className?: string;
  /** Open the full-size image on tap. */
  zoomable?: boolean;
}

/** Exercise demo image with a graceful placeholder when missing or broken. */
export function ExerciseImage({ thumbUrl, imageUrl, alt, className, zoomable = false }: Props) {
  const [failed, setFailed] = React.useState(false);
  const src = thumbUrl ?? imageUrl;

  React.useEffect(() => setFailed(false), [src]);

  if (!src || failed) {
    return (
      <div
        className={cn("flex items-center justify-center rounded-xl bg-muted text-subtle", className)}
        role="img"
        aria-label={`${alt} (no image)`}
      >
        <Dumbbell className="size-1/3 max-h-8 max-w-8" />
      </div>
    );
  }

  const img = (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={cn("rounded-xl bg-white object-cover object-top", className)}
    />
  );

  if (!zoomable || !imageUrl) return img;

  return (
    <DialogPrimitive.Root>
      <DialogPrimitive.Trigger className="group relative shrink-0 rounded-xl" aria-label={`View ${alt} demonstration`}>
        {img}
        <span className="absolute bottom-1 right-1 rounded-md bg-black/60 p-1 text-white opacity-90">
          <Maximize2 className="size-3.5" />
        </span>
      </DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/90 data-[state=open]:animate-fade-in" />
        <DialogPrimitive.Content className="fixed inset-0 z-50 flex items-center justify-center p-3 outline-none pt-safe pb-safe">
          <DialogPrimitive.Title className="sr-only">{alt}</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">Exercise demonstration image</DialogPrimitive.Description>
          <DialogPrimitive.Close className="absolute inset-0" aria-label="Close image" />
          <img src={imageUrl} alt={alt} className="relative max-h-full max-w-full rounded-xl object-contain" />
          <DialogPrimitive.Close
            className="absolute right-4 top-[calc(1rem+env(safe-area-inset-top))] rounded-full bg-black/70 p-2.5 text-white"
            aria-label="Close"
          >
            <X className="size-5" />
          </DialogPrimitive.Close>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
