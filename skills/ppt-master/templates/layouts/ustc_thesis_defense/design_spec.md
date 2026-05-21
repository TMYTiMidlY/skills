# USTC Thesis Defense Template - Design Specification

> Mirrored from 关贝贝中期答辩 PPTX. Suitable for USTC thesis defense, academic progress reports, and graduation defense presentations.

---

## I. Template Overview

| Property       | Description                                            |
| -------------- | ------------------------------------------------------ |
| **Template Name** | ustc_thesis_defense                                 |
| **Use Cases**  | Thesis defense (midterm/final), academic presentations, research progress reports |
| **Design Tone** | Professional, academic, clean, card-based layout with blue corner decorations |
| **Theme Mode** | Light theme (white background + deep blue accent + shadow card) |

---

## II. Canvas Specification

| Property       | Value                         |
| -------------- | ----------------------------- |
| **Format**     | Standard 16:9                 |
| **Dimensions** | 1280 × 720 px                |
| **viewBox**    | `0 0 1280 720`                |
| **Page Margins** | Left/Right ~42px, Top ~47px, Bottom ~47px |
| **Safe Area**  | x: 42-1237, y: 47-672 (inside the shadow card) |

---

## III. Color Scheme

### Primary Colors

| Role           | Value       | Notes                            |
| -------------- | ----------- | -------------------------------- |
| **Primary Deep Blue** | `#1C4885` | Corner rectangles, card header bar, chapter number circle, page titles |
| **Accent Blue** | `#2E75B6` | In-text keyword highlighting (bold), secondary emphasis |
| **Background White** | `#FFFFFF` | Page main background + card fill |

### Text Colors

| Role           | Value       | Usage                  |
| -------------- | ----------- | ---------------------- |
| **White Text** | `#FFFFFF`   | Text on blue backgrounds (circle numbers, etc.) |
| **Primary Text** | `#000000` | Body content           |
| **Dark Gray Text** | `#262626` | Section subtitles      |
| **Medium Gray** | `#404040`  | Sub-section titles     |
| **Light Gray** | `#808080`  | Subtitle text, decorative lines, footer |

### Decorative

| Element        | Value       | Usage                  |
| -------------- | ----------- | ---------------------- |
| **Shadow card glow** | rgba(0,0,0,0.3) | feGaussianBlur shadow on main card |
| **Separator line** | `#808080` | Horizontal line under titles |

---

## IV. Typography System

### Font Stack

**Primary**: `"微软雅黑", "Microsoft YaHei", sans-serif`
**Cover Title**: `"汉仪大宋简", "微软雅黑", sans-serif`

### Font Size Hierarchy

| Level | Usage            | Size   | Weight  |
| ----- | ---------------- | ------ | ------- |
| H1    | Cover main title | 64px   | Bold    |
| H2    | Chapter number title | 58.67px | Regular |
| H3    | Section title (left bar) | 37.33px | Regular |
| H4    | Sub-section title | 32px   | Regular/Bold |
| Body  | Body text        | 26.67px | Regular |
| Caption | Subtitle/footer | 26.67px | Regular |
| Small | Annotations      | 16px   | Bold    |

---

## V. Signature Visual Elements

### Corner Rectangles
- **Cover/Ending**: Four `#1C4885` rectangles at corners (width ~206, height ~178)
  - Top-left: (25.81, 30.97)
  - Top-right: (1048.26, 30.97)
  - Bottom-left: (25.81, 510.97)
  - Bottom-right: (1048.26, 510.97)
- **Chapter/TOC**: Two `#1C4885` rectangles (top-left + bottom-right only)
- **Content pages**: No corner rectangles; use left vertical blue bar instead

### Shadow Card
- All pages except pure content: white rounded rect with shadow
  - Position: (42.32, ~47), Size: 1195.35 × 625.55
  - rx/ry: 9.81
  - filter: feMorphology dilate + feGaussianBlur shadow

### Left Vertical Bar (Content pages)
- Blue `#1C4885` vertical line, 8px stroke width
- Position: x=83.61, from y=48 to y=114.38

### University Logo
- **image1.jpeg**: USTC seal (~85.68×85.68 px)
- **image2.jpeg**: "中国科学技术大学" text wordmark (~258.41×38.76 px)
- Placement varies by page type:
  - Cover/Ending: top-left at (~86, ~77) + (~199, ~101)
  - Chapter: top-left at (~67, ~75) + (~160, ~101)
  - TOC: top-right at (~877, ~75) + (~970, ~99)
  - Content: top-right seal at (~924, ~29) + wordmark at (~1010, ~53)

### Chapter Number Circle
- Blue `#1C4885` filled ellipse, radius ~83.58
- Centered at (~282, ~338)
- White bold number inside, font-size 184px
- Chapter title to the right, font-size 58.67px in `#1C4885`
- Gray separator line below title

---

## VI. Page Roster

| Page | Type | File | Description |
| ---- | ---- | ---- | ----------- |
| 01 | cover | `01_cover.svg` | Title page with 4-corner blue rects, shadow card, centered thesis title, author info |
| 02 | toc | `02_toc.svg` | Table of contents with numbered blue circles in 2×2 grid |
| 02 | chapter | `02_chapter.svg` | Chapter divider with large numbered circle + section title |
| 03 | content | `03_content.svg` | Content page with left blue bar + section title + body text |
| 04 | ending | `04_ending.svg` | Thank you page with 4-corner blue rects, centered farewell text |

---

## VII. SVG Technical Constraints

- viewBox: `0 0 1280 720`
- All text as `<text>` with `<tspan>` (no `<foreignObject>`)
- Images as `<image>` with `preserveAspectRatio="none"`
- Shadow via SVG `<filter>` (feMorphology + feGaussianBlur + feFlood + feComposite + feMerge)
- No external CSS; all styles inline
- Rounded rectangles via `rx`/`ry` attributes
