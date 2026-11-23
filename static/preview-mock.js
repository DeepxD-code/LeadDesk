(() => {
  "use strict";
  const isPreviewPage = document.querySelector('meta[name="leaddesk-preview"]') || new URLSearchParams(location.search).has("preview");
  if (!isPreviewPage) return;

  const pad = (value) => String(value).padStart(2, "0");
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const localTime = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  const dateAt = (offset, hour = 10, minute = 0) => {
    const date = new Date();
    date.setDate(date.getDate() + offset);
    date.setHours(hour, minute, 0, 0);
    return localTime(date);
  };
  const now = localTime(new Date());
  const inDays = (days, hour = 10, minute = 0) => dateAt(days, hour, minute);

  const members = [
    { id: 1, name: "Riya Sharma", shift: "Morning", department: "Operations" },
    { id: 2, name: "Kabir Soni", shift: "Morning", department: "Operations" },
    { id: 3, name: "Maya Nair", shift: "Evening", department: "Operations" },
    { id: 4, name: "Rohan Desai", shift: "Evening", department: "Operations" },
    { id: 5, name: "Ira Shah", shift: "Night", department: "Operations" },
    { id: 6, name: "Devika Rao", shift: "Morning", department: "Finance" },
    { id: 7, name: "Neil Khanna", shift: "Evening", department: "Finance" },
    { id: 8, name: "Aarav Menon", shift: "Night", department: "Finance" },
  ];
  const users = [
    { id: 900, username: "lead", name: "Priya Iyer", role: "lead", role_label: "Team Lead" },
    ...members.map((member, index) => ({
      id: member.id,
      username: `m${String(index + 1).padStart(2, "0")}`,
      name: member.name,
      role: "member",
      role_label: "Team Member",
      department: member.department,
      shift: member.shift,
      employee_id: `EMP-${1001 + index}`,
    })),
    { id: 910, username: "hr1", name: "Anika Bose", role: "hr", role_label: "HR", department: "Operations" },
    { id: 911, username: "admin", name: "Naveen Patel", role: "admin", role_label: "Administrator" },
    { id: 912, username: "int1", name: "Sana Kapoor", role: "interviewer", role_label: "Interviewer" },
    { id: 913, username: "tester", name: "Milan Dutta", role: "tester", role_label: "Tester" },
    { id: 914, username: "dev", name: "Aditi Verma", role: "developer", role_label: "Developer" },
  ];
  const taskTypes = ["Reconciliation", "Claims review", "Data entry", "Quality check"];
  const statuses = ["pending", "in_progress", "escalated", "done"];
  const priorities = ["low", "medium", "high", "urgent"];
  let activeUser = users[0];
  let nextTaskId = 33;

  const tasks = [
    ["Match settlement batch 1842", 1, "Reconciliation", "high", "in_progress", -1, "Compare the bank settlement file with the ledger and flag any unmatched lines."],
    ["Review duplicate payment claims", 2, "Claims review", "urgent", "escalated", -2, "Two claims share a reference number. Confirm the original before approving either."],
    ["Reconcile partner account 73", 3, "Reconciliation", "medium", "pending", 0, "Use the daily reconciliation checklist and attach the variance report."],
    ["Validate supplier tax records", 4, "Quality check", "medium", "in_progress", 1, "Check the latest supplier records against the approved registry."],
    ["Enter returns from 21 Nov", 1, "Data entry", "low", "pending", 1, "Enter the returns from the shift handover sheet."],
    ["Check refund exception queue", 5, "Claims review", "high", "in_progress", -1, "Review the exception queue and record the reason for each hold."],
    ["Verify cash-close totals", 6, "Reconciliation", "urgent", "pending", 0, "Compare the cash-close totals with the submitted end-of-day report."],
    ["Resolve invoice mismatch 5081", 7, "Quality check", "high", "escalated", -3, "The invoice total differs from the purchase order. Ask the owner for a corrected copy."],
    ["Review onboarding documents", 8, "Data entry", "medium", "in_progress", 2, "Confirm required fields are present before marking the record complete."],
    ["Reconcile wallet transfers", 2, "Reconciliation", "medium", "pending", 1, "Match wallet transfers to the transaction export."],
    ["Audit claim sample C-214", 3, "Claims review", "low", "done", -4, "Sample review complete; notes are attached to the claim."],
    ["Check regional batch totals", 4, "Quality check", "high", "in_progress", 0, "Compare region totals and report any variance above the daily threshold."],
    ["Enter approved adjustments", 5, "Data entry", "medium", "pending", 2, "Enter adjustments approved by the shift lead."],
    ["Match card settlement file", 6, "Reconciliation", "urgent", "in_progress", -1, "Match the card settlement file and identify reversals."],
    ["Review account change request", 7, "Claims review", "medium", "done", -2, "Review completed and the request was returned with notes."],
    ["Verify new vendor records", 8, "Quality check", "low", "pending", 1, "Check the vendor profile for duplicate tax identifiers."],
    ["Close weekly variance report", 1, "Reconciliation", "high", "in_progress", 2, "Summarize unresolved variances and send the report to the lead."],
    ["Review flagged transfers", 2, "Claims review", "urgent", "pending", -1, "Confirm the supporting documents for each flagged transfer."],
    ["Enter service credits", 3, "Data entry", "medium", "done", -5, "The approved credits have been entered and checked."],
    ["Check refund approval trail", 4, "Quality check", "high", "pending", 1, "Verify that each refund has the required approval record."],
    ["Reconcile cash adjustments", 5, "Reconciliation", "medium", "done", -3, "The adjustment entries match the close report."],
    ["Review open invoice disputes", 6, "Claims review", "high", "in_progress", 2, "Check the newest responses and update the dispute tracker."],
    ["Validate return references", 7, "Quality check", "low", "done", -6, "Completed with no duplicate references found."],
    ["Enter chargeback evidence", 8, "Data entry", "urgent", "pending", 0, "Add the received evidence to the chargeback record."],
    ["Match payout exceptions", 1, "Reconciliation", "medium", "done", -2, "The payout exceptions were matched and closed."],
    ["Review late settlement file", 1, "Reconciliation", "high", "pending", 1, "Confirm the business date and match the remaining settlement lines."],
    ["Check claim evidence for case 921", 1, "Claims review", "medium", "in_progress", 2, "Confirm each attachment is linked to the correct claim."],
    ["Enter approved fee adjustments", 1, "Data entry", "low", "pending", 2, "Enter fee adjustments that have already been approved."],
    ["Review duplicate transfer flags", 2, "Claims review", "urgent", "pending", -1, "Keep matching references on hold and ask the lead to confirm the original."],
    ["Reconcile partner batch 209", 2, "Reconciliation", "high", "in_progress", 1, "Compare the partner export with the ledger and list unresolved variances."],
    ["Validate payment return notes", 2, "Quality check", "medium", "pending", 2, "Check that each return has a complete reason and reference."],
    ["Prepare unassigned handover review", null, "Quality check", "low", "pending", 1, "Assign this sample task to a teammate before the handover."],
  ].map(([title, assigneeId, taskType, priority, status, deadlineOffset, description], index) => {
    const member = members.find((item) => item.id === assigneeId);
    const deadline = inDays(deadlineOffset, 11 + (index % 5));
    const due = new Date(deadline);
    const today = new Date(now);
    return {
      id: index + 1,
      title,
      description,
      task_type: taskType,
      priority,
      status,
      assignee_id: assigneeId,
      assignee_name: member?.name || null,
      deadline,
      overdue: status !== "done" && due < today && due.toDateString() !== today.toDateString(),
      due_today: status !== "done" && due.toDateString() === today.toDateString(),
      created_by_name: "Priya Iyer",
      done_at: status === "done" ? inDays(-Math.max(1, Math.abs(deadlineOffset)), 16) : null,
    };
  });

  const taskEvents = (task) => [
    { action: "created", actor_name: "Priya Iyer", at: dateAt(-5, 9), from_value: "", to_value: task.title },
    { action: "assigned", actor_name: "Priya Iyer", at: dateAt(-4, 10), from_value: "", to_value: task.assignee_name },
    { action: "status", actor_name: task.assignee_name, at: dateAt(-1, 11), from_value: "pending", to_value: task.status },
  ];

  const sopDocs = [
    { id: 1, title: "Daily Reconciliation Guide", filename: "daily-reconciliation.pdf", n_sections: 8, uploaded_at: dateAt(-18), uploaded_by: "Priya Iyer" },
    { id: 2, title: "Claims Review Procedure", filename: "claims-review.docx", n_sections: 6, uploaded_at: dateAt(-12), uploaded_by: "Priya Iyer" },
    { id: 3, title: "Refund Approval Matrix", filename: "refund-approvals.pdf", n_sections: 4, uploaded_at: dateAt(-7), uploaded_by: "Priya Iyer" },
  ];
  const sopSections = {
    1: [
      { section: "1. Prepare the source files", text: "Confirm the settlement file is for the correct business date. Keep the original export unchanged and save a working copy." },
      { section: "2. Match transactions", text: "Match each settlement line to a ledger entry by reference and amount. Record unmatched items in the variance sheet." },
      { section: "3. Escalate a variance", text: "Ask the team lead to review any unexplained variance or duplicate reference before closing the batch." },
    ],
    2: [
      { section: "1. Check the claim", text: "Confirm the claimant, transaction reference, amount, and supporting evidence before changing the claim status." },
      { section: "2. Duplicate references", text: "Do not approve either item when two claims share a reference. Keep both on hold and ask the team lead to confirm the original." },
    ],
    3: [
      { section: "1. Standard approval", text: "Refunds up to ₹10,000 require one authorized reviewer. Record the approval reference in the claim." },
      { section: "2. Higher-value refunds", text: "Refunds above ₹10,000 require approval from the operations lead and the finance approver before processing." },
    ],
  };
  const questions = [
    { id: 1, question: "What do I do when error 402 appears?", asked_by: "Maya Nair", user_id: 3, asked_at: dateAt(-1, 13), status: "answered", answer: "Pause the batch, check the settlement reference, and retry once after confirming the source file is current.", top_score: 0.91, language: "en", helpful: 1, sources: [{ doc: "Daily Reconciliation Guide", section: "2. Match transactions", excerpt: "Match each settlement line to a ledger entry by reference and amount." }] },
    { id: 2, question: "What is the office Wi-Fi password?", asked_by: "Riya Sharma", user_id: 1, asked_at: dateAt(-1, 15), status: "needs_lead", answer: "", top_score: 0.08, language: "en", helpful: null, sources: [] },
    { id: 3, question: "Who approves a refund above ₹10,000?", asked_by: "Kabir Soni", user_id: 2, asked_at: dateAt(-2, 12), status: "resolved", answer: "", lead_answer: "The operations lead and finance approver both need to approve it.", resolved_by: "Priya Iyer", resolved_by_name: "Priya Iyer", resolved_at: dateAt(-1, 10), top_score: 0.42, language: "en", helpful: null, sources: [] },
  ];
  const forumPosts = [
    { id: 1, title: "Shift handover: reconciliation checklist", body: "I added the source-file checks we discussed. Please flag anything that should be in the SOP as well.", author_name: "Priya Iyer", author_role_label: "Team Lead", updated_at: dateAt(-1, 16), created_at: dateAt(-2, 11), reply_count: 2 },
    { id: 2, title: "Tip for spotting duplicate references", body: "Filtering the export by reference number first makes repeated claim IDs easier to catch before review.", author_name: "Riya Sharma", author_role_label: "Team Member", updated_at: dateAt(-2, 14), created_at: dateAt(-2, 14), reply_count: 1 },
    { id: 3, title: "Interview panel availability next week", body: "Please add your open times to Availability so candidates can choose a slot without email back-and-forth.", author_name: "Sana Kapoor", author_role_label: "Interviewer", updated_at: dateAt(-3, 10), created_at: dateAt(-3, 10), reply_count: 0 },
  ];
  const forumReplies = {
    1: [
      { author_name: "Maya Nair", author_role_label: "Team Member", created_at: dateAt(-1, 16), body: "The check for the business date helped. I would include that in the guide." },
      { author_name: "Kabir Soni", author_role_label: "Team Member", created_at: dateAt(-1, 17), body: "Agree. I also look for a repeated settlement reference before I close the batch." },
    ],
    2: [{ author_name: "Priya Iyer", author_role_label: "Team Lead", created_at: dateAt(-2, 15), body: "Good call. I will add a short note to the claims procedure." }],
    3: [],
  };

  const employees = members.map((member, index) => ({
    employee_id: `EMP-${1001 + index}`,
    name: member.name,
    department: member.department,
  }));
  const docTypes = {
    offer_letter: "Offer letter",
    identity: "Identity document",
    pay_slip: "Pay slip",
    policy_acknowledgement: "Policy acknowledgement",
    other: "Other",
  };
  let vaultDocs = [
    { id: 501, employee_id: "EMP-1001", employee_name: "Riya Sharma", department: "Operations", original_name: "offer-letter-riya.pdf", title: "Offer letter · Riya Sharma", doc_type: "offer_letter", doc_type_label: "Offer letter", doc_type_source: "rule", type_reason: "Filename match", uploaded_at: dateAt(-35), uploaded_by_name: "Anika Bose", retention_until: "2027-11-30", retention_expired: false, ocr_used: false, mime: "application/pdf", text: "Offer letter for Riya Sharma. Department: Operations. Start date: 12 February." },
    { id: 502, employee_id: "EMP-1002", employee_name: "Kabir Soni", department: "Operations", original_name: "identity-kabir.jpg", title: "Identity document · Kabir Soni", doc_type: "identity", doc_type_label: "Identity document", doc_type_source: "rule", type_reason: "Image scan", uploaded_at: dateAt(-28), uploaded_by_name: "Anika Bose", retention_until: "2028-03-15", retention_expired: false, ocr_used: true, mime: "image/jpeg", text: "Identity document scan for Kabir Soni. Employee number EMP-1002." },
    { id: 503, employee_id: "EMP-1003", employee_name: "Maya Nair", department: "Operations", original_name: "payslip-maya-nov.pdf", title: "Pay slip · Maya Nair", doc_type: "pay_slip", doc_type_label: "Pay slip", doc_type_source: "manual", type_reason: "Reviewed by HR", uploaded_at: dateAt(-9), uploaded_by_name: "Anika Bose", retention_until: "2027-11-30", retention_expired: false, ocr_used: false, mime: "application/pdf", text: "Monthly pay statement for Maya Nair. Payroll period: November." },
    { id: 504, employee_id: "EMP-1004", employee_name: "Rohan Desai", department: "Operations", original_name: "policy-acknowledgement.txt", title: "Policy acknowledgement · Rohan Desai", doc_type: "policy_acknowledgement", doc_type_label: "Policy acknowledgement", doc_type_source: "rule", type_reason: "Filename match", uploaded_at: dateAt(-5), uploaded_by_name: "Anika Bose", retention_until: "2027-12-01", retention_expired: false, ocr_used: false, mime: "text/plain", text: "Rohan Desai confirmed receipt of the operations policy." },
    { id: 505, employee_id: "EMP-1006", employee_name: "Devika Rao", department: "Finance", original_name: "offer-letter-devika.pdf", title: "Offer letter · Devika Rao", doc_type: "offer_letter", doc_type_label: "Offer letter", doc_type_source: "rule", type_reason: "Filename match", uploaded_at: dateAt(-19), uploaded_by_name: "Anika Bose", retention_until: "2027-08-20", retention_expired: false, ocr_used: false, mime: "application/pdf", text: "Offer letter for Devika Rao. Department: Finance." },
  ];
  let deleteRequests = [
    { id: 1, doc_id: 503, original_name: "payslip-maya-nov.pdf", requested_by_name: "Anika Bose", requested_at: dateAt(-1), reason: "Uploaded to the wrong employee record", status: "pending" },
  ];
  const auditEntries = [
    { at: dateAt(-1, 16), username: "anika.bose", role: "hr", action: "upload", doc_id: 504, outcome: "ok", detail: "Policy acknowledgement" },
    { at: dateAt(-1, 15), username: "priya.iyer", role: "lead", action: "search", doc_id: null, outcome: "ok", detail: "Searched documents" },
    { at: dateAt(-2, 11), username: "milan.dutta", role: "member", action: "view", doc_id: 505, outcome: "denied", detail: "Department scope did not permit access" },
    { at: dateAt(-2, 10), username: "naveen.patel", role: "admin", action: "download", doc_id: 501, outcome: "ok", detail: "Watermarked copy" },
  ];

  const recruiters = [{ id: 910, name: "Anika Bose" }, { id: 911, name: "Priya Iyer" }];
  const interviewers = [{ id: 912, name: "Sana Kapoor" }, { id: 915, name: "Omar Fernandes" }];
  let interviews = [
    { id: 701, candidate_id: 301, candidate_name: "Meera Kulkarni", candidate_email: "meera.kulkarni@example.test", recruiter_id: 910, recruiter_name: "Anika Bose", role_title: "Operations Associate", round_name: "Round 1", interviewer_id: 912, interviewer_name: "Sana Kapoor", board_status: "scheduled", status: "scheduled", start: inDays(1, 11), end: inDays(1, 11, 45), location: "https://meet.example.test/ops-701", length_min: 45, reschedule_count: 0, link: "https://leaddesk-preview.vercel.app/book/demo-701" },
    { id: 702, candidate_id: 302, candidate_name: "Ishaan Mehta", candidate_email: "ishaan.mehta@example.test", recruiter_id: 910, recruiter_name: "Anika Bose", role_title: "Claims Reviewer", round_name: "Technical", interviewer_id: 912, interviewer_name: "Sana Kapoor", board_status: "feedback_pending", status: "scheduled", start: inDays(-1, 14), end: inDays(-1, 14, 45), location: "https://meet.example.test/ops-702", length_min: 45, reschedule_count: 0, link: "https://leaddesk-preview.vercel.app/book/demo-702" },
    { id: 703, candidate_id: 303, candidate_name: "Tara Joseph", candidate_email: "tara.joseph@example.test", recruiter_id: 911, recruiter_name: "Priya Iyer", role_title: "Finance Associate", round_name: "Round 2", interviewer_id: 915, interviewer_name: "Omar Fernandes", board_status: "rescheduled", status: "scheduled", start: inDays(3, 15), end: inDays(3, 15, 45), location: "Meeting room 2", length_min: 45, reschedule_count: 1, link: "https://leaddesk-preview.vercel.app/book/demo-703" },
    { id: 704, candidate_id: 304, candidate_name: "Arjun Pillai", candidate_email: "arjun.pillai@example.test", recruiter_id: 910, recruiter_name: "Anika Bose", role_title: "Operations Associate", round_name: "Round 1", interviewer_id: 915, interviewer_name: "Omar Fernandes", board_status: "invited", status: "invited", start: null, end: null, location: "", length_min: 30, reschedule_count: 0, link: "https://leaddesk-preview.vercel.app/book/demo-704" },
    { id: 705, candidate_id: 305, candidate_name: "Nisha Rao", candidate_email: "nisha.rao@example.test", recruiter_id: 911, recruiter_name: "Priya Iyer", role_title: "Claims Reviewer", round_name: "Round 1", interviewer_id: 912, interviewer_name: "Sana Kapoor", board_status: "completed", status: "completed", start: inDays(-4, 10), end: inDays(-4, 10, 45), location: "https://meet.example.test/ops-705", length_min: 45, reschedule_count: 0, link: "https://leaddesk-preview.vercel.app/book/demo-705" },
  ];
  let nextInterviewId = 706;
  let slots = [
    { id: 801, start: inDays(1, 10), end: inDays(1, 10, 30), length_min: 30, state: "open", location: "" },
    { id: 802, start: inDays(1, 11), end: inDays(1, 11, 45), length_min: 45, state: "booked", candidate_name: "Meera Kulkarni", location: "https://meet.example.test/ops-701" },
    { id: 803, start: inDays(2, 14), end: inDays(2, 15), length_min: 60, state: "open", location: "" },
    { id: 804, start: inDays(4, 10), end: inDays(4, 10, 45), length_min: 45, state: "open", location: "Meeting room 2" },
  ];
  let nextSlotId = 805;
  let notifications = [
    { text: "A question about the office Wi-Fi password needs your answer.", at: dateAt(-1, 15), link: "#/needs-lead", read: false },
    { text: "Maya Nair finished a reconciliation task.", at: dateAt(-1, 13), link: "#/board", read: false },
  ];
  let nextForumId = 4;

  const clone = (value) => JSON.parse(JSON.stringify(value));
  const bodyOf = (opts) => {
    if (!opts.body) return {};
    if (opts.body instanceof FormData) return Object.fromEntries(opts.body.entries());
    return opts.body;
  };
  const userByName = (name) => users.find((user) => user.username === name);
  const visibleDocs = () => {
    if (activeUser.role === "member") return vaultDocs.filter((doc) => doc.employee_id === activeUser.employee_id);
    if (activeUser.role === "hr") return vaultDocs.filter((doc) => doc.department === activeUser.department);
    return vaultDocs;
  };
  const makeEval = () => ({
    answerable_passed: 4, answerable_total: 5, gaps_caught: 3, gaps_total: 3,
    multilingual_passed: 2, multilingual_total: 2, model: "extractive demo", at: now,
    rows: [
      { passed: true, question: "What should I check before matching a batch?", answer: "Confirm that the settlement file is for the correct business date.", sources: ["Daily Reconciliation Guide › 1. Prepare the source files"], seconds: 0.01 },
      { passed: true, question: "Who approves a refund above ₹10,000?", answer: "The operations lead and finance approver both need to approve it.", sources: ["Refund Approval Matrix › 2. Higher-value refunds"], seconds: 0.01 },
      { passed: false, question: "What is the office Wi-Fi password?", answer: "", sources: [], got: "needs_lead", seconds: 0.01 },
    ],
  });
  const questionsCounts = () => ({
    needs_lead: questions.filter((question) => question.status === "needs_lead").length,
    resolved: questions.filter((question) => question.status === "resolved").length,
    answered: questions.filter((question) => question.status === "answered").length,
  });
  const workload = () => {
    const activeTasks = tasks.filter((task) => task.status !== "done");
    const workloadMembers = members.map((member) => {
      const mine = activeTasks.filter((task) => task.assignee_id === member.id);
      const overdue = mine.filter((task) => task.overdue).length;
      const open = mine.length;
      return { id: member.id, name: member.name, open, overdue, needs_help: overdue > 0 || open >= 4, overloaded: open >= 6 };
    });
    const atRisk = activeTasks.filter((task) => task.overdue || task.due_today || task.status === "escalated")
      .sort((a, b) => Number(b.overdue) - Number(a.overdue) || a.deadline.localeCompare(b.deadline));
    return {
      now,
      threshold: 6,
      totals: {
        open: activeTasks.length,
        members: members.length,
        overdue: activeTasks.filter((task) => task.overdue).length,
        due_today: activeTasks.filter((task) => task.due_today).length,
        escalated: activeTasks.filter((task) => task.status === "escalated").length,
        overloaded: workloadMembers.filter((member) => member.overloaded).length,
      },
      members: workloadMembers,
      at_risk: atRisk,
    };
  };
  const interviewBoard = () => {
    const counts = Object.fromEntries(["invited", "scheduled", "rescheduled", "feedback_pending", "completed", "cancelled"]
      .map((status) => [status, interviews.filter((item) => item.board_status === status).length]));
    return {
      time_zone: "Asia/Kolkata",
      interviews: clone(interviews),
      counts,
      recruiters: clone(recruiters),
      roles: [...new Set(interviews.map((item) => item.role_title))],
    };
  };
  const error = (message, status = 400) => {
    const err = new Error(message);
    err.status = status;
    throw err;
  };
  const api = async (path, opts = {}) => {
    const url = new URL(path, location.origin);
    const pathname = url.pathname;
    const method = (opts.method || "GET").toUpperCase();
    const body = bodyOf(opts);
    const getTask = (id) => tasks.find((task) => task.id === Number(id));
    const getDoc = (id) => vaultDocs.find((doc) => doc.id === Number(id));

    if (pathname === "/api/auth/demo-users") return { users: clone(users), password: "preview" };
    if (pathname === "/api/auth/me") {
      if (!activeUser) return error("Please sign in", 401);
      return { user: clone(activeUser) };
    }
    if (pathname === "/api/auth/login" && method === "POST") {
      activeUser = userByName(body.username);
      if (!activeUser) return error("That preview account was not found", 404);
      return { user: clone(activeUser) };
    }
    if (pathname === "/api/auth/logout" && method === "POST") {
      activeUser = null;
      return {};
    }
    const bookingMatch = pathname.match(/^\/api\/book\/([^/]+)(?:\/(cancel))?$/);
    if (bookingMatch) {
      const tokenId = Number((bookingMatch[1].match(/(\d+)$/) || [])[1]);
      let interview = interviews.find((item) => item.id === tokenId);
      if (!interview && /^demo-\d+$/.test(bookingMatch[1])) {
        interview = {
          id: tokenId, candidate_id: tokenId + 100, candidate_name: `Preview candidate ${tokenId}`,
          role_title: "Operations Associate", round_name: "Round 1", interviewer_id: interviewers[0].id,
          interviewer_name: interviewers[0].name, board_status: "invited", status: "invited",
          start: null, end: null, location: "", length_min: 30, reschedule_count: 0,
          link: `https://leaddesk-preview.vercel.app/book/${bookingMatch[1]}`,
        };
        interviews.push(interview);
      }
      if (!interview) return error("This sample booking link is not valid.", 404);
      if (bookingMatch[2] === "cancel" && method === "POST") {
        interview.board_status = "cancelled";
        interview.status = "cancelled";
        return {};
      }
      if (method === "POST") {
        const slot = slots.find((item) => item.id === Number(body.slot_id) && item.state === "open");
        if (!slot) return error("That sample time is no longer available.", 409);
        const rescheduled = Boolean(interview.start);
        slot.state = "booked";
        slot.candidate_name = interview.candidate_name;
        interview.start = slot.start;
        interview.end = slot.end;
        interview.location = slot.location || interview.location;
        interview.status = "scheduled";
        interview.board_status = rescheduled ? "rescheduled" : "scheduled";
        if (rescheduled) interview.reschedule_count += 1;
        const date = new Date(slot.start);
        return { label: date.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }), rescheduled };
      }
      const booking = interview.start ? {
        start: interview.start, end: interview.end,
        label: new Date(interview.start).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }),
        interviewer: interview.interviewer_name, location: interview.location,
        reschedules: interview.reschedule_count,
      } : null;
      return {
        candidate: interview.candidate_name, role: interview.role_title, round: interview.round_name,
        status: interview.board_status, time_zone: "Asia/Kolkata", past: Boolean(interview.start && new Date(interview.start) < new Date(now)),
        booking,
        slots: slots.filter((slot) => slot.state === "open").map((slot) => ({ ...slot, interviewer: interview.interviewer_name })),
      };
    }
    if (pathname === "/api/auth/password" && method === "POST") return {};
    if (pathname === "/api/health") return { time: now, status: "ok" };
    if (pathname === "/api/meta") return { now, task_types: taskTypes, statuses, priorities, members: clone(members) };
    if (pathname === "/api/notifications") return { unread: notifications.filter((item) => !item.read).length, items: clone(notifications) };
    if (pathname === "/api/notifications/read" && method === "POST") {
      notifications.forEach((item) => { item.read = true; });
      return {};
    }
    if (pathname === "/api/sop/status") return { online: false, model: "preview", url: "local preview", detail: "This static demo uses sample responses; no AI service is connected." };
    if (pathname === "/api/sop/my-questions") return { questions: clone(questions.filter((item) => item.user_id === activeUser.id)) };
    if (pathname === "/api/sop/questions" && method === "GET") {
      const status = url.searchParams.get("status") || "needs_lead";
      const selected = status === "all" ? questions : questions.filter((item) => item.status === status);
      return { questions: clone(selected), counts: questionsCounts() };
    }
    if (pathname === "/api/sop/ask" && method === "POST") {
      const question = String(body.question || "");
      const needsLead = /wi.?fi|password|unknown/i.test(question);
      const response = {
        id: questions.length + 1,
        question,
        status: needsLead ? "needs_lead" : "answered",
        answer: needsLead ? "" : "Pause the batch, confirm the business date, and match the settlement line to its ledger reference. Record any unexplained variance for the team lead.",
        reason: needsLead ? "No supporting section in the sample SOP library" : "",
        mode: "extractive",
        top_score: needsLead ? 0.08 : 0.88,
        sources: needsLead ? [] : [{ doc: "Daily Reconciliation Guide", section: "2. Match transactions", excerpt: "Match each settlement line to a ledger entry by reference and amount." }],
      };
      questions.push({ ...response, asked_by: activeUser.name, user_id: activeUser.id, asked_at: now, language: "en", helpful: null });
      return response;
    }
    const questionFeedback = pathname.match(/^\/api\/sop\/questions\/(\d+)\/feedback$/);
    if (questionFeedback && method === "POST") {
      const question = questions.find((item) => item.id === Number(questionFeedback[1]));
      if (question) question.helpful = body.helpful ? 1 : 0;
      return {};
    }
    const resolveQuestion = pathname.match(/^\/api\/sop\/questions\/(\d+)\/resolve$/);
    if (resolveQuestion && method === "POST") {
      const question = questions.find((item) => item.id === Number(resolveQuestion[1]));
      if (question) Object.assign(question, { status: "resolved", lead_answer: body.answer, resolved_by: activeUser.name, resolved_by_name: activeUser.name, resolved_at: now });
      return {};
    }
    if (pathname === "/api/sop/docs" && method === "GET") return { docs: clone(sopDocs) };
    if (pathname === "/api/sop/docs" && method === "POST") {
      const doc = { id: sopDocs.length + 1, title: String(body.file?.name || "Sample procedure"), filename: String(body.file?.name || "sample-procedure.pdf"), n_sections: 2, uploaded_at: now, uploaded_by: activeUser.name };
      sopDocs.push(doc);
      return { title: doc.title, sections: doc.n_sections };
    }
    const sopSectionsMatch = pathname.match(/^\/api\/sop\/docs\/(\d+)\/sections$/);
    if (sopSectionsMatch) {
      const doc = sopDocs.find((item) => item.id === Number(sopSectionsMatch[1]));
      if (!doc) return error("SOP not found", 404);
      return { doc: clone(doc), sections: clone(sopSections[doc.id] || [{ section: "Preview section", text: "This sample section is shown for the interactive preview." }]) };
    }
    const sopDocMatch = pathname.match(/^\/api\/sop\/docs\/(\d+)$/);
    if (sopDocMatch && method === "DELETE") {
      sopDocs = sopDocs.filter((item) => item.id !== Number(sopDocMatch[1]));
      return {};
    }
    if (pathname === "/api/sop/eval") return makeEval();
    if (pathname === "/api/tasks" && method === "GET") {
      const own = url.searchParams.get("mine") === "true" && activeUser.role === "member";
      return { tasks: clone(own ? tasks.filter((task) => task.assignee_id === activeUser.id) : tasks) };
    }
    if (pathname === "/api/tasks" && method === "POST") {
      const member = members.find((item) => item.id === Number(body.assignee_id));
      const task = {
        id: nextTaskId++, title: String(body.title || "Preview task"), description: String(body.description || ""),
        task_type: body.task_type || taskTypes[0], priority: body.priority || "medium", status: body.status || "pending",
        assignee_id: member?.id || null, assignee_name: member?.name || null,
        deadline: body.deadline || inDays(1), overdue: false, due_today: false, created_by_name: activeUser.name, done_at: null,
      };
      tasks.push(task);
      return { task: clone(task) };
    }
    if (pathname === "/api/workload") return workload();
    if (pathname === "/api/impact") {
      const load = workload();
      return {
        window_days: 30,
        board: { members: load.totals.members, tasks: tasks.length, overdue: load.totals.overdue, due_today: load.totals.due_today, overloaded: load.totals.overloaded, threshold: load.threshold, busiest: load.members.slice().sort((a, b) => b.open - a.open)[0] },
        assistant: { asked: 42, answer_rate_pct: 76, hours_saved: 5.3 },
        vault: { documents: vaultDocs.length, scans_searchable: vaultDocs.filter((doc) => doc.ocr_used).length, audit_entries: auditEntries.length },
        interviews: { upcoming: interviews.filter((item) => ["scheduled", "rescheduled"].includes(item.board_status)).length, hours_booked: 4.5, feedback_pending: interviews.filter((item) => item.board_status === "feedback_pending").length },
        assumptions: ["The preview uses synthetic sample records.", "Counts are calculated from the sample data loaded in this browser session."],
      };
    }
    const taskHistoryMatch = pathname.match(/^\/api\/tasks\/(\d+)\/history$/);
    if (taskHistoryMatch) {
      const task = getTask(taskHistoryMatch[1]);
      return { events: task ? taskEvents(task) : [] };
    }
    const taskMatch = pathname.match(/^\/api\/tasks\/(\d+)$/);
    if (taskMatch && method === "PATCH") {
      const task = getTask(taskMatch[1]);
      if (!task) return error("Task not found", 404);
      if (body.status) {
        task.status = body.status;
        if (body.status === "done") task.done_at = now;
      }
      if (body.title) task.title = body.title;
      if (body.description) task.description = body.description;
      if (body.note) task.note = body.note;
      if (body.assignee_id !== undefined) {
        const member = members.find((item) => item.id === Number(body.assignee_id));
        task.assignee_id = member?.id || null;
        task.assignee_name = member?.name || null;
      }
      if (body.task_type) task.task_type = body.task_type;
      if (body.priority) task.priority = body.priority;
      if (body.deadline) task.deadline = body.deadline;
      task.overdue = task.status !== "done" && new Date(task.deadline) < new Date(now) && new Date(task.deadline).toDateString() !== new Date(now).toDateString();
      task.due_today = task.status !== "done" && new Date(task.deadline).toDateString() === new Date(now).toDateString();
      return { task: clone(task) };
    }
    if (pathname === "/api/vault/employees") {
      const query = (url.searchParams.get("qs") || "").toLowerCase();
      return { employees: clone(employees.filter((item) => !query || `${item.employee_id} ${item.name} ${item.department}`.toLowerCase().includes(query))) };
    }
    if (pathname === "/api/vault/meta") return {
      can_upload: ["hr", "admin"].includes(activeUser.role),
      is_admin: activeUser.role === "admin",
      scope: activeUser.role === "admin" ? "All departments" : activeUser.role === "hr" ? `${activeUser.department} department` : activeUser.role === "lead" ? "Team sample data · read only" : "Your documents",
      doc_types: docTypes,
    };
    if (pathname === "/api/vault/docs" && method === "GET") return { docs: clone(visibleDocs()) };
    if (pathname === "/api/vault/docs" && method === "POST") {
      const employee = employees.find((item) => item.employee_id === body.employee_id);
      const doc = {
        id: Math.max(...vaultDocs.map((item) => item.id), 500) + 1,
        employee_id: body.employee_id || "EMP-1001", employee_name: employee?.name || "Riya Sharma", department: employee?.department || "Operations",
        original_name: String(body.file?.name || "preview-document.txt"), title: String(body.file?.name || "Preview document"),
        doc_type: body.doc_type || "other", doc_type_label: docTypes[body.doc_type] || "Other", doc_type_source: "manual", type_reason: "Preview change",
        uploaded_at: now, uploaded_by_name: activeUser.name, retention_until: body.retention_until || "", retention_expired: false,
        ocr_used: false, mime: "text/plain", text: "Sample document content. Files are not uploaded or stored in this preview.",
      };
      vaultDocs.push(doc);
      return { doc: clone(doc) };
    }
    if (pathname === "/api/vault/search") {
      const query = url.searchParams.get("qs") || "";
      return { scope: activeUser.role === "admin" ? "all departments" : "your permitted documents", results: clone(visibleDocs().slice(0, 3).map((doc) => ({ doc, snippets: [`<mark>${escapeHtml(query)}</mark> appears in this sample document.`] }))) };
    }
    if (pathname === "/api/vault/delete-requests") return { requests: clone(deleteRequests) };
    const decideDelete = pathname.match(/^\/api\/vault\/delete-requests\/(\d+)\/decide$/);
    if (decideDelete && method === "POST") {
      const request = deleteRequests.find((item) => item.id === Number(decideDelete[1]));
      if (request) Object.assign(request, { status: body.approve ? "approved" : "rejected", approved_by_name: activeUser.name });
      return {};
    }
    if (pathname === "/api/vault/audit") {
      const action = url.searchParams.get("action") || "";
      return { entries: clone(auditEntries.filter((entry) => !action || entry.action === action || (action === "denied" && entry.outcome === "denied"))), chain: { ok: true, entries: auditEntries.length } };
    }
    const storageMatch = pathname.match(/^\/api\/vault\/storage\/(\d+)$/);
    if (storageMatch) return {
      path_on_disk: "preview/sample.enc", stored_bytes: 4096, disk_head_hex: "4f 9a 2d 63 b1 77 08 e4", disk_head_text: "O.-c.w..",
      original_bytes: 2048, original_head_hex: "25 50 44 46 2d 31 2e 37", original_head_text: "%PDF-1.7",
      entropy_bits_per_byte: 7.94, printable_ratio: 0.12, sha256_matches: true, cipher: "AES-256-GCM", key_fingerprint: "preview-only",
    };
    const deleteRequestMatch = pathname.match(/^\/api\/vault\/docs\/(\d+)\/delete-request$/);
    if (deleteRequestMatch && method === "POST") {
      const doc = getDoc(deleteRequestMatch[1]);
      if (doc) deleteRequests.unshift({ id: Date.now(), doc_id: doc.id, original_name: doc.original_name, requested_by_name: activeUser.name, requested_at: now, reason: body.reason || "", status: "pending" });
      return {};
    }
    const vaultDocMatch = pathname.match(/^\/api\/vault\/docs\/(\d+)$/);
    if (vaultDocMatch && method === "GET") {
      const doc = getDoc(vaultDocMatch[1]);
      if (!doc || (activeUser.role === "member" && doc.employee_id !== activeUser.employee_id) || (activeUser.role === "hr" && doc.department !== activeUser.department)) return error("This account cannot access that sample document.", 403);
      return { doc: clone(doc), text: doc.text };
    }
    if (vaultDocMatch && method === "PATCH") {
      const doc = getDoc(vaultDocMatch[1]);
      if (!doc) return error("Document not found", 404);
      if (body.doc_type) Object.assign(doc, { doc_type: body.doc_type, doc_type_label: docTypes[body.doc_type] || "Other", doc_type_source: "manual" });
      if (body.retention_until !== undefined) doc.retention_until = body.retention_until;
      return { doc: clone(doc) };
    }
    if (pathname === "/api/iv/board") return interviewBoard();
    if (pathname === "/api/iv/mine") return { interviews: clone(interviews.filter((item) => item.interviewer_id === activeUser.id || activeUser.role === "interviewer")) };
    if (pathname === "/api/iv/slots" && method === "GET") return { time_zone: "Asia/Kolkata", slots: clone(slots) };
    if (pathname === "/api/iv/slots" && method === "POST") {
      const start = `${body.day}T${body.start_time}`;
      const end = `${body.day}T${body.end_time}`;
      const startDate = new Date(start);
      const endDate = new Date(end);
      const duration = Math.max(30, Number(body.length_min) || 45);
      let created = 0;
      for (let week = 0; week <= Math.min(8, Number(body.repeat_weeks) || 0); week += 1) {
        const day = new Date(startDate);
        day.setDate(day.getDate() + week * 7);
        const stop = new Date(endDate);
        stop.setDate(stop.getDate() + week * 7);
        for (let cursor = new Date(day); cursor.getTime() + duration * 60000 <= stop.getTime(); cursor = new Date(cursor.getTime() + duration * 60000)) {
          const slotEnd = new Date(cursor.getTime() + duration * 60000);
          slots.push({ id: nextSlotId++, start: localTime(cursor), end: localTime(slotEnd), length_min: duration, state: "open", location: body.location || "" });
          created += 1;
        }
      }
      return { created, skipped: 0 };
    }
    const removeSlot = pathname.match(/^\/api\/iv\/slots\/(\d+)$/);
    if (removeSlot && method === "DELETE") {
      slots = slots.filter((slot) => slot.id !== Number(removeSlot[1]));
      return {};
    }
    if (pathname === "/api/iv/outbox") return {
      mail_ui: "https://example.test/preview-mail",
      messages: [
        { id: 1, at: dateAt(-1, 16), subject: "Interview reminder · Meera Kulkarni", to_addr: "meera.kulkarni@example.test", kind: "candidate_reminder", body: "This is a sample message. No email was sent.", delivered: false, has_ics: true },
        { id: 2, at: dateAt(-2, 10), subject: "Booking link · Arjun Pillai", to_addr: "arjun.pillai@example.test", kind: "invite", body: "This is a sample message. No email was sent.", delivered: false, has_ics: false },
      ],
    };
    if (pathname === "/api/iv/candidates" && method === "POST") {
      const id = nextInterviewId++;
      const interview = {
        id, candidate_id: id + 100, candidate_name: body.name || "Preview Candidate",
        candidate_email: body.email || "candidate@example.test", recruiter_id: activeUser.id, recruiter_name: activeUser.name,
        role_title: body.role_title || "Operations Associate", round_name: body.round_name || "Round 1",
        interviewer_id: interviewers[0].id, interviewer_name: interviewers[0].name, board_status: "invited", status: "invited",
        start: null, end: null, location: "", length_min: Number(body.length_min) || 30, reschedule_count: 0,
        link: `https://leaddesk-preview.vercel.app/book/demo-${id}`,
      };
      interviews.unshift(interview);
      return { link: interview.link };
    }
    const feedbackMatch = pathname.match(/^\/api\/iv\/candidates\/(\d+)\/feedback$/);
    if (feedbackMatch) return {
      locked: false, hidden: 0,
      feedback: [
        { interviewer_name: "Omar Fernandes", round_name: "Round 1", communication: 4, technical: 4, problem_solving: 3, culture_fit: 4, recommendation: "advance", comments: "Clear examples and a careful review approach." },
      ],
    };
    const interviewFeedback = pathname.match(/^\/api\/iv\/interviews\/(\d+)\/feedback$/);
    if (interviewFeedback && method === "POST") {
      const interview = interviews.find((item) => item.id === Number(interviewFeedback[1]));
      if (interview) interview.board_status = "completed";
      return {};
    }
    const interviewAction = pathname.match(/^\/api\/iv\/interviews\/(\d+)\/(nudge|cancel)$/);
    if (interviewAction && method === "POST") {
      const interview = interviews.find((item) => item.id === Number(interviewAction[1]));
      if (interview && interviewAction[2] === "cancel") interview.board_status = "cancelled";
      return {};
    }
    if (pathname === "/api/iv/demo/race" && method === "POST") return {
      bookings_made: 1,
      slot: "preview slot",
      results: [{ who: "Candidate A", ok: true, message: "" }, { who: "Candidate B", ok: false, message: "The sample slot is already booked." }],
    };
    if (pathname === "/api/proof") return {
      eval: makeEval(), ai: { online: false, model: "preview", url: "local preview", detail: "This static preview is not connected to a local AI service." },
      sop_sections: sopDocs.reduce((sum, doc) => sum + doc.n_sections, 0),
      gaps: questions.filter((question) => question.status === "needs_lead").length,
      vault_docs: vaultDocs.length, scans: vaultDocs.filter((doc) => doc.ocr_used).length,
      audit_chain: { ok: true, entries: auditEntries.length },
    };
    if (pathname === "/api/forum/posts" && method === "GET") return { posts: clone(forumPosts) };
    if (pathname === "/api/forum/posts" && method === "POST") {
      const post = { id: nextForumId++, title: body.title || "Preview discussion", body: body.body || "", author_name: activeUser.name, author_role_label: activeUser.role_label, updated_at: now, created_at: now, reply_count: 0 };
      forumPosts.unshift(post);
      forumReplies[post.id] = [];
      return { post: clone(post) };
    }
    const forumThread = pathname.match(/^\/api\/forum\/posts\/(\d+)$/);
    if (forumThread && method === "GET") {
      const post = forumPosts.find((item) => item.id === Number(forumThread[1]));
      if (!post) return error("Discussion not found", 404);
      return { post: clone(post), replies: clone(forumReplies[post.id] || []) };
    }
    const forumReply = pathname.match(/^\/api\/forum\/posts\/(\d+)\/replies$/);
    if (forumReply && method === "POST") {
      const post = forumPosts.find((item) => item.id === Number(forumReply[1]));
      if (post) {
        const replies = forumReplies[post.id] || (forumReplies[post.id] = []);
        replies.push({ author_name: activeUser.name, author_role_label: activeUser.role_label, created_at: now, body: body.body || "" });
        post.reply_count = replies.length;
        post.updated_at = now;
      }
      return {};
    }

    return error(`Preview data is not configured for ${method} ${pathname}.`, 501);
  };

  window.LEADDESK_PREVIEW_MODE = true;
  window.LEADDESK_PREVIEW_API = api;
  document.addEventListener("click", (event) => {
    const link = event.target.closest('a[href^="/api/"]');
    if (!link) return;
    event.preventDefault();
    if (typeof window.toast === "function") window.toast("Downloads are not included in this preview.");
    else {
      const notice = document.createElement("div");
      notice.className = "alert warn";
      notice.textContent = "Downloads are not included in this preview.";
      document.querySelector("#toasts")?.appendChild(notice);
      setTimeout(() => notice.remove(), 3200);
    }
  });
})();
