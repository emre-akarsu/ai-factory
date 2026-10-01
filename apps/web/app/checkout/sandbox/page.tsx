import { notFound } from "next/navigation";
import { FlaskConical } from "lucide-react";
import { Button, Card, Section } from "@/components/ui";
import { getOrder } from "@/lib/api";

// Stands in for Stripe Checkout when the API has no Stripe keys.
export default async function SandboxCheckout({ searchParams }: PageProps<"/checkout/sandbox">) {
  const { order: orderId } = await searchParams;
  const order = typeof orderId === "string" ? await getOrder(orderId) : null;
  if (!order) notFound();
  return (
    <Section className="max-w-lg">
      <Card className="p-8">
        <p className="flex items-center gap-2 text-sm font-medium text-accent"><FlaskConical className="size-4" />Sandbox checkout, no card is charged</p>
        <h1 className="mt-4 font-display text-3xl font-semibold">Confirm your trial</h1>
        <dl className="mt-6 space-y-2 text-sm">
          <div className="flex justify-between"><dt className="text-muted">Restaurant</dt><dd>{order.business_name}</dd></div>
          <div className="flex justify-between"><dt className="text-muted">Email</dt><dd>{order.email}</dd></div>
          <div className="flex justify-between"><dt className="text-muted">Plan</dt><dd className="capitalize">{order.plan_id}</dd></div>
        </dl>
        <form method="post" action="/checkout/sandbox/complete" className="mt-8">
          <input type="hidden" name="order" value={order.order_id} />
          <Button type="submit" size="lg" className="w-full">Start free trial</Button>
        </form>
      </Card>
    </Section>
  );
}
