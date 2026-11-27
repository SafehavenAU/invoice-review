/* Run with node --test tests/custom_reply.test.cjs. No network or browser required. */
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const read = name => readFileSync(path.join(root, name), "utf8");
const context = vm.createContext({ structuredClone });
for (const file of ["demo/reply-intent.js", "demo/reply-policy.js"]) {
  vm.runInContext(read(file), context, { filename: file });
}
const makeScenario = vm.runInContext("buildCustomScenario", context);
const model = JSON.parse(read("invoice_review/data/reply_model.json"));
const packet = read("demo/email-approvals.html").match(
  /<script\b[^>]*\bid=["']email-data["'][^>]*>([\s\S]*?)<\/script>/,
);
assert.ok(packet, "Published demo must include the original bill and both email scenarios.");
const source = JSON.parse(packet[1]);

function analyse(text) {
  const scenario = makeScenario(text, source, model);
  const afterHours = scenario.result.items.find(item => item.line_id === "after_hours");
  const disposal = scenario.result.items.find(item => item.line_id === "disposal");
  assert.ok(afterHours);
  assert.equal(disposal.status, "price_only", "The separate disposal email has not changed.");
  assert.equal(scenario.result.supported_cents + scenario.result.query_cents, 540000);
  assert.ok(afterHours.reason.trim().length > 12, "Explain the finding to a reviewer.");
  return { scenario, item: afterHours };
}

for (const reply of [
  "Please book Thursday after closing for $400 ex GST.",
  "Sam, I approve the $400 Thursday evening crew visit at Banksia Rooms.",
  "The $400 after-hours visit on Thursday is approved. Please lock it in.",
  "I approve Thursday after closing for AUD $400. Approved amount: $400.",
]) {
  test(`clear selected charge: ${reply}`, () => {
    const { scenario, item } = analyse(reply);
    assert.equal(item.status, "supported", item.reason);
    assert.equal(scenario.result.query_cents, 20000);
  });
}

const unresolved = [
  ["unspecified option", "Sounds good, book it for $400."],
  ["two options", "I approve $400 for either Thursday evening or the Friday installer."],
  ["conditional", "I approve the Thursday evening visit for $400 if the building manager agrees."],
  ["declined", "Please do not book Thursday after closing for $400."],
  ["revoked", "I approved Thursday after closing for $400 yesterday. Cancel that booking."],
  ["wrong amount", "Please book Thursday after closing for $450 ex GST."],
  ["different slot", "Please book the extra installer on Friday for $400 ex GST."],
  ["competing amounts", "I approve Thursday after closing. Was that $400 or $450?"],
  ["wrong currency", "I approve the Thursday after-hours visit for USD $400."],
  ["mixed currencies", "Please book Thursday after closing for $400, or EUR 400 if you prefer."],
  ["different job", "I approve the Thursday after-hours visit for $400 at Fern Hall."],
  ["changes the decision", "Thursday after closing is $400. Please only book Friday."],
  ["only asks for a price", "Can you quote $400 for Thursday after closing?"],
  ["gibberish", "qqzvx plmrr"],
  ["unrelated", "Our stationery delivery is next Wednesday."],
  ["multiple visits at a unit price", "I approve two Thursday after-hours visits for $400 each."],
  ["extra fee for the same amount", "I approve the Thursday after-hours visit for $400 plus a $400 callout."],
  ["discount changes the total", "I approve the Thursday after-hours visit for $400 less ten percent."],
  ["hypothetical agreement", "I would approve the Thursday after-hours visit for $400."],
  ["pending decision", "I have yet to approve Thursday after closing at $400."],
  ["third party agreement", "The builder approves the Thursday after-hours visit for $400."],
  ["unrelated service at the same time and price", "I approve the carpet cleaning on Thursday evening for $400."],
];

for (const [name, reply] of unresolved) {
  test(`keeps after-hours charge open: ${name}`, () => {
    const { scenario, item } = analyse(reply);
    assert.notEqual(item.status, "supported", item.reason);
    assert.equal(scenario.result.query_cents, 60000);
    assert.ok(item.draft_question.trim().length > 6, "Give the reviewer a useful follow-up.");
  });
}

test("explains which detail stops a plausible reply from supporting the charge", () => {
  const checks = [
    ["Yes, go ahead.", /option|which|choose|select|slot|Thursday|Friday|visit|amount/i],
    ["I approve the Thursday after-hours visit for $375.", /375|amount|price|different|match|400/i],
    ["I approve the Thursday after-hours visit for $400 if the client signs off.", /if|condition|confirm|sign.off|depends/i],
  ];
  for (const [reply, expected] of checks) {
    const { item } = analyse(reply);
    assert.notEqual(item.status, "supported");
    assert.match(item.reason, expected, reply);
  }
});

test("a custom result cites the typed source without mutating either saved replay", () => {
  const before = JSON.stringify(source);
  const reply = 'Before I agree, please explain "<pending approval>" to me.';
  const { item, scenario } = analyse(reply);
  const messages = scenario.threads.find(thread => thread.id === item.thread_id).messages;
  const custom = messages.find(message => message.body === reply);
  assert.ok(custom, "Display the unaltered typed words in the original conversation.");
  assert.ok(item.quotes.some(quote => quote.message_id === custom.id && quote.text &&
    custom.body.includes(quote.text)), "Link the explanation to the words in the new reply.");
  const repeated = analyse("Thanks. Both proposals sound interesting.").scenario;
  assert.equal(JSON.stringify(source), before);
  assert.ok(!JSON.stringify(repeated).includes("<pending approval>"));
});

test("rejects empty, whitespace-only, and oversized submissions", () => {
  for (const reply of ["", "  \n\t ", "x".repeat(1001)]) {
    assert.throws(() => makeScenario(reply, source, model));
  }
});
