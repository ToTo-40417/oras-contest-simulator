const byId = id => document.getElementById(id);
const categories = new Map([
  ["cool", "かっこよさ"], ["beauty", "うつくしさ"], ["cute", "かわいさ"],
  ["clever", "かしこさ"], ["tough", "たくましさ"],
]);
const ranks = new Map([
  ["normal", "ノーマル"], ["super", "スーパー"], ["hyper", "ハイパー"], ["master", "マスター"],
]);
const conditionInputs = [];
const turnInputs = [];
let options;
let result;
let busy = false;

function fill(select, pairs) {
  select.replaceChildren(...Array.from(pairs, ([id, name]) => new Option(name, id)));
}

function labeled(parent, text, field) {
  const label = document.createElement("label");
  label.append(text, field);
  parent.append(label);
}

fill(byId("category"), [...categories, ["all", "すべての種目"]]);
fill(byId("rank"), [...ranks, ["all", "すべてのランク"]]);
fill(byId("scarf"), [["match", "種目に合わせる"], ...categories]);
for (const name of categories.values()) {
  const field = Object.assign(document.createElement("input"), {
    type: "number", min: 0, max: 255, step: 1, value: 0, required: true,
  });
  conditionInputs.push(field);
  labeled(byId("conditions"), name, field);
}
for (let turn = 1; turn <= 5; turn++) {
  const select = document.createElement("select");
  turnInputs.push(select);
  labeled(byId("turns"), `第${turn}ターン`, select);
}

function selectedSpecies() {
  return options?.species.find(row => row.id === byId("species").value);
}

function searchKey(text) {
  return text.normalize("NFKC").toLowerCase().trim().replace(/[ァ-ヶ]/g,
    letter => String.fromCharCode(letter.charCodeAt(0) - 0x60));
}

function filterSpecies() {
  const select = byId("species");
  const current = select.value;
  const query = searchKey(byId("species-search").value);
  const matches = options.species.filter(row =>
    searchKey(row.name).includes(query) || row.id.includes(query));
  fill(select, [["", matches.length ? "選択してください" : "該当するポケモンがいません"],
    ...matches.map(row => [row.id, row.name])]);
  select.disabled = !matches.length;
  if (matches.some(row => row.id === current)) select.value = current;
  else if (matches.length === 1) select.value = matches[0].id;
  updateSpecies();
}

function updateSpecies() {
  const species = selectedSpecies();
  const moves = species ? species.moves.map(id => [id, options.moves[id]]) : [];
  moves.sort((a, b) => a[1].localeCompare(b[1], "ja"));
  for (const select of turnInputs) {
    const current = select.value;
    fill(select, [["-", "技を出さない"], ...moves]);
    if (moves.some(([id]) => id === current)) select.value = current;
    select.disabled = !species;
  }
  byId("item").options[2].disabled = !species?.mega;
  if (!species?.mega && byId("item").value === "mega") byId("item").value = "none";
  byId("scarf-field").hidden = byId("item").value !== "scarf";
  byId("rayquaza").hidden = species?.id !== "rayquaza";
  byId("run").disabled = busy || !species;
}

byId("species").addEventListener("change", updateSpecies);
byId("species-search").addEventListener("input", event => {
  if (options && !event.isComposing) filterSpecies();
});
byId("species-search").addEventListener("compositionend", () => {
  if (options) filterSpecies();
});
byId("item").addEventListener("change", () => {
  byId("scarf-field").hidden = byId("item").value !== "scarf";
});
byId("max").addEventListener("click", () => {
  for (const input of conditionInputs) input.value = 255;
});
byId("progress").addEventListener("change", () => {
  const stage = byId("progress").value;
  if (stage === "wallace" || stage === "rematch") byId("hall").checked = true;
});

function percentage(value) {
  if (value === null) return "—";
  if (value > 0 && value < 0.01) return "<0.01%";
  return `${value.toLocaleString("ja-JP", {maximumFractionDigits: 2})}%`;
}

function render(data) {
  const rows = document.createDocumentFragment();
  for (const division of data.divisions) {
    const row = document.createElement("tr");
    const values = [
      categories.get(division.category), ranks.get(division.rank),
      ...[1, 2, 3, 4].map(rank => percentage(division.player_rank_pct[rank])),
      percentage(division.scenario_npc_appearance_exact_pct.Lisia ?? 0),
      percentage(division.player_first_lisia_fourth_pct),
      percentage(division.player_first_lisia_fourth_given_appearance_pct),
    ];
    for (const [index, value] of values.entries()) {
      const cell = document.createElement(index === 0 ? "th" : "td");
      if (index === 0) cell.scope = "row";
      cell.textContent = value;
      row.append(cell);
    }
    rows.append(row);
  }
  byId("rows").replaceChildren(rows);
  byId("results").hidden = false;
  byId("results-title").focus();
}

byId("settings").addEventListener("submit", async event => {
  event.preventDefault();
  const species = selectedSpecies();
  if (!species || busy) return;
  const turns = turnInputs.map(input => input.value);
  const known = species.id === "rayquaza" && byId("dragon").checked ? ["dragon-ascent"] : [];
  if (turns.every(move => move === "-") || new Set([...turns.filter(move => move !== "-"), ...known]).size > 4) {
    byId("status").textContent = "使う技を選び、覚えている技を4種類以内にしてください。";
    return;
  }
  busy = true;
  byId("run").disabled = true;
  byId("results").hidden = true;
  byId("status").textContent = "計算中…";
  try {
    const response = await fetch("/api/simulate", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Contest-Token": options.token},
      body: JSON.stringify({
        species: species.id, conditions: conditionInputs.map(input => input.valueAsNumber),
        turns, known, category: byId("category").value, rank: byId("rank").value,
        item: byId("item").value, scarf: byId("scarf").value, progress: byId("progress").value,
        hallOfFame: byId("hall").checked, trials: Number(byId("trials").value),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    result = data;
    byId("status").textContent = "";
    render(data);
  } catch (error) {
    byId("status").textContent = error.message || "計算できませんでした。";
  } finally {
    busy = false;
    byId("run").disabled = !selectedSpecies();
  }
});

byId("download").addEventListener("click", () => {
  if (!result) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type: "application/json"}));
  const link = Object.assign(document.createElement("a"), {href: url, download: "contest-results.json"});
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

async function initialize() {
  updateSpecies();
  try {
    const response = await fetch("/api/options");
    if (!response.ok) throw new Error();
    options = await response.json();
    filterSpecies();
  } catch {
    byId("status").textContent = "ポケモン一覧を読み込めませんでした。";
  }
}
initialize();
