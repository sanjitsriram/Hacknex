# Validation record

8 October 2026, restricted Windows session.

## Passed
- TypeScript strict checking with `tsc --noEmit`.
- Next.js production webpack compilation (39.8 seconds), followed by Next.js TypeScript checking.
- Six upload validation checks: valid image, valid PDF at 20 MB, over-limit file, empty file, unsupported SVG, unsupported executable MIME type.
- The application index was prerendered to `.next/server/app/index.html` during the build.

## Not completed
- Full production build: static generation failed while Next.js attempted to create its built-in `_not-found` output directory, with EPERM in the restricted environment. This is not a successful full build.
- Browser/visual QA and interaction automation: the in-app browser could not connect to the local preview. A direct request reported a socket access permission denial. No visual verification is claimed.
- Clean dependency installation: registry DNS access was blocked. Locally installed dependencies were used; top-level versions match package.json.
- Requested B-drive placement: directory creation returned access denied.

## Checks to run in an unrestricted workspace
1. Run a clean `npm install`, `npm run typecheck`, `npm run build`, `npm run dev`.
2. At desktop and mobile widths, inspect the overview, sidebar, document list, review split panes, dialogs and evaluation/settings screens.
3. Upload a valid image and a PDF; verify preview. Reject empty, unsupported and >20 MB files.
4. Resolve sample regions, edit text, complete the review, export TXT/JSON, reload and confirm persistence. Editing after completion must reopen the review state.
5. Verify keyboard navigation, modal focus containment, visible focus, label/error announcement and no horizontal page overflow.
6. Verify document search/filter/sort and settings persistence. Uploaded file references should not survive reload.

No real OCR, model accuracy or benchmark improvement has been tested. The illustrative sample is labeled throughout the UI.
