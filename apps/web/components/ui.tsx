import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// shadcn-style primitives, themed for the store.
export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-full font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-60",
  {
    variants: {
      variant: {
        primary: "bg-accent text-white hover:bg-[#c94a22] shadow-sm",
        brand: "bg-brand text-brand-ink hover:bg-[#173b2c]",
        outline: "border border-line bg-card hover:bg-[#f3eee4]",
        ghost: "hover:bg-[#f3eee4]",
      },
      size: { sm: "h-9 px-4 text-sm", md: "h-11 px-6 text-sm", lg: "h-13 px-8 text-base" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export function Button({
  className, variant, size, asChild, ...props
}: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export function Card({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("rounded-2xl border border-line bg-card shadow-[0_1px_0_rgba(0,0,0,0.03)]", className)} {...props} />;
}

export function Badge({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent", className)}
      {...props}
    />
  );
}

export function Eyebrow({ className, ...props }: React.ComponentProps<"p">) {
  return <p className={cn("text-xs font-semibold uppercase tracking-[0.18em] text-accent", className)} {...props} />;
}

export function Section({ className, ...props }: React.ComponentProps<"section">) {
  return <section className={cn("mx-auto max-w-6xl px-5 py-20", className)} {...props} />;
}
