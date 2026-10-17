# Interface design and implementation

The sidebar identifies the main area. A single contextual navigation row identifies the workspace view. Breadcrumbs identify the record. Project and milestone pages suppress the outer section tabs when they provide their own navigation, avoiding competing consoles.

The visual system uses a local font stack, 16px body text, three heading levels, a shared spacing scale, neutral surfaces, restrained borders and green primary actions. Status chips pair colour with plain text. Desktop keeps the sidebar persistent; mobile enhances the native details/menu control. Tabs wrap on small screens, and calendar month columns adapt without widening the page.

Overview emphasises owner decisions and progress. Project/milestone views separate everyday inspection from configuration. Evidence is split into a source/requirement view, investigations and review standards. Confirmed scope becomes a status instead of another form. Detailed source grants, rationale fields, confirmation checkboxes and technical audit records remain accessible at their decision points.

Existing server-generated fragments are partitioned using a small standard-library HTML parser. It operates on known guarded templates, preserves form actions/hidden values and leaves source/user text intact. Existing business handlers and execution backends remain authoritative. Tests compare legacy action sets with the union of focused views and exercise the actual approval/consent paths.

A presentation adapter removes routine internal milestone reviews from the owner decision queue while keeping strategic gates, exceptional contributor reviews and recovery actions. The same read model powers Overview, Attention and Reviews. No task is approved, cancelled, reassigned or started by this adapter.

HTML validation errors provide recovery links; JSON clients retain the prior error handlers. A same-site, same-record redirect adapter preserves an allowlisted view/panel after successful POSTs. It cannot redirect externally or grant access. All assets remain behind the existing authentication boundary and are served locally. Existing chat refresh, dictation and browser-tab draft protection remain intact.

This package adds no business-data schema, tools, employees, model permissions or external actions. Rollback restores exact v1.32 UI source and preserves business rows; the existing rollback procedure leaves the worker paused. The broader Twin coordination and accepted business-outcome gaps remain outside this interface installation.
