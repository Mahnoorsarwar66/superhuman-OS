# Team workspace design

The requested correction restores contrast without a full dark theme. Forest-green navigation and conversation rails establish location; light work surfaces preserve long-form readability. Existing brand colours and local font stacks remain.

The Team list previously combined employee filtering, repeated cards, a prominent conversation-creation form and navigation to a separate room view. The new layout keeps a stable people/project/recent-conversation rail beside the list or room. Conversation creation is disclosed when needed. Single-employee rooms and project-linked rooms retain their actual semantics; no multi-agent conversation, presence indicator or unread count is fabricated.

A presentation adapter captures the exact guarded v1.34 room template and replaces its introductory heading with a compact portrait/context header. It retains the existing data-room root, transcript/proposal/live-status targets, submission key, draft attributes, disabled states, form endpoints, hidden values and action controls. Native links/forms still work without JavaScript. Existing polling and dictation remain authoritative; the additional script only manages responsive disclosure and reading position.

The portrait defect came from the old `.ux-avatar:after` bot-face drawing, which remained active after adding raster portraits. Employee cards now use a separate portrait-only wrapper; defensive scoped pseudo-element rules prevent the legacy drawing from returning. Images are reused unchanged, not regenerated.

No database schema, model, worker, source access, budget mathematics, employee permissions, conversation association or milestone creation workflow is changed. The project-channel filter reads exact project kind/id associations. The existing seven-milestone endorsement blueprint remains distinct from ordinary project creation.

Design follows the previously read Sites skill's task-first, accessible, responsive guidance and the prior NN/g/WAI guidance for progressive disclosure, recognition, labels and native controls. Browser-control skill availability remained absent, so new verification is limited to native route/form/DOM tests, CSS/JavaScript checks and the owner's device acceptance checklist; no real-browser visual pass is claimed.
