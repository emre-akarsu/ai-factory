"use client";

import { useState } from "react";
import { usd } from "@/lib/utils";

type Roi = { food_cost_pct: number; savings_low_pct: number; savings_high_pct: number; default_monthly_sales: number };

export function RoiCalculator({ roi, price }: { roi: Roi; price: number }) {
  const [sales, setSales] = useState(roi.default_monthly_sales);
  const [foodPct, setFoodPct] = useState(roi.food_cost_pct);
  const spend = (sales * foodPct) / 100;
  const low = (spend * roi.savings_low_pct) / 100;
  const high = (spend * roi.savings_high_pct) / 100;

  return (
    <div className="grid gap-8 rounded-3xl bg-brand p-6 text-brand-ink sm:p-8 md:grid-cols-2 md:p-12">
      <div className="min-w-0 space-y-8">
        <label className="block">
          <span className="flex justify-between text-sm opacity-80">
            Monthly sales <strong className="font-semibold text-white">{usd(sales)}</strong>
          </span>
          <input
            aria-label="Monthly sales"
            type="range" min={20000} max={600000} step={5000} value={sales}
            onChange={(e) => setSales(Number(e.target.value))}
            className="mt-3 w-full accent-[#e0562b]"
          />
        </label>
        <label className="block">
          <span className="flex justify-between text-sm opacity-80">
            Food cost <strong className="font-semibold text-white">{foodPct}% of sales</strong>
          </span>
          <input
            aria-label="Food cost percent"
            type="range" min={20} max={45} step={1} value={foodPct}
            onChange={(e) => setFoodPct(Number(e.target.value))}
            className="mt-3 w-full accent-[#e0562b]"
          />
        </label>
        <p className="text-xs leading-relaxed opacity-70">
          Estimate only. It assumes better supplier choice and invoice credits save {roi.savings_low_pct}% to{" "}
          {roi.savings_high_pct}% of your {usd(spend)} monthly food spend. Your result depends on your prices.
        </p>
      </div>
      <div className="flex min-w-0 flex-col justify-center rounded-2xl bg-white/10 p-8">
        <p className="text-sm opacity-80">Estimated savings per month</p>
        <p data-testid="roi-range" className="mt-2 font-display text-5xl font-semibold text-white">
          {usd(low)}–{usd(high)}
        </p>
        <p className="mt-4 text-sm opacity-80">
          Against a {usd(price)} monthly plan, that is {Math.max(0, low / price).toFixed(1)}× to {(high / price).toFixed(1)}× what you pay.
        </p>
      </div>
    </div>
  );
}
