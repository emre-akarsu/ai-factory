import "server-only";

const API = process.env.FACTORY_API_URL ?? "http://localhost:8000";

export type Stat = { value: string; label: string; source?: string | null };
export type Plan = { id: string; name: string; price_monthly_usd: number; trial_days: number; includes: string[] };
export type Store = {
  headline: string;
  subheadline: string;
  cta: string;
  problem: Stat[];
  steps: { title: string; body: string }[];
  features: { icon: string; title: string; body: string }[];
  demo: { title: string; note: string; rows: { label: string; value: string }[] };
  roi: { food_cost_pct: number; savings_low_pct: number; savings_high_pct: number; default_monthly_sales: number };
  plans: Plan[];
  faq: { q: string; a: string }[];
  trust: string[];
  media: {
    hero_video?: string | null;
    hero_video_webm?: string | null;
    hero_poster?: string | null;
    social_video?: string | null;
    one_pager?: string | null;
    images: string[];
    kit: { title: string; file: string; kind: string }[];
  };
};
export type Product = {
  employee_id: string;
  name: string;
  version: string;
  industry: string;
  tagline: string;
  description: string;
  category: string;
  highlights: string[];
  permissions: { components: string[]; connectors: { name: string; scopes: string[]; purpose: string }[] };
  suggested_prompts: string[];
  store: Store;
  sandbox: boolean;
};
export type Listing = {
  employee_id: string;
  rank: number;
  name: string;
  industry: string;
  tagline: string;
  category: string;
  price_monthly_usd: number;
  featured: boolean;
  highlights: string[];
};
export type Order = {
  order_id: string;
  status: "pending" | "paid";
  employee_id: string;
  plan_id: string;
  business_name: string;
  email: string;
  workspace_id: string | null;
};

async function get<T>(path: string): Promise<T | null> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (res.status === 404 || res.status === 422) return null;
  if (!res.ok) throw new Error(`API ${path} returned ${res.status}`);
  return res.json();
}

export const getCatalog = () => get<Listing[]>("/v1/marketplace").then((r) => r ?? []);
export const getProduct = (id: string) => get<Product>(`/v1/store/products/${encodeURIComponent(id)}`);
export const getOrder = (id: string) => get<Order>(`/v1/store/orders/${encodeURIComponent(id)}`);

export const media = (employeeId: string, file?: string | null) => (file ? `/media/${employeeId}/${file}` : undefined);
