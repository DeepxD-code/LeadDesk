# LeadDesk design system

## Product read

LeadDesk is an operations workspace for team leads, members, HR, interviewers, testers and developers.
The mode is **Operate**: information must be scanable, familiar and task-focused. Brand expression comes from
precision, not decorative effects.

## Visual language

- Base surfaces: warm off-white `#f6f4f0`, white content, and a near-black navigation rail.
- Primary accent: muted blue `#315d98` on light surfaces and `#5b8fd6` on the rail.
- Semantic colors: green for success, amber for attention, red for errors or overdue work, blue for information.
- Typography: Segoe UI Variable Text or the platform Segoe UI system stack. No external font dependency.
- Heading scale: 22px page title, 17px section title, 15px subsection title.
- Radius: 7-8px controls and rows, 10px panels, 99px status pills.
- Shadow: reserved for raised content, sticky surfaces and overlays. Normal cards use a one-pixel border.

## Layout

- Desktop navigation is a collapsible 252px rail with grouped links and role-aware project queues.
- The rail reduces to a 60px icon rail at tablet widths and becomes a drawer with bottom navigation on phones.
- The top bar is sticky and at least 54px tall; identity and account actions live in the rail footer.
- Main content uses 26px horizontal and 22px vertical spacing on desktop.
- The overview uses a compact metric strip, segmented chart tabs and stacked attention panels.
- At intermediate widths, overview panels stack while attention panels use two columns; mobile switches to a drawer and bottom tabs at 760px.
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
