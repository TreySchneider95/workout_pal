import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex shrink-0 select-none items-center justify-center gap-2 whitespace-nowrap rounded-xl font-semibold transition-[background-color,color,transform,opacity] active:scale-[0.97] disabled:pointer-events-none disabled:opacity-40 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        secondary: "bg-elevated text-foreground hover:bg-muted border border-border",
        ghost: "text-foreground hover:bg-muted",
        outline: "border border-input bg-transparent hover:bg-muted",
        destructive: "bg-destructive-soft text-destructive hover:bg-destructive/20",
        soft: "bg-primary-soft text-primary hover:bg-primary/20",
      },
      size: {
        default: "h-11 px-4 text-[15px] [&_svg]:size-[18px]",
        sm: "h-9 px-3 text-sm rounded-lg [&_svg]:size-4",
        lg: "h-14 px-6 text-base rounded-2xl [&_svg]:size-5",
        icon: "size-11 [&_svg]:size-5",
        "icon-sm": "size-9 rounded-lg [&_svg]:size-[18px]",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps extends React.ComponentProps<"button">, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild = false, type, ...props }: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      className={cn(buttonVariants({ variant, size }), className)}
      type={asChild ? undefined : (type ?? "button")}
      {...props}
    />
  );
}

export { buttonVariants };
