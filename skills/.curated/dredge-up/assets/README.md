# dredge-up export assets

`share-export.css` and `share-export.js` are extracted **verbatim** from the
installed `@github/copilot` CLI bundle (`app.js`), so the dredge-up HTML export
matches Copilot CLI's own `/share html` (a.k.a. `/export`) interactive
conversation export — dark GitHub (Primer) theme, sticky header, type-filter
pills, search, collapsible entries, sidebar map, jump-nav.

- `share-export.css` = bundle `lFs` (Primer light) + `cFs` (Primer dark) +
  the custom tail of `mFs()`.
- `share-export.js` = bundle `pFs()` (the IIFE wiring up all interactivity).

`scripts/dump_session.py` reproduces the same DOM that this CSS/JS expects
(`.sticky-header`, `.filter-pill[data-filter-type]`, `.entry.border-*`,
`.entry-header/-icon/-number/-label/-time`, `.entry-body`, `.user-text`,
`.markdown-body`, `#search-input`, `#sidebar`, `.main-container`, `.jump-btn`…),
with visible labels localised to Chinese. The JS filters on `data-type`
(English) and only reads `.entry-label` text for the sidebar, so localised
labels are safe.

To refresh after a Copilot CLI upgrade, run `node scripts/extract_assets.js`
(auto-locates the global `@github/copilot/app.js`, or pass its path). It slices
the `lFs` / `cFs` / `mFs` / `pFs` template literals and **evaluates** them, so
the doubled backslashes the bundle stores on disk (`\\u2600`, regex `\\b`,
`\\n`, …) collapse to the real strings the bundle itself emits. Copying the raw
bytes instead leaves them doubled and breaks the theme toggle, search and the
syntax highlighter — re-run the extractor, never hand-edit the assets.

This is the **conversation** exporter only; the bundle's separate *research*
exporter (`/share html research`) is intentionally not used.
