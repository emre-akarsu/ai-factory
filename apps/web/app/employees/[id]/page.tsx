import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ArrowRight, Check, Download, FileText, Film, ImageIcon, Mail, ShieldCheck } from "lucide-react";
import { CheckoutForm } from "@/components/checkout-form";
import { Faq } from "@/components/faq";
import { Icon } from "@/components/icons";
import { RoiCalculator } from "@/components/roi-calculator";
import { Badge, Button, Card, Eyebrow, Section } from "@/components/ui";
import { VideoPlayer } from "@/components/video-player";
import { getProduct, media } from "@/lib/api";
import { usd } from "@/lib/utils";

// Generic product page: everything on it comes from the employee's store.yaml and manifest.

export async function generateMetadata({ params }: PageProps<"/employees/[id]">): Promise<Metadata> {
  const product = await getProduct((await params).id);
  if (!product) return {};
  return {
    title: `${product.name} for ${product.industry}`,
    description: product.tagline,
    openGraph: { images: product.store.media.images.length ? [media(product.employee_id, product.store.media.images[1] ?? product.store.media.images[0])!] : [] },
  };
}

const kitIcon = { video: Film, pdf: FileText, image: ImageIcon, text: Mail } as const;

export default async function ProductPage({ params }: PageProps<"/employees/[id]">) {
  const { id } = await params;
  const product = await getProduct(id);
  if (!product) notFound();
  const s = product.store;
  const plan = s.plans[0];
  const m = (f?: string | null) => media(product.employee_id, f);

  return (
    <>
      {/* Hero */}
      <div className="relative overflow-hidden">
        <div className="pointer-events-none absolute -top-40 right-[-10%] size-[640px] rounded-full bg-accent-soft blur-3xl" />
        <Section className="relative grid items-center gap-12 pb-16 pt-14 lg:grid-cols-[1.05fr_1fr]">
          <div>
            <Badge>AI employee for {product.industry}</Badge>
            <h1 className="mt-5 font-display text-5xl font-semibold leading-[1.05] tracking-tight md:text-6xl">
              {s.headline}
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted">{s.subheadline}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg"><a href="#pricing">{s.cta} <ArrowRight className="size-4" /></a></Button>
              <Button asChild size="lg" variant="outline"><a href="#demo">Watch the demo</a></Button>
            </div>
            <ul className="mt-8 grid gap-2 text-sm text-muted sm:grid-cols-2">
              {product.highlights.map((h) => (
                <li key={h} className="flex items-center gap-2"><Check className="size-4 text-good" />{h}</li>
              ))}
            </ul>
          </div>
          {s.media.hero_video ? (
            <VideoPlayer src={m(s.media.hero_video)!} webm={m(s.media.hero_video_webm)} poster={m(s.media.hero_poster)} title={`${product.name} demo`} />
          ) : null}
        </Section>
      </div>

      {/* Problem */}
      <div className="border-y border-line bg-card">
        <Section className="py-14">
          <div className="grid gap-8 md:grid-cols-3">
            {s.problem.map((p) => (
              <div key={p.value}>
                <p className="font-display text-5xl font-semibold text-brand">{p.value}</p>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  {p.label}{" "}
                  {p.source ? <a href={p.source} target="_blank" rel="noreferrer" className="underline decoration-line underline-offset-2 hover:text-foreground">Source</a> : null}
                </p>
              </div>
            ))}
          </div>
        </Section>
      </div>

      {/* How it works */}
      <Section>
        <Eyebrow>How it works</Eyebrow>
        <h2 className="mt-3 max-w-2xl font-display text-4xl font-semibold tracking-tight">From the walk-in to the supplier&rsquo;s inbox, without the spreadsheet.</h2>
        <ol className="mt-12 grid gap-6 md:grid-cols-4">
          {s.steps.map((step, i) => (
            <li key={step.title} className="relative">
              <span className="font-display text-sm font-semibold text-accent">0{i + 1}</span>
              <h3 className="mt-2 text-xl font-semibold">{step.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{step.body}</p>
            </li>
          ))}
        </ol>
      </Section>

      {/* App preview + demo numbers */}
      <Section className="grid items-center gap-12 pt-0 lg:grid-cols-2">
        <Card className="overflow-hidden p-0">
          <div className="flex items-center justify-between border-b border-line bg-[#f7f3ea] px-6 py-4">
            <div>
              <p className="text-xs text-muted">{product.name}</p>
              <p className="font-semibold">{s.demo.title}</p>
            </div>
            <Badge className="bg-[#e3f1e8] text-good">Ready for approval</Badge>
          </div>
          <dl className="divide-y divide-line">
            {s.demo.rows.map((r) => (
              <div key={r.label} className="flex items-center justify-between gap-6 px-6 py-4">
                <dt className="text-sm text-muted">{r.label}</dt>
                <dd className="text-right font-semibold">{r.value}</dd>
              </div>
            ))}
          </dl>
          <div className="flex gap-3 border-t border-line bg-[#f7f3ea] px-6 py-4">
            <span className="rounded-full bg-brand px-4 py-2 text-xs font-medium text-brand-ink">Approve and send</span>
            <span className="rounded-full border border-line bg-white px-4 py-2 text-xs font-medium">Review lines</span>
          </div>
        </Card>
        <div>
          <Eyebrow>See it work</Eyebrow>
          <h2 className="mt-3 font-display text-4xl font-semibold tracking-tight">One count in. Orders out. Overcharges back.</h2>
          <p className="mt-5 leading-relaxed text-muted">{product.description}</p>
          <p className="mt-4 text-xs text-muted">{s.demo.note}</p>
        </div>
      </Section>

      {/* Features */}
      <div className="bg-card">
        <Section>
          <Eyebrow>What it does</Eyebrow>
          <h2 className="mt-3 font-display text-4xl font-semibold tracking-tight">A purchasing manager that never skips the boring part.</h2>
          <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {s.features.map((f) => (
              <Card key={f.title} className="p-6">
                <span className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent"><Icon name={f.icon} className="size-5" /></span>
                <h3 className="mt-5 text-lg font-semibold">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{f.body}</p>
              </Card>
            ))}
          </div>
        </Section>
      </div>

      {/* ROI */}
      <Section>
        <Eyebrow>What it could save you</Eyebrow>
        <h2 className="mb-10 mt-3 font-display text-4xl font-semibold tracking-tight">Run your own numbers.</h2>
        <RoiCalculator roi={s.roi} price={plan.price_monthly_usd} />
      </Section>

      {/* Pricing */}
      <Section id="pricing" className="grid gap-12 pt-4 lg:grid-cols-[1fr_440px]">
        <div>
          <Eyebrow>Pricing</Eyebrow>
          <h2 className="mt-3 font-display text-4xl font-semibold tracking-tight">One price per location. Try it free for {plan.trial_days} days.</h2>
          <ul className="mt-8 space-y-3">
            {plan.includes.map((i) => (
              <li key={i} className="flex items-start gap-3"><Check className="mt-0.5 size-5 text-good" />{i}</li>
            ))}
          </ul>
          <Card className="mt-10 p-6">
            <p className="flex items-center gap-2 font-semibold"><ShieldCheck className="size-5 text-brand" />What it can access</p>
            <ul className="mt-3 space-y-1 text-sm text-muted">
              {product.permissions.connectors.map((c) => (
                <li key={c.name}>Your {c.name} ({c.scopes.join(", ")}): {c.purpose.toLowerCase()}.</li>
              ))}
              <li>Nothing else. You approve these on install and can remove them any time.</li>
            </ul>
            <div className="mt-5 flex flex-wrap gap-2">
              {s.trust.map((t) => <Badge key={t} className="bg-[#eef3ef] text-brand">{t}</Badge>)}
            </div>
          </Card>
        </div>
        <Card className="h-fit p-8 shadow-xl shadow-brand/10 lg:sticky lg:top-24">
          <p className="font-semibold">{product.name} · {plan.name}</p>
          <p className="mt-4 flex items-baseline gap-2">
            <span className="font-display text-6xl font-semibold">{usd(plan.price_monthly_usd)}</span>
            <span className="text-muted">/ month</span>
          </p>
          <p className="mt-2 text-sm text-muted">{plan.trial_days}-day free trial, then billed monthly.</p>
          <div className="mt-6">
            <CheckoutForm employeeId={product.employee_id} planId={plan.id} cta={s.cta} sandbox={product.sandbox} />
          </div>
        </Card>
      </Section>

      {/* FAQ */}
      <Section className="max-w-3xl">
        <h2 className="mb-8 text-center font-display text-4xl font-semibold tracking-tight">Questions owners ask</h2>
        <Faq items={s.faq} />
      </Section>

      {/* Marketing kit */}
      {s.media.kit.length ? (
        <div className="bg-brand text-brand-ink">
          <Section className="py-16">
            <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#f5a88e]">Press and partner kit</p>
                <h2 className="mt-3 font-display text-3xl font-semibold">Videos, one-pager and launch copy</h2>
              </div>
              {s.media.one_pager ? (
                <Button asChild variant="primary"><a href={m(s.media.one_pager)} download>Download the one-pager <Download className="size-4" /></a></Button>
              ) : null}
            </div>
            <ul className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {s.media.kit.map((k) => {
                const KitIcon = kitIcon[k.kind as keyof typeof kitIcon] ?? FileText;
                return (
                  <li key={k.file}>
                    <a href={m(k.file)} target="_blank" rel="noreferrer" className="flex items-center gap-3 rounded-xl bg-white/10 px-4 py-3 text-sm hover:bg-white/15">
                      <KitIcon className="size-4 shrink-0" />{k.title}
                    </a>
                  </li>
                );
              })}
            </ul>
          </Section>
        </div>
      ) : null}
    </>
  );
}
