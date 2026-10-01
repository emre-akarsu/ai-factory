import Link from "next/link";
import { ArrowRight, Star } from "lucide-react";
import { Badge, Card, Eyebrow, Section } from "@/components/ui";
import { getCatalog } from "@/lib/api";
import { brand } from "@/lib/brand";
import { usd } from "@/lib/utils";

export default async function Home() {
  const catalog = await getCatalog();
  return (
    <>
      <Section className="pb-10 pt-20 text-center">
        <Eyebrow>{brand.name} marketplace</Eyebrow>
        <h1 className="mx-auto mt-4 max-w-3xl font-display text-5xl font-semibold leading-tight tracking-tight md:text-6xl">
          Hire an AI employee for the work nobody has time for.
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-muted">
          Each one does a real job inside your business, asks before it spends money, and logs everything it does.
        </p>
      </Section>
      <Section className="pt-6">
        <div className="grid gap-6 md:grid-cols-2">
          {catalog.map((l) => (
            <Link key={l.employee_id} href={`/employees/${l.employee_id}`} className="group">
              <Card className="h-full p-8 transition group-hover:-translate-y-0.5 group-hover:shadow-xl group-hover:shadow-brand/10">
                <div className="flex items-center justify-between">
                  <Badge className="capitalize">{l.industry}</Badge>
                  {l.featured ? <span className="flex items-center gap-1 text-xs font-medium text-brand"><Star className="size-3.5" fill="currentColor" />Featured</span> : null}
                </div>
                <h2 className="mt-6 font-display text-3xl font-semibold">{l.name}</h2>
                <p className="mt-3 text-muted">{l.tagline}</p>
                <ul className="mt-6 space-y-1.5 text-sm">
                  {l.highlights.map((h) => <li key={h}>• {h}</li>)}
                </ul>
                <div className="mt-8 flex items-center justify-between">
                  <span className="text-sm"><strong className="text-lg">{usd(l.price_monthly_usd)}</strong> / month</span>
                  <span className="flex items-center gap-1 text-sm font-medium text-accent">See details <ArrowRight className="size-4 transition group-hover:translate-x-1" /></span>
                </div>
              </Card>
            </Link>
          ))}
          <Card className="flex h-full flex-col justify-center border-dashed p-8 text-muted">
            <p className="font-display text-2xl font-semibold text-foreground">More employees are in training</p>
            <p className="mt-3 text-sm">Bookkeeping, marketing and prospecting employees are next.</p>
          </Card>
        </div>
      </Section>
    </>
  );
}
