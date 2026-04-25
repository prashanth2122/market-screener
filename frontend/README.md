# Frontend Module

Purpose:
- Personal dashboard for screener rankings, symbol detail, and alert visibility.

Directory layout:
- `src/app/` Next.js App Router pages and layouts
- `public/` static assets
- `tests/` UI/component test area

Stack baseline:
- Next.js 14
- TypeScript (strict mode)
- React 18

## Day 75 Delivery

- Implemented screener table view in `src/app/page.tsx`.
- Wired data fetch to backend screener API (`GET /api/v1/screener`) via `src/lib/screener.ts`.
- Added robust page states for API error, empty rows, and populated ranking table.
- Added responsive table styling and signal/risk badges in `src/app/globals.css`.

### Optional frontend API base override

By default the frontend fetches from `http://localhost:8000`.
To override:
- `MARKET_SCREENER_API_BASE_URL` (preferred, server-side)
- or `NEXT_PUBLIC_API_BASE_URL`

## Quickstart

From repo root:

```powershell
cd .\frontend
npm install
npm run dev
```

Quality checks:

```powershell
npm run typecheck
npm run lint
npm run build
```
