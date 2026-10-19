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
  document
    .querySelectorAll("[data-view]")
    .forEach((e) => e.classList.toggle("active", e.dataset.view === view));
  const stats = $("#stats");
  stats.replaceChildren();
  for (const [value, title] of [
    [state.tasks.length, "Open next steps"],
    [state.proposals.length, "Updates to review"],
    [state.counts.contacts, "People in the story"],
    [
      state.tickets.filter((t) => t.fixed_at && !t.notified_at).length,
      "Fixed, update still owed",
    ],
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
  label(left, "CLOSE THE LOOP");
  const owed = state.tickets.filter((t) => t.fixed_at && !t.notified_at);
  if (!owed.length)
    empty(left, "No recorded fixes are waiting for a client update.");
  for (const t of owed)
    row(left, t.title, t.account_name, null, tag("UPDATE OWED", "amber"));
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
async function history(id) {
  const a = await api("accounts/" + id),
    p = open(a.name);
  add(p, tag(a.relationship), node("p", "hint", a.lifecycle));
  label(p, "CONTACTS");
  for (const person of a.contacts)
    row(p, person.name, person.email || "No email recorded");
  p.append(button("+ Add contact", () => contactForm(id)));
  label(p, "RELATIONSHIP HISTORY");
  if (!a.interactions.length) empty(p, "No interactions recorded yet.");
  for (const i of a.interactions)
    row(p, i.summary, `${i.direction} · ${i.created_at}`);
  label(p, "NEXT STEPS");
  for (const t of a.tasks)
    row(p, t.title, `${t.status} · ${t.due_date || "No date"}`);
}
function renderPipeline(c) {
  const top = label(c, "CUSTOMER PIPELINE");
  top.append(button("+ Add opportunity", opportunityForm));
  const lanes = node("div", "pipeline");
  for (const stage of [
    "discovery",
    "demo",
    "pilot",
    "proposal",
    "won",
    "lost",
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
      ["discovery", "demo", "pilot", "proposal", "won", "lost"].map((s) => [
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
