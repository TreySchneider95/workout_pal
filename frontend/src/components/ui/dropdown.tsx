import { DropdownMenu as Menu } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

export const DropdownMenu = Menu.Root;
export const DropdownMenuTrigger = Menu.Trigger;

export function DropdownMenuContent({ className, ...props }: React.ComponentProps<typeof Menu.Content>) {
  return (
    <Menu.Portal>
      <Menu.Content
        align="end"
        sideOffset={6}
        className={cn(
          "z-50 min-w-52 rounded-2xl border border-border bg-elevated p-1.5 shadow-2xl shadow-black/50 data-[state=open]:animate-fade-in",
          className,
        )}
        {...props}
      />
    </Menu.Portal>
  );
}

export function DropdownMenuItem({
  className,
  destructive,
  ...props
}: React.ComponentProps<typeof Menu.Item> & { destructive?: boolean }) {
  return (
    <Menu.Item
      className={cn(
        "flex h-11 cursor-pointer select-none items-center gap-3 rounded-xl px-3 text-[15px] outline-none data-[highlighted]:bg-muted [&_svg]:size-[18px] [&_svg]:text-muted-foreground",
        destructive && "text-destructive [&_svg]:text-destructive",
        className,
      )}
      {...props}
    />
  );
}

export const DropdownMenuSeparator = () => <Menu.Separator className="my-1 h-px bg-border" />;
