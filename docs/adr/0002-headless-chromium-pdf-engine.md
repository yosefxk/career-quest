# ADR 0002: Headless Chromium & CSS Paged Media for ATS Resume Compilation

## Status
Accepted

## Context
Standard PDF generators (such as ReportLab, WeasyPrint, or wkhtmltopdf) often suffer from inconsistent typography rendering, poor CSS Flexbox/Grid support, and unpredictable multi-page spillover. ATS resume formatting requires strict single-page bounding boxes (`@page { size: letter; margin: 0; }`), exact line-height calibration, and clean extractable text layers.

## Decision
We selected **Playwright Headless Chromium** with Jinja2 HTML templates and CSS Paged Media.

## Consequences
### Positive
* **Pixel-Perfect Fidelity**: Modern CSS3 (Flexbox, custom fonts, precise letter spacing) renders identically in both browser preview and exported PDF.
* **ATS Text Layer**: Chromium generates native, extractable PDF text layers that pass Workday and Greenhouse parsers cleanly.
* **Deterministic Layout**: Guarantees single-page letter budget scaling without layout breaks.

### Negative
* Requires Chromium dependencies inside the Docker container (~180MB image layer footprint).
