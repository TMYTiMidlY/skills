# Template Resources (upstream-shipped, read-only)

> **Read first.** Everything under `${SKILL_DIR}/templates/` is the **upstream-shipped sample / read-only asset library** that ships with the skill:
>
> - `brands/`, `layouts/`, `decks/` — **sample libraries**. Your editable template library lives at `$PPT_MASTER_TEMPLATES_DIR/{brands,layouts,decks}/` (typically `~/ppt-projects/templates/{brands,layouts,decks}/`); `register_template.py` writes there. The samples in this directory are reference material — copy one into your library as a starting point, or pass any one of these sample directories directly to SKILL.md Step 3 as a brand / layout / deck path.
> - `charts/`, `icons/`, `design_spec_reference.md`, `spec_lock_reference.md` — **shipped assets and references** that all projects consume directly from `${SKILL_DIR}/templates/`. No env-var indirection.

## Design Specification & Outline Reference

`design_spec_reference.md` is an all-in-one reference template for defining:
1.  **Visual Specifications**: Canvas dimensions, color scheme, typography, layout principles
2.  **Content Outline**: Slide-by-slide page structure planning
3.  **Technical Constraints**: Hard requirements for SVG generation and PPT compatibility

[View Design Spec Reference](./design_spec_reference.md)

## Page Layout Templates

The `layouts/` directory contains pre-built page layout templates organized by design style:

- **General**: Versatile modern style, clean and flexible
- **Consultant**: Consulting style, professional and structured
- **Consultant Top**: Top-tier consulting style (MBB-level)
- **Academic Defense**: Academic defense style, research-oriented

- **Human browsing**: [layouts/README.md](./layouts/README.md)
- **Slim lookup (discovery only)**: [layouts/layouts_index.json](./layouts/layouts_index.json) — used to answer "what templates exist?". Step 3 triggers on an explicit directory path supplied by the user, not on names from this index.

## Brand Identity Presets

The `brands/` directory holds brand-only templates: identity bundles (color / typography / logo / voice / icon style) without an SVG page roster. Brands follow the **same explicit-path trigger rule as layout templates** — at SKILL.md Step 3 the user supplies the brand directory path to apply it; bare brand names never trigger. Both layout and brand inputs land in the same project directory (`<project_path>/templates/`). When supplied together, Step 3 fuses them into a single `design_spec.md` (brand wins on identity tokens, layout wins on page structure) — see `SKILL.md` Step 3 for the precedence table.

A brand is structurally a layout template minus its page roster. Use a brand when the user wants identity locking with free page layout; use a layout template when fixed page structures are also required.

- **Human browsing**: [brands/README.md](./brands/README.md)
- **Discovery index (no trigger)**: [brands/brands_index.json](./brands/brands_index.json) — answers "what brands exist?"; Step 3 still requires an explicit directory path from the user
- **Creation workflow**: [`../workflows/create-brand.md`](../workflows/create-brand.md)

## Visualization Templates

The `charts/` directory contains 57 standardized visualization templates. For backward compatibility, the directory name remains `charts/`, but its scope includes charts, infographics, process diagrams, relationship diagrams, strategic frameworks, and system architecture diagrams:

- KPI Cards
- Bar Chart / Stacked Bar Chart
- Line Chart / Dual-Axis Line Chart
- Donut Chart
- Radar Chart
- Funnel Chart
- Matrix (2x2)
- Timeline
- Gantt Chart
- Process Flow
- Org Chart
- Layered Architecture / Module Composition / Hub with Described Spokes / Pipeline with Stages / Client-Server Flow

- **Library index (single source of truth)**: [charts/charts_index.json](./charts/charts_index.json)
- **Directory overview**: [charts/README.md](./charts/README.md)

## Icon Library

The `icons/` directory contains 11,600+ vector icons across five libraries:

| Library | Style | Count |
|---------|-------|-------|
| `chunk-filled` | fill / straight-line geometry | 640 |
| `tabler-filled` | fill / bezier-curve forms | 1000+ |
| `tabler-outline` | stroke / line | 5000+ |
| `phosphor-duotone` | duotone / single color + 0.2 opacity backplate | 1200+ |
| `simple-icons` | brand logos (company / product marks) | 3400+ |

- **Usage & style rules**: [icons/README.md](./icons/README.md)
- **Search icons**: `ls ${SKILL_DIR}/templates/icons/<library>/ | grep <keyword>`
