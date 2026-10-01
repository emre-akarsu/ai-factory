import { notFound } from "next/navigation";
import { CheckCircle2, Clock } from "lucide-react";
import { Card, Section } from "@/components/ui";
import { getOrder } from "@/lib/api";

export default async function Success({ searchParams }: PageProps<"/checkout/success">) {
  const { order: orderId } = await searchParams;
  const order = typeof orderId === "string" ? await getOrder(orderId) : null;
  if (!order) notFound();
  const paid = order.status === "paid";
  return (
    <Section className="max-w-xl text-center">
      <Card className="p-10">
        {paid ? <CheckCircle2 className="mx-auto size-12 text-good" /> : <Clock className="mx-auto size-12 text-muted" />}
        <h1 className="mt-5 font-display text-4xl font-semibold">
          {paid ? `Welcome aboard, ${order.business_name}` : "Confirming your payment"}
        </h1>
        <p className="mt-4 text-muted">
          {paid
            ? `Your workspace is ready. Sign in with ${order.email} to connect your email, add your suppliers and set par levels.`
            : "This takes a few seconds. Refresh the page if it does not update."}
        </p>
        {paid ? <p data-testid="workspace-id" className="mt-6 text-xs text-muted">Workspace {order.workspace_id}</p> : null}
      </Card>
    </Section>
  );
}
