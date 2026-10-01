import { FileClock, MessageSquare, Receipt, Scale, ShieldCheck, Sparkles, Truck, type LucideIcon } from "lucide-react";

const icons: Record<string, LucideIcon> = {
  scale: Scale,
  truck: Truck,
  "shield-check": ShieldCheck,
  receipt: Receipt,
  "message-square": MessageSquare,
  "file-clock": FileClock,
};

// store.yaml names icons by their lucide name; unknown names fall back to a sparkle.
export function Icon({ name, className }: { name: string; className?: string }) {
  const C = icons[name] ?? Sparkles;
  return <C className={className} aria-hidden />;
}
