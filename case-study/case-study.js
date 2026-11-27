"use strict";

(() => {
  const byId = id => document.getElementById(id);
  const packet = JSON.parse(byId("email-data").textContent);
  const model = JSON.parse(byId("reply-model").textContent);
  const options = document.querySelectorAll("[data-try-reply]");
  const panel = byId("reply-result");
  const currency = new Intl.NumberFormat("en-AU", {
    style: "currency", currency: packet.bill.currency, minimumFractionDigits: 0, maximumFractionDigits: 2
  });

  for (const button of options) {
    button.addEventListener("click", () => {
      const reply = button.querySelector("[data-reply-text]").textContent.trim();
      const {result} = buildCustomScenario(reply, packet, model);
      const item = result.items.find(line => line.line_id === packet.reply_editor.line_id);
      const citation = item.quotes.find(quote => quote.message_id === packet.reply_editor.buyer_message_id);
      const supported = currency.format(result.supported_cents / 100);
      const toQuery = currency.format(result.query_cents / 100);

      for (const option of options) option.setAttribute("aria-pressed", String(option === button));
      byId("finding-label").textContent = item.verdict_label;
      byId("finding-reason").textContent = item.reason;
      byId("finding-reply").textContent = citation.text;
      byId("amount-supported").textContent = supported;
      byId("amount-query").textContent = toQuery;
      byId("finding-followup").textContent = item.draft_question;
      byId("finding-followup").hidden = !item.draft_question;
      panel.dataset.status = item.status;
      panel.hidden = false;
      byId("finding-label").focus();
      byId("reply-status").textContent = supported + " supported. " + toQuery + " to query.";
    });
  }
})();
