# HackNex

Evidence-first handwriting review workspace for HACKNEX 2026, PS04.

## Structure

- `frontend/`: Next.js App Router, React, TypeScript and Lucide icons.
- `backend/`: reserved for the next phase; no backend implementation yet.

## Start

From `frontend`, run `npm install` and `npm run dev`. Open http://localhost:3000.

For production, run `npm run build`, followed by `npm start`.

The active project is `B:\Hackathon\hancknex`. Dependencies are pinned and the frontend has its own `package-lock.json`. Use `npm ci` for repeatable installations.

Run `npm test`, `npm run typecheck` and `npm run build` from `frontend` to validate changes. Regression tests cover file limits, saved-state validation, and safe region corrections when text is duplicated or manually edited.

## Delivered screens

1. Overview with document summary, sample-review progress and product introduction.
2. Documents with search, status filtering and sorting.
3. Source/transcription review workspace, zoom/rotate, region selection, candidate comparison, manual decisions, illegibility marking, editing and activity history.
4. Evaluation workspace with metric/subset controls, baseline structure and honest empty states.
5. Settings with reviewer identity, language defaults and evidence overlay preferences.
6. Accessible native dialogs for file intake, help, notifications and exports.

## Real frontend behavior

- PNG/JPEG/WebP/PDF file intake, one file at a time, maximum 20 MB.
- Required title and structured document metadata.
- Local previews and object URL cleanup.
- Sample review decisions and settings persist in localStorage.
- TXT transcript and JSON audit export with draft/demo labels.
- Completion is blocked until all three sample regions have a decision.
- Responsive navigation, native dialog focus containment, focus indicators, skip link, labels, reduced-motion support and textual error notices.

## Deliberate boundaries

This is a frontend implementation, not an OCR service. No uploaded file receives fabricated recognition results. Only the field-notes sample has an illustrative transcript and interactive regions; its source artwork is not benchmark data. The two other seeded library entries demonstrate unprocessed states. Uploaded originals are session-only and disappear on reload. Review decisions remain in the browser and are not cloud-synchronized. Authentication, team permissions, server storage, processing jobs, OCR and evaluation execution belong to the backend phase. Language selection is metadata, not a claim of recognition support.

The interface follows accessibility-oriented patterns, but has not received a formal WCAG audit. Do not describe it as certified or production-hardened.

## Development note

Webpack and `next/babel` are configured because the sandbox's Windows path permissions caused native SWC canonicalization failures. This is a documented Next.js fallback. Once outside the restricted environment, evaluate removing `.babelrc` and using the default compiler after running the checks again.

See `frontend/docs/backend-contract.md`, `frontend/docs/design-research.md` and `frontend/docs/validation.md`.
