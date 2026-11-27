/* Purchasing checks for the two offers in the fictional Banksia Rooms email. */
const replyPrice = /(?:au?\s*\$|\$|aud\s*)\s*(\d+(?:,\d{3})*(?:\.\d+)?)|\b(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:dollars?\b|aud\b)/g;

function readReplyPrices(words) {
  return Array.from(words.matchAll(replyPrice), match => Number((match[1] || match[2]).replaceAll(",", "")) * 100);
}

// The model recognises intent. Limit automatic support to the scope of this particular offer.
// An unfamiliar service or qualifier should give the reviewer a source to inspect.
const offerVocabulary = new Set((
  "a an the this that our your my me us you we i it its is am are be and as for at of on in to with by " +
  "hi hey hello dear sam reed jo bell regards kind cheers thanks thank you very much many mate yes yep yeah " +
  "great good perfect absolutely happy fine sounds works well okay ok let's lets please kindly can " +
  "approve approved approval authorise authorize authorised authorized agree agreed accept accepted " +
  "confirm confirmed confirming proceed go ahead book booking schedule scheduled lock " +
  "choose chosen select selected send bring take use give have got do get make arrange arranged " +
  "crew electrician team guys visit attendance return come back out work job attend slot option first one former " +
  "th thu thurs thursday evening night after hours closing close closed afterhours banksia rooms " +
  "total amount price charge sum quoted stated figure flat dollars dollar aud au ex excluding exclusive plus gst " +
  "four hundred only exactly from all set done now then time same access building doors see there that's " +
  "suits i'll we're i'm you've sound correct right"
).split(/\s+/));

function assessAfterHours(reply, intent, bill, config, charge, thread) {
  const words = reply.toLowerCase().normalize("NFKC").replace(/[‘’]/g, "'").replace(/[–—‑]/g, "-");
  const amount = new Intl.NumberFormat("en-AU", {style: "currency", currency: bill.currency,
    minimumFractionDigits: 0}).format(charge.cents / 100);
  const confirm = `Could you confirm whether you approved the Thursday after-closing visit for ${amount} ex GST at Banksia Rooms?`;
  const open = (verdict_label, reason, draft_question = confirm) => ({
    status: "unclear", verdict_label, reason, draft_question
  });
  const priceWording = words.replace(/\bfour hundred (?:dollars|aud)\b/g, "400 dollars");
  const prices = readReplyPrices(priceWording);
  const thursday = /\b(?:thu(?:rs(?:day)?)?|after[- ](?:hours|closing|close)|evening|night|first (?:option|one)|option (?:one|1)|former)\b/.test(words);
  const friday = /\b(?:fri(?:day)?|extra installer|(?:normal|regular|business) hours|second (?:option|one)|option (?:two|2)|latter)\b/.test(words);
  const negative = /\b(?:no(?! problem\b)|not|never|cannot|can't|won't|don't|didn't|isn't|haven't|unable|cancel\w*|declin\w*|reject\w*|withdraw\w*|revoke\w*|refus\w*|hold off|hold on|do neither|on hold|wait|stop|scratch that)\b/.test(words);
  const conditional = /\b(?:if|unless|until|pending|once|subject to|provided|providing|as long as|assuming|depending|only when|before (?:we|i|you)|on condition|as soon as|yet to|would approve|will approve|to be approved)\b/.test(words);
  const otherSite = /\b(?:another (?:job|site)|different (?:job|site)|fern hall|(?:at|for) (?!banksia rooms\b)(?:the )?(?:[a-z]+ ){1,3}(?:hall|rooms|depot|site|school|office|warehouse))\b/.test(words)
    || (words.match(/\b[a-z]{2,5}-\d+\b/g) || []).some(job => job !== bill.job_ref.toLowerCase());
  if (otherSite) return open("Check the job", "The reply mentions a different job or site. The invoice and this email thread refer to Banksia Rooms.");
  if (conditional) return open("Conditional", "The reply ties the booking to a condition. It leaves open whether the condition was met.",
    "Was the condition met, and did Jo then confirm the Thursday visit and its price?");
  if (negative) return open("Hold for review", "The wording reads as a refusal, hold or change of instruction. It cannot confirm this booking.",
    "Was a later, unconditional approval issued for the Thursday visit?");
  if (/\b(?:said|says|apparently|told me|claims?|according to|wrote|thought|heard|recall|used to|last (?:week|month|thursday)|previously|yesterday|hypothetical|pretend|(?:jo|sam|he|she|they|the \w+) (?:approved|approves|agreed))\b/.test(words)
      || /["“”]/.test(words)) return open("Check who approved", "The reply may be quoting or recalling someone else's decision. Check for Jo's own instruction for this visit.");
  if (friday && !thursday) return open("Different work", "The reply points to the Friday installer. The bill charges for the Thursday after-hours visit.",
    "Should this line cover the Friday installer, or is there a separate approval for Thursday?");
  if ((thursday && friday) || /\b(?:both|either|whichever|any option)\b/.test(words)) return open("Check the option", "The reply refers to more than one possible booking. Both offers cost the same, so the price cannot identify the billed visit.",
    "Which $400 option did you agree to, the Thursday visit or the Friday installer?");
  if (/\b(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|sat(?:urday)?|sun(?:day)?|next week|morning|afternoon|lunch(?:time)?)\b/.test(words)) return open("Check the timing", "The timing in the reply differs from the supplier's Thursday after-closing offer.");
  if (/\?|^\s*(?:who|what|where|when|which|how much|how many|can you (?:quote|price|confirm|explain)|could you (?:quote|price|confirm|explain))\b/.test(words)
      || intent.label === "question") return open("Question raised", "The wording asks a question. The reviewer still needs a clear instruction to book the work.");
  if (intent.label === "conditional") return open("Conditional", "The wording suggests a condition or a decision still to come. Ask Jo for a final instruction.");
  if (!thursday) return open("Which option?", "The reply leaves the choice open. Sam offered two $400 bookings and the bill covers only the Thursday after-closing visit.",
    "Did you choose the Thursday after-closing visit or Friday's extra installer?");
  if (/[€£¥₹]|\b(?:usd|nzd|eur|gbp|cad|sgd|us\s*dollars?|nz\s*dollars?|pounds?|euros?|cents?|us\s*\$|nz\s*\$)/.test(words)
      || /\b(?:including|includes?|inc|incl|inclusive|with)\.?\s+(?:of\s+)?(?:gst|tax)|\b(?:gst|tax)[ -]inclusive\b|[%/]|(?:^|\s)per\s+(?:hour|person|day)|[$]\s*-|(?:\bto\s*|[-–~]\s*)\$?\d/.test(words.replaceAll(bill.job_ref.toLowerCase(), ""))) {
    return open("Check the price basis", "The reply uses a different or unclear currency, rate or tax basis. The bill is for one visit at AUD $400 excluding GST.");
  }
  if (!prices.length) return open("Amount missing", `The reply identifies Thursday, but it does not confirm the billed price of ${amount}.`);
  if (prices.some(value => value !== charge.cents)) return open("Check the amount", `The price in the reply does not unambiguously match the ${amount} on the bill.`);
  const remainingTerms = priceWording.replaceAll(bill.job_ref.toLowerCase(), "").replace(replyPrice, " ").replace(/\boption 1\b/g, "");
  if (/\d/.test(remainingTerms)) return open("Check the figures", "The reply includes another figure as well as the price. Confirm the quantity, timing and total for this visit.");
  if (/\b(?:each|plus (?!gst\b)|per|less|percent|about|around|roughly|approx\w*|up to|budget|maximum|estimate|maybe|perhaps|possibly|might|tentative\w*|probably|unsure|instead|other than|except|discount|deposit|disposal|removal|collection)\b/.test(words)) {
    return open("Clarify the terms", "The reply qualifies the price or the work. Ask which service and final price Jo agreed to.");
  }
  if (intent.label === "decline" && intent.confidence >= 0.58) return open("Hold for review", "The wording reads as a refusal or change of instruction. Ask Jo whether the visit was booked.");
  const agreement = /\b(?:approve[d]?|authori[sz]e[d]?|agree[d]?|accept(?:ed)?|confirm(?:ed)?|proceed|go ahead|book|lock (?:it|that) in|schedule|let's|choose|select|sounds good|works|fine|yes|okay|ok|happy (?:to|with))\b/.test(words);
  if (!agreement || intent.label !== "approve" || intent.confidence < 0.58) return open("Intent unclear", "The wording does not give the reader a clear instruction to book the named work at this price.");
  const tokens = words.replaceAll(bill.job_ref.toLowerCase(), "").match(/[a-z]+(?:'[a-z]+)?/g) || [];
  const unrecognised = [...new Set(tokens.filter(word => !offerVocabulary.has(word)))];
  if (unrecognised.length) return open("Check the wording",
    "The reader could not link “" + unrecognised.slice(0, 3).join(" ") + "” to the offered visit. Check that the reply covers the same work and terms as the bill.");
  if (!thread.eligible || config.approval_limit_cents < charge.cents) return open("Check authority", "The supplier, job or buyer's spending limit does not support this charge.");
  return {status: "supported", verdict_label: "Supported", draft_question: "",
    reason: `The wording reads as an instruction to go ahead. It selects the Thursday after-closing visit and confirms the billed ${amount}.`,
    authority_note: `${config.buyer} is authorised for this amount on the sample job.`};
}

function buildCustomScenario(reply, data, model) {
  const config = data.reply_editor;
  if (typeof reply !== "string" || !reply.trim() || reply.length > config.max_length) {
    throw new RangeError("Enter a reply within the displayed character limit.");
  }
  const original = data.scenarios.find(scenario => scenario.id === config.template_scenario);
  const charge = data.bill.lines.find(line => line.id === config.line_id);
  const thread = original.threads.find(item => item.id === config.thread_id);
  const intent = classifyReplyIntent(reply, model);
  const decision = assessAfterHours(reply, intent, data.bill, config, charge, thread);
  const threads = original.threads.map(item => item !== thread ? item : {...thread,
    messages: thread.messages.map(msg => msg.id === config.buyer_message_id ? {...msg, body: reply} : msg)});
  const offer = thread.messages.find(msg => msg.id === config.offer_message_id);
  const quotes = [{message_id: config.buyer_message_id, text: reply}, {message_id: offer.id, text: offer.body}];
  const items = original.result.items.map(item => item.line_id !== charge.id ? item :
    {line_id: charge.id, amount_cents: charge.cents, thread_id: thread.id, quotes, ...decision});
  const supported = items.reduce((sum, item) => sum + (item.status === "supported" ? item.amount_cents : 0), data.bill.base_cents);
  return {id: "custom", label: "Your reply", threads, result: {
    items, supported_cents: supported, query_cents: data.bill.total_cents - supported}};
}
