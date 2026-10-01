import { NextResponse, type NextRequest } from "next/server";

const API = process.env.FACTORY_API_URL ?? "http://localhost:8000";

// Plain form POST, so the sandbox button works before the page has hydrated.
export async function POST(request: NextRequest) {
  const order = String((await request.formData()).get("order") ?? "");
  const res = await fetch(`${API}/v1/store/sandbox/${encodeURIComponent(order)}/complete`, { method: "POST" });
  const target = res.ok ? `/checkout/success?order=${encodeURIComponent(order)}` : `/checkout/sandbox?order=${encodeURIComponent(order)}`;
  return NextResponse.redirect(new URL(target, request.url), 303);
}
