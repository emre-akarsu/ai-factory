"use client";

import { useState } from "react";
import { Loader2, Lock } from "lucide-react";
import { Button } from "@/components/ui";

export function CheckoutForm({ employeeId, planId, cta, sandbox }: { employeeId: string; planId: string; cta: string; sandbox: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    const res = await fetch("/api/store/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        employee_id: employeeId, plan_id: planId,
        email: form.get("email"), business_name: form.get("business_name"),
      }),
    });
    if (!res.ok) {
      setBusy(false);
      setError(res.status === 422 ? "Please check your email address and restaurant name." : "Checkout is unavailable right now. Please try again.");
      return;
    }
    const { url } = await res.json();
    window.location.assign(url);
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <input
        name="business_name" required maxLength={120} placeholder="Restaurant name"
        className="h-11 w-full rounded-xl border border-line bg-white px-4 text-sm outline-none focus:border-accent"
      />
      <input
        name="email" type="email" required placeholder="Work email"
        className="h-11 w-full rounded-xl border border-line bg-white px-4 text-sm outline-none focus:border-accent"
      />
      <Button type="submit" size="lg" className="w-full" disabled={busy}>
        {busy ? <Loader2 className="size-4 animate-spin" /> : null}
        {cta}
      </Button>
      {error ? <p role="alert" className="text-sm text-accent">{error}</p> : null}
      <p className="flex items-center justify-center gap-1.5 text-xs text-muted">
        <Lock className="size-3" />
        {sandbox ? "Sandbox checkout: no card is charged." : "Secure checkout by Stripe. Cancel any time."}
      </p>
    </form>
  );
}
