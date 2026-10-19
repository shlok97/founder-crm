"use strict";
const $ = (s) => document.querySelector(s);
const node = (tag, cls = "", text = "") => {
  const e = document.createElement(tag);
  e.className = cls;
  e.textContent = text;
  return e;
};
const add = (parent, ...children) => {
  children.forEach((c) => parent.append(c));
  return parent;
};
const button = (label, fn, cls = "button small") => {
  const b = node("button", cls, label);
  b.type = "button";
  b.onclick = () =>
    Promise.resolve()
      .then(fn)
      .catch((error) => toast(error.message, true));
  return b;
};
const tag = (text, tone = "") => node("span", "row-tag " + tone, text);
let state,
  view = "today",
  toastTimer;
const api = async (path, data) => {
  const opts =
    data === undefined
      ? {}
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CRM-CSRF": $("meta[name=crm-csrf]").content,
          },
          body: JSON.stringify(data),
        };
  const r = await fetch("/api/" + path, opts);
  const body = await r.json();
  if (!r.ok) throw new Error(body.error || "Request failed");
  return body;
};
function toast(message, error = false) {
  const e = $("#toast");
  if ($("#dialog").open) $("#dialog").append(e);
  else document.body.append(e);
  e.textContent = message;
  e.className = error ? "error" : "";
  e.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (e.hidden = true), 7000);
}
function open(title) {
  $("#dialog-title").textContent = title;
  $("#dialog-body").replaceChildren();
  if (!$("#dialog").open) $("#dialog").showModal();
  return $("#dialog-body");
}
function close() {
  if ($("#dialog").open) $("#dialog").close();
  document.body.append($("#toast"));
}
function field(parent, label, type = "text", value = "") {
  const l = node("label", "", label),
    e = node(type === "textarea" ? "textarea" : "input");
  if (type !== "textarea") e.type = type;
  e.value = value;
  e.setAttribute("aria-label", label);
  add(parent, l, e);
  return e;
}
function select(parent, label, choices) {
  const l = node("label", "", label),
    e = node("select");
  e.setAttribute("aria-label", label);
  for (const [value, title] of choices) {
    const o = node("option", "", title);
    o.value = value;
    e.append(o);
  }
  add(parent, l, e);
  return e;
}
function label(parent, text, right = "") {
  const l = node("div", "section-label", text);
  if (right) l.append(node("span", "", right));
  parent.append(l);
  return l;
}
function empty(parent, title, detail) {
  const e = node("div", "empty", title);
  if (detail) e.append(node("small", "", detail));
  parent.append(e);
}
function row(parent, title, sub, action, meta) {
  const r = node("div", "row"),
    m = node("div", "row-main");
  add(m, node("div", "row-title", title), node("p", "", sub || ""));
  r.append(m);
  if (meta) r.append(meta);
  if (action) r.append(action);
  parent.append(r);
  return r;
}
function accountName(id) {
  return (
    state.accounts.find((a) => a.id === id)?.name || "Unknown relationship"
  );
}
function targetName(payload) {
  const id =
    payload.account_id ||
    state.tickets.find((t) => t.id === payload.ticket_id)?.account_id ||
    state.opportunities.find((o) => o.id === payload.opportunity_id)
      ?.account_id;
  return accountName(id);
}
const heads = {
  today: [
    "YOUR NEXT MOVES",
    "Keep the promises.",
    "The replies, next steps, and updates that deserve your attention.",
  ],
  inbox: [
    "CONVERSATIONS. ONE HISTORY.",
    "Start with the evidence.",
    "Emails, website enquiries, and the notes you bring from conversations.",
  ],
  review: [
    "THE SPACE BEFORE SAVE",
    "A second look.",
    "Inspect the source and the proposed update. Jev can advise; you decide.",
  ],
  people: [
    "PEOPLE BEFORE PIPELINES",
    "Know who you know.",
    "A customer, an investor, and a vendor need different next steps.",
  ],
  pipeline: [
    "CUSTOMER OPPORTUNITIES",
    "What’s moving forward?",
    "Sales opportunities stay separate from your other relationships.",
  ],
  tickets: [
    "WHAT CUSTOMERS ARE WAITING ON",
    "Close every loop.",
    "A ticket stays open until it is fixed, and a fix is not delivered until the customer is told.",
  ],
  qualify: [
    "QUALIFICATION",
    "Who can buy, and why?",
    "The questions that decide whether an account can and will buy. Every claim keeps its source.",
  ],
  yours: [
    "MAKE IT YOURS",
    "Shape it to your business.",
    "Add your own fields without a schema change, or ask Claude to change the app itself.",
  ],
  integrations: [
    "BRING YOUR OWN TOOLS",
    "Connect the useful bits.",
    "The app works locally. Connect external services only when you need them.",
  ],
};
async function refresh() {
  state = await api("dashboard");
  render();
}
function render() {
  const h = heads[view];
  $("#eyebrow").textContent = h[0];
  $("#page-title").textContent = h[1];
  $("#page-description").textContent = h[2];
  $("#demo-banner").hidden = !state.demo;
  $("#workspace-label").textContent = state.demo
    ? "DEMO / FICTIONAL RECORDS"
    : "YOUR WORKSPACE";
  $("#intake-count").textContent = state.intake.length || "";
  $("#review-count").textContent = state.proposals.length || "";
  $("#untold-count").textContent = state.untold.length || "";
  document
    .querySelectorAll("[data-view]")
    .forEach((e) => e.classList.toggle("active", e.dataset.view === view));
  const stats = $("#stats");
  stats.replaceChildren();
  for (const [value, title] of [
    [state.tasks.length, "Open next steps"],
    [state.proposals.length, "Updates to review"],
    [state.counts.contacts, "People in the story"],
    [state.untold.length, "Fixed, update still owed"],
  ]) {
    add(
      stats,
      add(
        node("div", "stat"),
        node("strong", "", String(value)),
        node("span", "", title),
      ),
    );
  }
  const c = $("#content");
  c.replaceChildren();
  ({
    today: renderToday,
    inbox: renderInbox,
    review: renderReview,
    people: renderPeople,
    pipeline: renderPipeline,
    integrations: renderConnections,
    tickets: renderTickets,
    qualify: renderQualify,
    yours: renderYours,
  })[view](c);
}
function renderToday(c) {
  const cols = node("div", "two-col"),
    left = node("div"),
    right = node("div");
  label(left, "FOLLOW THROUGH", `${state.tasks.length} OPEN`);
  if (!state.tasks.length)
    empty(
      left,
      "Nothing is waiting here.",
      "Capture a note or ask Claude to propose a next step.",
    );
  const now = new Date(),
    today = [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, "0"),
      String(now.getDate()).padStart(2, "0"),
    ].join("-");
  for (const task of state.tasks) {
    const due = node(
      "span",
      "due" + (task.due_date && task.due_date < today ? " late" : ""),
      task.due_date || "No date",
    );
    row(
      left,
      task.title,
      task.account_name,
      button("Done", async () => {
        await api("complete-task", { id: task.id });
        await refresh();
        toast("Next step completed.");
      }),
      due,
    );
  }
  const dated = state.followups.filter((f) => f.kind !== "task");
  label(left, "DATED NEXT STEPS", `${dated.length}`);
  if (!dated.length) empty(left, "No dated next steps on relationships, deals or tickets.");
  for (const f of dated.slice(0, 25)) {
    const due = node(
      "span",
      "due" + (f.due && f.due < today ? " late" : ""),
      f.due || "No date",
    );
    const r = row(left, f.next_action || f.what, `${f.account_name} · ${f.what}`, null, due);
    r.prepend(tag(f.kind, "gray"));
  }
  label(left, "CLOSE THE LOOP");
  if (!state.untold.length)
    empty(left, "No recorded fixes are waiting for a client update.");
  for (const t of state.untold)
    row(
      left,
      t.title,
      `${t.account_name} · ${t.resolution || t.status}`,
      button("Record update", () => notifyForm(t)),
      tag("UPDATE OWED", "amber"),
    );
  label(right, "HOW A MEMORY BECOMES AN UPDATE");
  const panel = node("div", "panel");
  add(
    panel,
    node("div", "eyebrow", "EVIDENCE → PROPOSAL → REVIEW"),
    node("h2", "", "A fix is not a notification."),
    node(
      "p",
      "",
      "Keep the customer conversation attached to the record. A shipped fix stays separate from evidence that someone was told.",
    ),
    button("See the review queue", () => {
      view = "review";
      render();
    }),
  );
  right.append(panel);
  label(right, "RECENT RECORDS");
  for (const a of state.audit.slice(0, 5)) {
    const e = node("div", "activity");
    add(
      e,
      node("strong", "", `${a.actor} · ${a.action.replaceAll("_", " ")}`),
      node("p", "", `${a.object_type} #${a.object_id} · ${a.created_at}`),
    );
    right.append(e);
  }
  add(cols, left, right);
  c.append(cols);
}
function flow(c) {
  const f = node("div", "flow");
  for (const [i, [name, desc]] of [
    ["Gmail / notes", "Bring the source"],
    ["Claude", "Propose the update"],
    ["Jev", "Check the evidence"],
    ["You + SQLite", "Review, then save"],
  ].entries()) {
    if (i) f.append(node("span", "flow-arrow", "→"));
    const n = node("div", "flow-node" + (i === 2 ? " accent" : ""));
    add(n, node("strong", "", name), node("small", "", desc));
    f.append(n);
  }
  c.append(f);
}
function renderInbox(c) {
  flow(c);
  label(c, "RECENT INTAKE", `${state.intake.length} SHOWN`);
  if (!state.intake.length)
    empty(
      c,
      "The inbox is empty.",
      "Capture a founder note, pull Gmail, or connect a website form.",
    );
  for (const i of state.intake) {
    const r = row(
      c,
      i.subject,
      `${i.contact_name || i.sender || "Founder note"} · ${i.body.slice(0, 100)}`,
      button("Inspect", () => inspectIntake(i)),
    );
    r.prepend(tag(i.source, "gray"));
  }
}
function inspectIntake(i) {
  const p = open(i.subject);
  add(
    p,
    node(
      "p",
      "hint",
      `${i.source} · ${i.direction} · ${i.sender || "No sender"} · record #${i.id}`,
    ),
    node("div", "evidence", i.body),
  );
  label(p, "PROPOSE A NEXT STEP");
  const action = select(p, "Type of update", [
    ["create_task", "Create a follow-up"],
    ["log_interaction", "Record an interaction"],
    ["open_ticket", "Open a client ticket"],
  ]);
  const a = select(p, "Relationship", [
    ["", "Choose a relationship"],
    ...state.accounts.map((a) => [a.id, a.name]),
  ]);
  const title = field(p, "Update", "textarea");
  const due = field(p, "Due date (follow-ups only)", "date");
  const save = button(
    "Stage for review",
    async () => {
      if (!a.value)
        throw new Error("Choose the relationship this source belongs to.");
      const payload = {
        account_id: Number(a.value),
        [action.value === "log_interaction" ? "summary" : "title"]: title.value,
      };
      if (action.value === "create_task" && due.value)
        payload.due_date = due.value;
      await api("propose", { intake_id: i.id, action: action.value, payload });
      close();
      view = "review";
      await refresh();
      toast("Update staged. Nothing has been applied.");
    },
    "button primary",
  );
  add(p, add(node("div", "actions"), save));
}
function renderReview(c) {
  flow(c);
  label(c, "PENDING UPDATES", `${state.proposals.length} TO REVIEW`);
  if (!state.proposals.length)
    empty(c, "All proposed updates have been reviewed.");
  for (const p of state.proposals) {
    const payload = JSON.parse(p.payload),
      status = p.verdict || "NOT JUDGED";
    const r = row(
      c,
      payload.title || payload.summary || p.action.replaceAll("_", " "),
      `${targetName(payload)} · ${p.subject}`,
      button("Review source", () => inspectProposal(p.id)),
    );
    r.prepend(
      tag(
        status,
        status === "UNSUPPORTED"
          ? "amber"
          : status === "SUPPORTED"
            ? ""
            : "gray",
      ),
    );
  }
}
async function inspectProposal(id) {
  const data = await api("proposals/" + id),
    p = open("Review proposed update");
  add(
    p,
    node(
      "p",
      "hint",
      `Proposal #${id} · ${data.action.replaceAll("_", " ")} · ${data.created_by}`,
    ),
  );
  label(p, "SOURCE EVIDENCE");
  add(p, node("div", "evidence", data.context.source_evidence.body));
  label(p, "KNOWN RELATIONSHIP");
  p.append(
    node(
      "p",
      "hint",
      data.context.known_account
        ? `${data.context.known_account.name} · ${data.context.known_account.relationship} · ${data.context.known_account.lifecycle}`
        : "No verified relationship matched this sender.",
    ),
  );
  if (data.context.target_record) {
    label(p, "TARGET RECORD");
    const t = data.context.target_record,
      r = t.record,
      a = data.context.target_account;
    row(
      p,
      `${a.name} · ${a.relationship}`,
      t.table === "accounts"
        ? `Relationship #${r.id} · ${r.lifecycle}`
        : t.table === "tickets"
          ? `Ticket #${r.id}: ${r.title} · ${r.status} · ${r.notified_at ? "notification recorded" : "no notification recorded"}`
          : `Opportunity #${r.id}: ${r.title} · ${r.stage}`,
    );
  }
  if (data.context.recent_interactions.length) {
    label(p, "RECENT HISTORY SHARED WITH JEV");
    for (const i of data.context.recent_interactions)
      row(p, i.summary, `${i.direction} · ${i.created_at}`);
  }
  label(p, "PROPOSED WRITE");
  p.append(node("pre", "", JSON.stringify(data.payload, null, 2)));
  if (data.judgments.length) {
    const j = data.judgments[0];
    p.append(tag(j.verdict, j.verdict === "UNSUPPORTED" ? "amber" : ""));
    p.append(
      node(
        "p",
        "hint",
        `${j.model} · confidence ${j.confidence}. Confidence measures the model’s concentration, not verified accuracy.`,
      ),
    );
  } else
    p.append(
      node(
        "p",
        "hint",
        "Not judged. You can review manually or explicitly ask your configured Jev provider.",
      ),
    );
  p.append(
    node(
      "p",
      "hint",
      "Ask Jev shares this source, relationship and target records, recent history and proposed update with your configured provider. It does not save the update.",
    ),
  );
  const actions = node("div", "actions");
  add(
    actions,
    button(
      "Reject",
      async () => {
        await api("reject", { id });
        close();
        await refresh();
        toast("Proposal rejected.");
      },
      "button danger",
    ),
    button("Ask Jev", async () => {
      toast("Requesting a judgment…");
      await api("judge", { id });
      await refresh();
      await inspectProposal(id);
    }),
    button(
      "Apply after review",
      async () => {
        await api("apply", { id, confirm: true });
        close();
        await refresh();
        toast("Update saved with an audit record.");
      },
      "button primary",
    ),
  );
  p.append(actions);
}
function renderPeople(c) {
  const search = node("input", "search");
  search.type = "search";
  search.placeholder = "Find a relationship…";
  search.setAttribute("aria-label", "Find a relationship");
  c.append(search);
  const cards = node("div", "cards");
  c.append(cards);
  function paint() {
    cards.replaceChildren();
    const filtered = state.accounts.filter((a) =>
      `${a.name} ${a.relationship}`
        .toLowerCase()
        .includes(search.value.toLowerCase()),
    );
    for (const a of filtered) {
      const card = button("", () => history(a.id), "person");
      add(
        card,
        node(
          "div",
          "initials",
          a.name
            .split(" ")
            .map((s) => s[0])
            .slice(0, 2)
            .join(""),
        ),
        node("h3", "", a.name),
        tag(a.relationship),
        node(
          "p",
          "",
          `${a.lifecycle} · ${a.contact_count} contact${a.contact_count === 1 ? "" : "s"}`,
        ),
      );
      cards.append(card);
    }
    if (!filtered.length) empty(cards, "No relationships match.");
  }
  search.oninput = paint;
  paint();
}
function details(parent, pairs) {
  const dl = node("dl", "kv");
  for (const [k, v] of pairs) {
    if (v === null || v === undefined || v === "" || v === "[]") continue;
    add(dl, node("dt", "", k), node("dd", "", typeof v === "object" ? JSON.stringify(v) : String(v)));
  }
  if (dl.children.length) parent.append(dl);
  return dl;
}
function fieldLabel(type, key) {
  return state.fields.find((f) => f.object_type === type && f.key === key)?.label || key;
}
async function history(id) {
  const a = await api("accounts/" + id),
    p = open(a.name);
  add(p, tag(a.relationship), node("p", "hint", `${a.lifecycle}${a.segment ? " · " + a.segment : ""}`));
  details(p, [
    ["Next step", a.next_action && `${a.next_action} (${a.next_action_date || "no date"})`],
    ["Owner", a.owner],
    ["Tier", a.tier],
    ["Website", a.website],
    ["Location", [a.city, a.region, a.country].filter(Boolean).join(", ")],
    ["Source", a.source_detail],
    ["Tags", JSON.parse(a.tags || "[]").join(", ")],
    ["Notes", a.notes],
    ...Object.entries(a.custom).map(([k, v]) => [fieldLabel("account", k), v]),
  ]);
  const q = a.qualification.status;
  label(p, "QUALIFICATION", `${q.pct}% · ${q.status.replace("_", " ")}`);
  p.append(button("Open qualification", () => qualifyDialog(id)));
  label(p, "CONTACTS");
  for (const person of a.contacts)
    row(
      p,
      person.name,
      [person.title, person.email, person.phone || person.whatsapp].filter(Boolean).join(" · ") ||
        "No email recorded",
    );
  p.append(button("+ Add contact", () => contactForm(id)));
  label(p, "TICKETS", `${a.tickets.length}`);
  for (const t of a.tickets)
    row(p, `#${t.id} ${t.title}`, `${t.severity} · ${t.status}${t.notified_at ? " · customer told" : ""}`, button("Open", () => ticketDialog(t.id)));
  p.append(button("+ New ticket", () => ticketForm(id)));
  if (a.opportunities.length) {
    label(p, "OPPORTUNITIES");
    for (const o of a.opportunities)
      row(p, o.title, [o.stage, o.value && `${o.value} ${o.currency || ""}`, o.next_action].filter(Boolean).join(" · "));
  }
  label(p, "RELATIONSHIP HISTORY");
  if (!a.interactions.length) empty(p, "No interactions recorded yet.");
  for (const i of a.interactions)
    row(
      p,
      i.summary,
      [i.kind.replaceAll("_", " "), i.channel, i.direction, i.occurred_at || i.created_at]
        .filter(Boolean)
        .join(" · "),
    );
  label(p, "NEXT STEPS");
  for (const t of a.tasks)
    row(p, t.title, `${t.status} · ${t.due_date || "No date"}`);
}
function choices(values) {
  return values.map((v) => [v, v.replaceAll("_", " ")]);
}
const CHANNELS = ["whatsapp", "email", "call", "in_person", "video", "linkedin", "app", "chat", "sms", "internal", "other"];
function renderTickets(c) {
  const top = label(c, "OPEN TICKETS", "WORST FIRST");
  top.append(button("+ New ticket", () => ticketForm()));
  const open = state.tickets.filter((t) => !["closed", "wont_do", "duplicate"].includes(t.status));
  if (!open.length) empty(c, "No open tickets.", "Log what a customer reports so it cannot slip.");
  for (const t of open) {
    const r = row(
      c,
      `#${t.id} ${t.title}`,
      [t.account_name, t.status.replaceAll("_", " "), t.kind.replaceAll("_", " "), t.next_action].filter(Boolean).join(" · "),
      button("Open", () => ticketDialog(t.id)),
      t.next_action_date ? node("span", "due", t.next_action_date) : null,
    );
    r.prepend(tag(t.severity, ["blocker", "high"].includes(t.severity) ? "amber" : "gray"));
  }
  label(c, "FIXED, CUSTOMER NOT TOLD", `${state.untold.length}`);
  if (!state.untold.length) empty(c, "Every fix has been told to its customer.");
  for (const t of state.untold)
    row(c, `#${t.id} ${t.title}`, `${t.account_name} · ${t.resolution || t.status}`, button("Record update", () => notifyForm(t)), tag("UPDATE OWED", "amber"));
}
function ticketForm(accountId) {
  const p = open("Log a customer ticket");
  const a = select(p, "Relationship", [["", "Choose a relationship"], ...state.accounts.map((x) => [x.id, x.name])]);
  if (accountId) a.value = accountId;
  const title = field(p, "What is wrong or wanted?"),
    kind = select(p, "Kind", choices(["bug", "data_defect", "feature_request", "question", "performance", "access", "billing", "onboarding", "other"])),
    severity = select(p, "Severity", choices(["normal", "high", "blocker", "low"])),
    via = select(p, "Reported via", [["", "Unknown"], ...choices(CHANNELS)]),
    body = field(p, "What they said, verbatim where you have it", "textarea"),
    next = field(p, "Next action"),
    due = field(p, "Next action date", "date");
  add(
    p,
    add(
      node("div", "actions"),
      button(
        "Open ticket",
        async () => {
          if (!a.value) throw new Error("Choose the relationship that reported this.");
          const data = { account_id: Number(a.value), title: title.value, kind: kind.value, severity: severity.value };
          if (via.value) data.reported_via = via.value;
          if (body.value) data.body = body.value;
          if (next.value) data.next_action = next.value;
          if (due.value) data.next_action_date = due.value;
          await api("tickets", data);
          close();
          view = "tickets";
          await refresh();
          toast("Ticket opened and the report logged on the timeline.");
        },
        "button primary",
      ),
    ),
  );
}
async function ticketDialog(id) {
  const t = await api("tickets/" + id),
    p = open(`Ticket #${id}`);
  add(p, tag(t.severity, ["blocker", "high"].includes(t.severity) ? "amber" : "gray"), tag(t.status.replaceAll("_", " "), "gray"), node("h3", "", t.title));
  details(p, [
    ["Relationship", t.account_name],
    ["Kind", t.kind],
    ["Area", t.area],
    ["Reported", [t.reported_at, t.reported_via].filter(Boolean).join(" via ")],
    ["Expected", t.expected],
    ["Next step", t.next_action && `${t.next_action} (${t.next_action_date || "no date"})`],
    ["Owner", t.owner],
    ["Resolution", t.resolution],
    ["Release", t.release_ref],
    ["Commit", t.commit_ref],
    ["Evidence", t.evidence],
    ["Fixed", t.fixed_at],
    ["Closed", t.closed_at],
    ["Customer told", t.notified_at && `${t.notified_at} via ${t.notified_via || "?"}${t.notification_verified ? " (verified sent mail)" : " (recorded by a person)"}`],
    ["What they were told", t.notified_note],
    ...Object.entries(t.custom).map(([k, v]) => [fieldLabel("ticket", k), v]),
  ]);
  if (t.body) {
    label(p, "WHAT THEY SAID");
    p.append(node("div", "evidence", t.body));
  }
  label(p, "MOVE IT ALONG");
  const status = select(p, "Status", choices(["open", "triaged", "in_progress", "waiting_on_client", "fixed", "closed", "wont_do", "duplicate"]));
  status.value = t.status;
  const resolution = field(p, "Resolution, in the customer's words", "text", t.resolution || ""),
    release = field(p, "Release reference", "text", t.release_ref || ""),
    evidence = field(p, "Evidence (link, report, query)", "text", t.evidence || "");
  const actions = node("div", "actions");
  add(
    actions,
    button("Save", async () => {
      const values = {};
      if (resolution.value !== (t.resolution || "")) values.resolution = resolution.value;
      if (release.value !== (t.release_ref || "")) values.release_ref = release.value;
      if (evidence.value !== (t.evidence || "")) values.evidence = evidence.value;
      if (status.value !== t.status) await api("ticket-status", { id, status: status.value, ...values });
      else if (Object.keys(values).length) await api("records", { object_type: "ticket", id, values });
      await refresh();
      await ticketDialog(id);
      toast("Ticket saved.");
    }, "button primary"),
  );
  if ((t.fixed_at || ["fixed", "closed"].includes(t.status)) && !t.notified_at)
    actions.prepend(button("Record that you told them", () => notifyForm(t)));
  p.append(actions);
}
function notifyForm(t) {
  const p = open(`Told the customer: #${t.id}`);
  p.append(node("p", "hint", "Record what you said and how. This is your own record, not a verified sent message; Gmail-sourced proposals are the verified path."));
  const via = select(p, "How did you tell them?", choices(CHANNELS)),
    note = field(p, "What you told them", "textarea"),
    at = field(p, "When (blank = now)", "date");
  add(
    p,
    add(
      node("div", "actions"),
      button(
        "Record update",
        async () => {
          const data = { id: t.id, via: via.value, note: note.value };
          if (at.value) data.at = at.value;
          await api("ticket-notify", data);
          close();
          await refresh();
          toast("Customer update recorded.");
        },
        "button primary",
      ),
    ),
  );
}
function renderQualify(c) {
  label(c, "STILL TO QUALIFY", `${state.qualification_gaps.length} BUYERS`);
  if (!state.qualification_gaps.length) empty(c, "Every live buyer is fully qualified.");
  for (const g of state.qualification_gaps) {
    const meter = add(node("div", "meter"), node("span"));
    meter.firstChild.style.width = g.pct + "%";
    const r = row(
      c,
      g.name,
      `${g.lifecycle} · ${g.status.replace("_", " ")} · missing ${g.missing.map((k) => questionLabel(k)).join(", ")}`,
      button("Qualify", () => qualifyDialog(g.id)),
      add(node("div", "row-meta", `${g.pct}%`), meter),
    );
    r.prepend(tag(g.confidence, "gray"));
  }
  c.append(node("p", "hint", "Unknown stays unknown: leave a field empty rather than guessing, so it stays in this queue. Add your own questions in Make it yours."));
}
function questionLabel(key) {
  return { entity_type: "entity", team_size: "team size", current_tools: "tools", pain_points: "pain points", use_case: "use case", budget_authority: "budget", decision_process: "decision process", fit_score: "fit" }[key] || fieldLabel("account", key);
}
async function qualifyDialog(id) {
  const account = await api("accounts/" + id),
    q = account.qualification,
    p = open(`Qualify ${account.name}`);
  p.append(node("p", "hint", `${q.status.pct}% answered · ${q.status.status.replace("_", " ")}`));
  const inputs = {};
  for (const question of q.questions) {
    const def = state.fields.find((f) => f.object_type === "account" && f.key === question.key);
    if (def?.type === "choice") {
      inputs[question.key] = select(p, question.label, [["", "Unknown"], ...def.choices.map((x) => [x, x])]);
      inputs[question.key].value = question.value ?? "";
    } else if (question.key === "budget_authority") {
      inputs[question.key] = select(p, question.label, [["", "Unknown"], ...choices(["yes", "no", "influencer", "unknown"])]);
      inputs[question.key].value = question.value ?? "";
    } else inputs[question.key] = field(p, question.label, ["team_size", "fit_score"].includes(question.key) || ["number", "integer"].includes(def?.type) ? "number" : "text", question.value ?? "");
  }
  const confidence = select(p, "Your confidence in this dossier", choices(["low", "medium", "high"]));
  confidence.value = q.record?.confidence || "low";
  add(
    p,
    add(
      node("div", "actions"),
      button(
        "Save answers",
        async () => {
          const values = { account_id: id, confidence: confidence.value };
          for (const question of q.questions) {
            const v = inputs[question.key].value;
            if (String(v) !== String(question.value ?? "")) values[question.key] = v === "" ? null : ["team_size", "fit_score"].includes(question.key) ? Number(v) : v;
          }
          await api("qualification", values);
          await refresh();
          await qualifyDialog(id);
          toast("Qualification saved.");
        },
        "button primary",
      ),
    ),
  );
  label(p, "EVIDENCE", `${q.evidence.length}`);
  if (!q.evidence.length) empty(p, "No evidence recorded.", "A number with no source is a rumour.");
  for (const e of q.evidence) row(p, e.claim, [e.source, e.observed_at, e.url].filter(Boolean).join(" · "));
  const claim = field(p, "Claim"),
    source = field(p, "Where it came from");
  p.append(
    add(
      node("div", "actions"),
      button("Add evidence", async () => {
        await api("evidence", { account_id: id, claim: claim.value, source: source.value });
        await qualifyDialog(id);
      }),
    ),
  );
}
function renderYours(c) {
  const cols = node("div", "two-col"),
    left = node("div"),
    right = node("div");
  label(left, "YOUR FIELDS", `${state.fields.length} DEFINED`);
  left.append(node("p", "hint", "Custom fields hold the data only your business needs, on relationships, contacts, opportunities, tickets, interactions or events. Mark an account field as a qualification question and it counts toward the Qualification queue."));
  if (!state.fields.length) empty(left, "No custom fields yet.");
  for (const f of state.fields) {
    const r = row(left, f.label, `${f.object_type}.${f.key} · ${f.type}${f.choices ? " (" + f.choices.join(", ") + ")" : ""} · ${f.used} value${f.used === 1 ? "" : "s"}`);
    r.prepend(tag(f.qualification ? "QUALIFICATION" : f.object_type, f.qualification ? "" : "gray"));
  }
  left.append(button("+ Define a field", fieldForm, "button primary"));
  label(right, "HOW TO MAKE IT YOURS");
  const panel = node("div", "panel");
  const steps = node("ol", "steps");
  for (const s of [
    "Add a custom field here for anything your business tracks that others would not: a licence number, a plan tier, a region code.",
    "Mark the account fields that decide whether someone can buy as qualification questions.",
    "Use the CLI the same way: founder-crm field define account plan_tier \"Plan tier\" --type choice --choices free,team,enterprise",
    "For a change to the app itself (a new view, a new rule, your own labels), open this folder in Claude Code and describe one concrete change. Keep human review and add tests.",
    "Back up data/ before a schema change. Upgrades keep every row and write a backup first.",
  ])
    steps.append(node("li", "", s));
  add(panel, node("div", "eyebrow", "FIELDS → QUESTIONS → CODE"), node("h2", "", "Start with data, then change the code."), steps);
  right.append(panel);
  label(right, "WHERE CHANGES BELONG");
  details(right, [
    ["Labels, layout, colours", "founder_crm/static/"],
    ["A built-in field", "schema.sql + Store.init upgrade + core.py"],
    ["A workflow or rule", "core.py, with a test in tests/"],
    ["How Claude operates", ".claude/skills/ and CLAUDE.md"],
    ["Guide", "docs/personalise.md"],
  ]);
  right.append(node("p", "hint", `Schema version ${state.schema_version}.`));
  add(cols, left, right);
  c.append(cols);
}
function fieldForm() {
  const p = open("Define a custom field");
  const type = select(p, "Record", choices(["account", "contact", "opportunity", "ticket", "interaction", "event"])),
    key = field(p, "Key (lower_snake_case)"),
    lab = field(p, "Label"),
    kind = select(p, "Type", choices(["text", "number", "integer", "date", "boolean", "choice", "json"])),
    opts = field(p, "Choices, comma separated (choice only)"),
    qual = select(p, "Qualification question?", [["0", "No"], ["1", "Yes (account fields only)"]]),
    help = field(p, "Help text (optional)");
  add(
    p,
    add(
      node("div", "actions"),
      button(
        "Define field",
        async () => {
          const data = { object_type: type.value, key: key.value, label: lab.value, type: kind.value, qualification: qual.value === "1" };
          if (kind.value === "choice") data.choices = opts.value.split(",").map((s) => s.trim()).filter(Boolean);
          if (help.value) data.help = help.value;
          await api("fields", data);
          close();
          await refresh();
          toast("Field defined.");
        },
        "button primary",
      ),
    ),
  );
}
function renderPipeline(c) {
  const top = label(c, "CUSTOMER PIPELINE");
  top.append(button("+ Add opportunity", opportunityForm));
  const lanes = node("div", "pipeline");
  for (const stage of [
    "discovery",
    "qualified",
    "demo",
    "pilot",
    "proposal",
    "negotiation",
    "won",
    "lost",
    "parked",
  ]) {
    const lane = node("div", "lane");
    lane.append(node("div", "lane-title", stage));
    for (const o of state.opportunities.filter((o) => o.stage === stage)) {
      const d = node("div", "deal", o.title);
      d.append(node("small", "", o.account_name));
      lane.append(d);
    }
    lanes.append(lane);
  }
  c.append(lanes);
  c.append(
    node(
      "p",
      "hint",
      "Investors, advisers, partners and vendors stay in Relationships. A new sales stage can be proposed through Claude with source evidence.",
    ),
  );
}
function renderConnections(c) {
  flow(c);
  for (const [title, status, desc, fn] of [
    [
      "Claude MCP",
      "LOCAL TOOLS",
      "Read the CRM, capture notes and stage updates. Approval stays in this dashboard.",
      claudeHelp,
    ],
    [
      "Gmail",
      state.integrations.gmail_configured ? "CONFIGURED" : "NOT CONNECTED",
      "A bounded read-only pull. No labels, read status, archives, attachments or outgoing mail.",
      gmailForm,
    ],
    [
      "Web3Forms",
      state.integrations.forms_configured
        ? "RECEIVER CONFIGURED"
        : "NOT CONNECTED",
      "Website submissions become source evidence. A form does not create or promote a relationship on its own.",
      () => {
        const p = open("Web3Forms setup");
        p.append(
          node(
            "p",
            "hint",
            "Set a private webhook token of at least 32 characters. Web3Forms sends JSON to your HTTPS relay at /hooks/web3forms/<token>. Only expose that route; keep the dashboard local. See docs/integrations.md. Native Web3Forms webhooks require an eligible paid plan.",
          ),
        );
      },
    ],
    [
      "Jev",
      state.integrations.jev_configured
        ? state.integrations.model_sharing
          ? "ENABLED"
          : "SHARING OFF"
        : "NOT CONNECTED",
      "Advisory checks on individual proposals. No automatic database writes.",
      () => {
        const p = open("Jev setup");
        add(
          p,
          node(
            "p",
            "hint",
            "Set FOUNDER_CRM_JEV_API_KEY and choose typesafe or openrouter. To share a proposal and its evidence with the provider, explicitly set FOUNDER_CRM_ALLOW_MODEL_EGRESS=1. Ask Jev on a proposal to make a call.",
          ),
          node(
            "p",
            "notice",
            "No private credentials from other projects are loaded. Demo records are synthetic.",
          ),
        );
      },
    ],
  ]) {
    const r = row(c, title, desc, button("Setup", fn));
    r.prepend(tag(status, status === "NOT CONNECTED" ? "gray" : ""));
  }
}
function noteForm() {
  const p = open("Capture a conversation");
  const subject = field(p, "What was this about?"),
    sender = field(p, "Contact email (optional)", "email"),
    body = field(p, "What happened?", "textarea");
  add(
    p,
    add(
      node("div", "actions"),
      button(
        "Capture note",
        async () => {
          await api("intake", {
            external_id: crypto.randomUUID(),
            subject: subject.value,
            sender: sender.value,
            body: body.value,
            direction: "internal",
          });
          close();
          view = "inbox";
          await refresh();
          toast("Note captured as evidence.");
        },
        "button primary",
      ),
    ),
  );
}
function accountForm() {
  const p = open("Add a relationship"),
    name = field(p, "Company or relationship name"),
    rel = select(p, "Relationship", [
      ["unknown", "Unknown"],
      ["prospect", "Customer prospect"],
      ["customer", "Customer"],
      ["investor", "Investor"],
      ["partner", "Partner"],
      ["adviser", "Adviser"],
      ["vendor", "Vendor"],
      ["other", "Other"],
    ]);
  add(
    p,
    add(
      node("div", "actions"),
      button(
        "Add relationship",
        async () => {
          await api("accounts", { name: name.value, relationship: rel.value });
          close();
          view = "people";
          await refresh();
          toast("Relationship added.");
        },
        "button primary",
      ),
    ),
  );
}
function contactForm(accountId) {
  const p = open("Add a contact"),
    name = field(p, "Contact name"),
    email = field(p, "Email", "email");
  add(
    p,
    add(
      node("div", "actions"),
      button(
        "Add contact",
        async () => {
          await api("contacts", {
            account_id: accountId,
            name: name.value,
            email: email.value || null,
          });
          await refresh();
          await history(accountId);
        },
        "button primary",
      ),
    ),
  );
}
function opportunityForm() {
  const p = open("Add a sales opportunity");
  const a = select(
    p,
    "Customer or prospect",
    state.accounts
      .filter((a) => ["customer", "prospect"].includes(a.relationship))
      .map((a) => [a.id, a.name]),
  );
  const title = field(p, "Opportunity"),
    stage = select(
      p,
      "Stage",
      ["discovery", "qualified", "demo", "pilot", "proposal", "negotiation", "won", "lost", "parked"].map((s) => [
        s,
        s,
      ]),
    );
  add(
    p,
    add(
      node("div", "actions"),
      button(
        "Add opportunity",
        async () => {
          if (!a.value)
            throw new Error("Add a customer or prospect relationship first.");
          await api("opportunities", {
            account_id: Number(a.value),
            title: title.value,
            stage: stage.value,
          });
          close();
          await refresh();
        },
        "button primary",
      ),
    ),
  );
}
function gmailForm() {
  const p = open("Pull recent Gmail messages");
  add(
    p,
    node(
      "p",
      "hint",
      "Reads messages into local intake using the configured access token. No message content goes to Jev during this pull.",
    ),
  );
  const q = field(p, "Gmail query", "text", "in:inbox newer_than:14d"),
    limit = field(p, "Maximum messages", "number", "20");
  add(
    p,
    add(
      node("div", "actions"),
      button(
        "Pull read-only",
        async () => {
          const r = await api("gmail-sync", {
            query: q.value,
            limit: Number(limit.value),
          });
          close();
          view = "inbox";
          await refresh();
          toast(`${r.new} new messages, ${r.duplicates} duplicates skipped.`);
        },
        "button primary",
      ),
    ),
  );
}
function claudeHelp() {
  const p = open("Use Claude as your dashboard");
  add(
    p,
    node(
      "p",
      "hint",
      "Install the MCP extra and use an absolute path in your Claude MCP configuration. See README.md for the full setup.",
    ),
    node(
      "pre",
      "",
      'python -m pip install -e ".[mcp]"\nclaude mcp add --transport stdio founder-crm -- /absolute/path/to/.venv/bin/founder-crm --db /absolute/path/to/data/crm.db mcp',
    ),
    node(
      "p",
      "hint",
      "Try: “What do I owe people today?” or “Log this call and propose a follow-up.” The bundled skills cover daily review, conversation capture and proposal review.",
    ),
  );
}
document.querySelectorAll("[data-view]").forEach(
  (e) =>
    (e.onclick = () => {
      view = e.dataset.view;
      render();
    }),
);
$("#new-note").onclick = noteForm;
$("#new-account").onclick = accountForm;
$("#claude-help").onclick = claudeHelp;
$("#close-dialog").onclick = close;
$("#today-date").textContent = new Date().toLocaleDateString(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
});
refresh().catch((e) => {
  empty($("#content"), "Could not open the workspace.", e.message);
  toast(e.message, true);
});
