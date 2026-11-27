/* Classify new text with the fitted weights in reply_model.json. No network or state. */
function classifyReplyIntent(text, model) {
  const cleaned = text.toLowerCase().replaceAll("’", "'")
    .replaceAll("won't", "will not").replaceAll("can't", "cannot").replaceAll("n't", " not")
    .replaceAll("'ll", " will").replaceAll("'re", " are")
    .replace(/(?:aud\s*|\$\s*)[\d,.]+|\b\d+(?:[,.]\d+)*\b/g, " amount ");
  const words = cleaned.match(/[a-z]+|\?/g) || [];
  const terms = new Set();
  let knownWords = 0;
  words.forEach((word, i) => {
    const term = "w:" + word;
    terms.add(term);
    if (Object.hasOwn(model.weights, term)) knownWords++;
    if (word.length >= 6) terms.add("p:" + word.slice(0, 5));
    if (i) terms.add("b:" + words[i - 1] + "/" + word);
  });
  const sentence = " " + words.join(" ") + " ";
  for (const [name, phrases] of Object.entries(model.cue_groups)) {
    if (phrases.some(phrase => sentence.includes(" " + phrase + " "))) terms.add("c:" + name);
  }
  if (!words.length || !knownWords || knownWords / words.length < 0.35) {
    return {label: "uncertain", confidence: 0};
  }
  const scores = model.bias.slice();
  for (const term of terms) {
    const weights = model.weights[term];
    if (weights) weights.forEach((weight, i) => { scores[i] += weight; });
  }
  const best = Math.max(...scores);
  const total = scores.reduce((sum, score) => sum + Math.exp(score - best), 0);
  return {label: model.labels[scores.indexOf(best)], confidence: 1 / total};
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {classifyReplyIntent};
}
