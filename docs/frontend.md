# Frontend Architecture & UI Component Decisions

**Last Updated**: 2026-02-24
**Stack**: Next.js 14 · shadcn/ui · Tailwind CSS · Recharts · TypeScript

---

## Table of Contents

1. [Tech Stack Overview](#tech-stack-overview)
2. [Component Library — shadcn/ui](#component-library--shadcnui)
3. [Design System & Theming](#design-system--theming)
4. [Component Inventory](#component-inventory)
5. [Page Architecture](#page-architecture)
6. [Key Design Decisions](#key-design-decisions)
7. [Patterns & Conventions](#patterns--conventions)
8. [Adding New Components](#adding-new-components)

---

## Tech Stack Overview

| Layer | Technology | Why |
|-------|-----------|-----|
| Framework | Next.js 14 (App Router) | RSC for data pages, client components only where interactivity needed |
| UI Library | shadcn/ui | Copy-owned components, Tailwind-first, no runtime dependency |
| Styling | Tailwind CSS v3 | Utility-first, co-located with markup |
| Charts | Recharts | Declarative, composable, works well with Recharts + Tailwind |
| Icons | lucide-react | Consistent stroke-based icon set |
| Type safety | TypeScript strict mode | End-to-end types from API → component props |

---

## Component Library — shadcn/ui

### What shadcn/ui Is

shadcn/ui is **not an npm package**. Components are copied directly into the codebase via CLI (`npx shadcn@latest add`). This means:
- Components live in `components/ui/` — they are **our code**, not a node_modules dependency
- They can be freely modified without forking or patching a library
- Upgrades are opt-in: re-run `npx shadcn@latest add <component> --overwrite`

### Configuration

**`frontend/components.json`** — shadcn config file:
```json
{
  "style": "default",
  "rsc": true,
  "tsx": true,
  "tailwind": {
    "baseColor": "zinc",
    "cssVariables": true
  },
  "aliases": {
    "ui": "@/components/ui",
    "utils": "@/lib/utils"
  }
}
```

- `baseColor: zinc` — neutral palette anchors (zinc-800, zinc-900 etc.) match the dark dashboard aesthetic
- `cssVariables: true` — all colors flow through CSS custom properties, enabling dark mode via a single `.dark` class swap

### Installed Components

| Component | File | Used In |
|-----------|------|---------|
| Card | `ui/card.tsx` | All pages, all chart wrappers |
| Badge | `ui/badge.tsx` (extended) | data-table, target-achievement, upload page |
| Button | `ui/button.tsx` | sales-filters, target-achievement, revenue-trend, upload page |
| Select | `ui/select.tsx` | sales-filters (portal picker), upload page (file type picker) |
| Input | `ui/input.tsx` | sales-filters (date range), product-table (search) |
| Table | `ui/table.tsx` | data-table, dashboard/page, inventory/page |
| Progress | `ui/progress.tsx` | target-achievement (progress bars) |
| Skeleton | `ui/skeleton.tsx` | sales/page loading states |
| Separator | `ui/separator.tsx` | available, not yet used |

To add a new component: `npx shadcn@latest add <name>` from `frontend/`.

---

## Design System & Theming

### Dark Mode

The app is **always dark**. `<html className="dark">` is set unconditionally in `app/layout.tsx`. Light mode CSS variables exist in `:root` (shadcn requirement) but are never activated.

### CSS Variables (`app/globals.css`)

Both `:root` and `.dark` define the full token set. The critical dark-mode overrides:

```css
.dark {
  --background: 240 10% 3.9%;     /* zinc-950 */
  --foreground: 0 0% 98%;
  --card: 240 10% 7%;             /* zinc-900 */
  --card-foreground: 0 0% 98%;
  --muted: 240 3.7% 15.9%;        /* zinc-800 */
  --muted-foreground: 240 5% 64.9%;
  --border: 240 3.7% 15.9%;
  --input: 240 3.7% 15.9%;
  --ring: 240 4.9% 83.9%;
  --primary: 24 95% 53%;          /* orange-500 — brand color */
  --primary-foreground: 0 0% 100%;
  --secondary: 240 3.7% 15.9%;
  --secondary-foreground: 0 0% 98%;
  --accent: 240 3.7% 15.9%;
  --accent-foreground: 0 0% 98%;
  --destructive: 0 62.8% 30.6%;
  --destructive-foreground: 0 0% 98%;
  --popover: 240 10% 7%;
  --popover-foreground: 0 0% 98%;
}
```

### Brand Color — Orange

`--primary: 24 95% 53%` maps to `#f97316` (Tailwind `orange-500`). This is the brand accent used for:
- Default `<Button>` background (`bg-primary`)
- Active nav tab indicator (`text-orange-400 border-orange-400`)
- Active filter preset buttons (`bg-orange-500`)
- Chart accents and highlights

**Why a CSS variable instead of hardcoding `orange-500`?** shadcn's `<Button variant="default">` uses `bg-primary` — by setting `--primary` to orange in `.dark`, all default buttons are automatically orange with no per-component overrides.

### Tailwind Config (`tailwind.config.js`)

Extends Tailwind's color system with both CSS variable tokens (for shadcn) and a static `brand` palette:

```js
colors: {
  brand: { 50: "#fff7ed", 100: "#ffedd5", 500: "#f97316", 600: "#ea580c", 700: "#c2410c" },
  primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
  // ...secondary, accent, destructive, popover, muted, card, border, input, ring
}
```

Use `bg-primary` / `text-primary` for shadcn-integrated components. Use `brand-500` for arbitrary orange usage in non-shadcn contexts (charts, etc.).

---

## Component Inventory

### `components/ui/` — shadcn Primitives

These are owned, copyable shadcn components. Do not add business logic here.

#### `badge.tsx` — Extended with Custom Variants

Standard shadcn Badge extended with 4 additional CVA variants for the dark dashboard context:

```ts
success:  "border-green-800 bg-green-900/50 text-green-400"
warning:  "border-yellow-800 bg-yellow-900/50 text-yellow-400"
danger:   "border-red-800 bg-red-900/50 text-red-400"
muted:    "border-transparent bg-zinc-800 text-zinc-500"
```

Full variant list: `default | secondary | destructive | outline | success | warning | danger | muted`

**Why extended rather than replaced?** The existing codebase already referenced `success`, `warning`, `danger`, `muted` variants. Extending the CVA definition means zero changes at call sites.

#### `nav-tabs.tsx` — Custom (Not shadcn)

Shared navigation component used on all 4 dashboard pages. **Not a shadcn component** — custom built because shadcn's Tabs component uses internal state, but we need URL-driven active state via `usePathname()`.

```tsx
// Active state: orange underline. Inactive: zinc-500 → zinc-200 on hover
const isActive = pathname === href;
```

To add a new page to the nav, add one entry to `NAV_ITEMS`:
```ts
{ label: "Reports", href: "/dashboard/reports" }
```

---

### `components/charts/`

#### `metric-card.tsx`
Wraps shadcn `<Card>` + `<CardContent>`. Accepts `label`, `value`, and optional `highlight` (renders value in orange when true, e.g. low-stock alert count).

#### `bar-chart.tsx`
Recharts `BarChart` wrapper. Accepts `data: { name: string; value: number }[]`, `dataKey`, and `label`. Used on the Overview page for portal and product breakdowns.

---

### `components/tables/`

#### `data-table.tsx` — Scraping Status Table
Uses shadcn `<Table>` components. Status column uses Badge with a variant map:
```ts
const STATUS_VARIANT = {
  success:    "success",
  completed:  "success",
  running:    "default",
  pending:    "warning",
  failed:     "danger",
  error:      "danger",
};
```

---

### `components/sales/`

These are all client components (`"use client"`) — they receive server-fetched data as props and handle local UI state.

#### `sales-filters.tsx`
Filter bar for the Sales page. Syncs filter state to URL search params via `router.push()` — no local state for filter values; URL is the single source of truth.

- **Preset buttons**: shadcn `<Button variant="ghost" size="sm">` with `cn()` override for active state (`bg-orange-500 text-white`)
- **Date inputs**: shadcn `<Input type="date">` with `[color-scheme:dark]` Tailwind arbitrary property to style the native date picker chrome in dark mode
- **Portal selector**: shadcn `<Select>` → `<SelectTrigger>` → `<SelectContent>` → `<SelectItem>`

#### `kpi-strip.tsx`
KPI metric strip. Uses shadcn `<Card>` per metric. No interactive elements.

#### `revenue-trend.tsx`
Recharts `AreaChart` wrapped in shadcn `<Card>`. Day/Week/Month granularity toggle uses shadcn `<Button variant="ghost" size="sm">` with active state override.

#### `portal-breakdown.tsx`
Two-panel layout (bar chart + pie chart) in a grid. Uses shadcn `<Card>` wrappers.

#### `category-chart.tsx`
Horizontal bar chart for sales by category. shadcn `<Card>` wrapper.

#### `target-achievement.tsx`
Month-over-month target tracking panel.

- **Month navigation**: shadcn `<Button variant="ghost" size="icon">` for prev/next chevrons
- **Progress bars**: shadcn `<Progress>` with color override via Tailwind `[&>div]` selector:
  ```tsx
  className={cn("h-2",
    pct >= 100 ? "[&>div]:bg-green-500"
    : pct >= 75 ? "[&>div]:bg-yellow-500"
    : "[&>div]:bg-red-500"
  )}
  ```
  shadcn `<Progress>` doesn't expose indicator color as a prop — the `[&>div]` arbitrary modifier targets the inner indicator div.
- **Achievement badge**: custom `achievementVariant()` maps percentage to Badge variant: `≥100% → success`, `≥75% → warning`, `<75% → danger`

#### `product-table.tsx`
Sortable, searchable product table.

- **Search**: shadcn `<Input>` with `focus-visible:ring-0` to suppress the default focus ring in this context
- **Table markup**: Uses raw `<table>/<thead>/<tbody>/<tr>/<th>/<td>` — **intentional**. The table has complex sortable column headers with inline sort icons via a `ColHead` sub-component. shadcn's `<Table>` adds no value here and would require wrapping every `<th>` in `<TableHead>` anyway.

#### `portal-daily-table.tsx`
Per-portal daily breakdown table. Uses raw HTML table — **intentional**. Multi-level column grouping (portal header spans multiple date columns) requires manual `colSpan` control not easily achievable with shadcn Table.

---

## Page Architecture

| Page | Rendering | Notes |
|------|-----------|-------|
| `/dashboard` | Server Component (RSC) | `revalidate = 300`. Fetches summary, portal, product, and scraping logs in parallel via `Promise.all`. |
| `/dashboard/sales` | Client Component | URL-param driven filters. `Suspense` boundary at page root for `useSearchParams()`. |
| `/dashboard/inventory` | Server Component (RSC) | `revalidate = 300`. Fetches inventory snapshot and low-stock list. |
| `/dashboard/upload` | Client Component | File upload flow with drag-and-drop. No server fetching at render time. |

### Why Sales is Client-Side

Sales uses `useSearchParams()` to read filter state from the URL — this requires a client component. The `Suspense` wrapper at the page level is required by Next.js App Router when using `useSearchParams()` in a child component (to prevent static rendering errors).

### Why Dashboard and Inventory are Server Components

These pages have no user-driven filter state — they always display the same data (last 5 minutes, `revalidate = 300`). RSC means zero client JS for data fetching — faster initial load, no loading spinners.

---

## Key Design Decisions

### 1. shadcn/ui Over Other Libraries

Alternatives considered: MUI, Mantine, Chakra UI.

Chose shadcn because:
- No runtime dependency — components are copied into the repo
- Tailwind-first — identical styling approach to the rest of the codebase
- Full control — customise without fighting library internals or CSS-in-JS specificity
- Dark mode via CSS variables — single toggle, no per-component `colorScheme` props

### 2. CSS Variable Tokens for Theming

All shadcn color tokens use `hsl(var(--...))` in `tailwind.config.js`. This means:
- One change to `--primary` in `globals.css` recolours all buttons, focus rings, and active states globally
- Dark mode is a single `.dark` class on `<html>` — no JS theme provider needed
- The orange brand colour is expressed once (`--primary: 24 95% 53%`) and propagates everywhere automatically

### 3. URL as Filter State (Sales Page)

Sales filters (date range, portal) are stored in URL search params, not React state. Benefits:
- Shareable/bookmarkable filtered views
- Browser back/forward works naturally
- No prop-drilling of filter state through component tree
- Easy to extend with new filter dimensions

### 4. Raw HTML Tables Where Appropriate

`product-table.tsx` and `portal-daily-table.tsx` use raw `<table>` elements. This is intentional:
- Complex multi-column headers with sort icons require fine-grained `<th>` control
- `portal-daily-table.tsx` needs `colSpan` for grouped date columns
- shadcn `<Table>` is a thin semantic wrapper — it doesn't block raw HTML; the decision is about explicitness and control

### 5. Progress Bar Color Override Pattern

shadcn `<Progress>` uses a single indicator div. Color is overridden with:
```tsx
className="[&>div]:bg-green-500"
```
This targets the inner `<div>` (the indicator) via a Tailwind arbitrary CSS selector. It's the correct approach for shadcn Progress — do not use inline `style` or wrap with extra divs.

### 6. No Global State Management

No Redux, Zustand, or Context for UI state. Reasoning:
- Dashboard pages are read-only displays — server-fetched, no mutations needed in UI
- Filter state lives in the URL (no store needed)
- Upload flow is entirely self-contained in one page component
- If shared state becomes necessary, Zustand is the preferred choice (lightweight, no boilerplate)

---

## Patterns & Conventions

### Import Aliases

```ts
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SalesSummary } from "@/lib/api";
```

All imports use `@/` alias (maps to `frontend/`). Never use relative paths for cross-directory imports.

### `cn()` for Conditional Classes

Always use `cn()` (from `@/lib/utils`, re-exports `clsx` + `tailwind-merge`) for conditional class composition:

```tsx
// Correct
className={cn("base-classes", isActive && "active-classes", className)}

// Incorrect
className={`base-classes ${isActive ? "active-classes" : ""}`}
```

`tailwind-merge` inside `cn()` deduplicates conflicting Tailwind classes — critical when overriding shadcn defaults.

### Server vs Client Components

Default to **Server Components**. Add `"use client"` only when the component uses:
- `useState`, `useEffect`, `useCallback`, `useMemo`
- `useRouter`, `useSearchParams`, `usePathname`
- Browser APIs (drag events, file input, etc.)
- Event handlers (`onClick`, `onChange`, etc.)

### Loading States

- **Server pages**: no loading state needed (RSC blocks until data resolves)
- **Client pages**: use shadcn `<Skeleton>` for placeholder shapes during `fetch`
- Pattern in `sales/page.tsx`: `{loading ? <Skeleton className="h-28 rounded-xl" /> : <ActualComponent />}`

### Data Formatting

All currency and number formatting lives in `lib/utils.ts`:
- `formatCurrency(n)` — formats to ₹ with Indian number system
- `formatNumber(n)` — formats with `en-IN` locale

Components like `product-table.tsx` define local `fmtRevenue()` and `fmtNum()` for compact notation (e.g. `₹2.4 Cr`, `₹85 L`) — these are intentionally local to that component because the format differs from the global utility.

---

## Adding New Components

### A new shadcn primitive

```bash
cd frontend
npx shadcn@latest add <component-name>
```

This copies the component into `components/ui/`. Commit the generated file.

### A new page section component

1. Create `components/<domain>/<component-name>.tsx`
2. Default to `"use client"` only if needed (see above)
3. Accept data as typed props — fetch in the page, not the component
4. Use shadcn primitives from `@/components/ui/`
5. Import it in the relevant page

### A new dashboard page

1. Create `app/dashboard/<page-name>/page.tsx`
2. Add `<NavTabs />` in the page header (import from `@/components/ui/nav-tabs`)
3. Add the route to `NAV_ITEMS` in `components/ui/nav-tabs.tsx`
4. Use `export const revalidate = 300` for data pages, or `"use client"` for interactive pages
