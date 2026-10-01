import { expect, test } from "@playwright/test";

test("a restaurant finds the Purchasing Manager and starts a trial", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /Purchasing Manager/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Your food costs");

  // The demo video loads from the pack's marketing folder.
  const duration = await page.locator("video").evaluate(async (v: HTMLVideoElement) => {
    if (v.readyState < 1) await new Promise((r) => v.addEventListener("loadedmetadata", r, { once: true }));
    return v.duration;
  });
  expect(duration).toBeGreaterThan(40);

  // The savings calculator reacts to the sliders.
  const range = page.getByTestId("roi-range");
  const before = await range.textContent();
  await page.getByLabel("Monthly sales").fill("300000");
  await expect(range).not.toHaveText(before!);

  await page.getByRole("button", { name: /Plus|Do I have to change suppliers/ }).first().click();
  await expect(page.getByText("It works with the distributors")).toBeVisible();

  await page.getByPlaceholder("Restaurant name").fill("Playwright Bistro");
  await page.getByPlaceholder("Work email").fill(`owner-${Date.now()}@bistro.example`);
  await page.getByRole("button", { name: "Start 14-day free trial" }).click();

  await expect(page).toHaveURL(/\/checkout\/sandbox\?order=/);
  await expect(page.getByText("Playwright Bistro")).toBeVisible();
  await page.getByRole("button", { name: "Start free trial" }).click();

  await expect(page).toHaveURL(/\/checkout\/success\?order=/);
  await expect(page.getByRole("heading")).toContainText("Welcome aboard, Playwright Bistro");
  await expect(page.getByTestId("workspace-id")).toContainText(/Workspace [0-9a-f-]{36}/);
});

test("marketing kit files download", async ({ page, request }) => {
  await page.goto("/employees/restaurant-purchasing");
  const links = await page.locator("a[href^='/media/']").evaluateAll((as) => [...new Set(as.map((a) => a.getAttribute("href")!))]);
  expect(links.length).toBeGreaterThanOrEqual(6);
  for (const href of links) {
    const res = await request.get(href, { headers: { Range: "bytes=0-10" } });
    expect([200, 206], href).toContain(res.status());
  }
});
