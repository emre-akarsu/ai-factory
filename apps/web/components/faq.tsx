"use client";

import * as Accordion from "@radix-ui/react-accordion";
import { Plus } from "lucide-react";

export function Faq({ items }: { items: { q: string; a: string }[] }) {
  return (
    <Accordion.Root type="single" collapsible className="divide-y divide-line rounded-2xl border border-line bg-card">
      {items.map((item, i) => (
        <Accordion.Item key={item.q} value={`q${i}`}>
          <Accordion.Header>
            <Accordion.Trigger className="group flex w-full items-center justify-between gap-4 px-6 py-5 text-left font-medium">
              {item.q}
              <Plus className="size-4 shrink-0 text-muted transition-transform group-data-[state=open]:rotate-45" />
            </Accordion.Trigger>
          </Accordion.Header>
          <Accordion.Content className="px-6 pb-5 text-sm leading-relaxed text-muted">{item.a}</Accordion.Content>
        </Accordion.Item>
      ))}
    </Accordion.Root>
  );
}
