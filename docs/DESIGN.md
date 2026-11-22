# LeadDesk design system

## Product read

LeadDesk is an operations workspace for team leads, members, HR, interviewers, testers and developers.
The mode is **Operate**: information must be scanable, familiar and task-focused. Brand expression comes from
precision, not decorative effects.

## Visual language

- Base surfaces: warm-neutral or cool-neutral off-white, white cards and dark slate navigation.
- Primary accent: muted blue `#315d98`, used for primary actions and active decisions.
- Semantic colors: green for success, amber for attention, red for errors or overdue work, blue for information.
- Typography: Segoe UI Variable Text or the platform Segoe UI system stack. No external font dependency.
- Heading scale: 22px page title, 17px section title, 15px subsection title.
- Radius: 8px controls and cards, 10px dashboard panels, 99px status pills.
- Shadow: reserved for raised content, sticky surfaces and overlays. Normal cards use a one-pixel border.

## Layout

- Desktop navigation is a 224px sticky sidebar.
- The top bar is sticky and at least 58px tall.
- Main content uses 26px horizontal and 22px vertical spacing on desktop.
- The overview uses a compact metric strip, segmented chart tabs and stacked attention panels.
- At intermediate widths, overview panels stack while attention panels use two columns; mobile switches to horizontal navigation and single-column panels at 760px.
- One primary action per page or dialog. Put secondary actions beside it or in a clear menu.

## Interaction

- Every control has default, hover, active and keyboard-focus states.
- Button press feedback is a 3% scale reduction for 140ms.
- Interface transitions use the custom ease-out curve `cubic-bezier(.23,1,.32,1)`.
- Dialogs and overlays remain keyboard dismissible.
- Respect `prefers-reduced-motion`.

## Content

- Use verbs for actions: Sign in, Save changes, Post discussion, Add reply.
- Avoid em dashes in interface copy.
- Status text must be explicit and consistent.
- User-provided names and messages must truncate or wrap safely; never let them push actions off screen.
