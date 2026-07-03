# Spec Delta: Fix Tab Đề xuất — missing import + runtime errors

## Analysis

**Root cause:** `popup.ts` imports `fetchRecommendationsAndSyncUrl` and `fetchRecommendations` as type-only on line 1-7:
```ts
import type { RecommendationsResponse } from "../lib/recommendations-api.js";
```
The function value import is missing. Runtime error: `fetchRecommendationsAndSyncUrl is not defined`.

Also missing: `fetchRecommendations` (used in `loadRecommendations` load-order logic).

## Fix Requirements

### REQ-RTF-001: Add value imports

`src/popup/popup.ts` — add to existing `recommendations-api` import:

```ts
import type {
  ConsensusChamRow,
  ConsensusStats,
  DeByExpertRow,
  LiveExpertRow,
  RecommendationsResponse,
} from "../lib/recommendations-api.js";
// BUGFIX: add value import
import { fetchRecommendationsAndSyncUrl, fetchRecommendations } from "../lib/recommendations-api.js";
```

### REQ-RTF-002: Verify all runtime callers

Check these function calls in `loadRecommendations()` render path:
- `fetchRecommendationsAndSyncUrl(target, settings)` — dòng 1289, 1315
- `fetchRecommendations` — if used anywhere (check entire file)
- `pushSessionToApi` — dòng 10 đã import đúng
- `pollNowWithTimeout` — defined locally dòng 73
- `setTab`, `refreshUi` — defined locally

### REQ-RTF-003: Verify build output

After fix:
```bash
cd extension && npm run build
```
Check `dist/popup.js` for the function export being included (not tree-shaken away).

### REQ-RTF-004: Test scenarios

1. Open popup → tab Đề xuất → renders data from API (or appropriate error if API offline)
2. Switch back/forth between tabs → no crash
3. "Tải đề xuất" button → re-fetches and re-renders
4. No console error for undefined function names
