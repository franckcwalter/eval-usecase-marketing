const form = document.getElementById('scoreForm');
const result = document.getElementById('result');
const numericFields = ['previous', 'emp.var.rate', 'cons.price.idx', 'cons.conf.idx'];
const percent = (rate) => `${(rate * 100).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`;

// Lignes réelles du jeu de données : 10 souscripteurs et 20 non-souscripteurs.
const referenceColumns = ['cons.conf.idx', 'cons.price.idx', 'emp.var.rate', 'previous', 'contact', 'default', 'housing', 'loan', 'poutcome'];
const referenceRows = [
  [-47.1, 93.075, -1.8, 0, 'cellular', 'no', 'no', 'no', 'nonexistent'],
  [-42.0, 93.2, -0.1, 0, 'cellular', 'no', 'no', 'no', 'nonexistent'],
  [-36.4, 93.994, 1.1, 0, 'telephone', 'unknown', 'no', 'yes', 'nonexistent'],
  [-46.2, 92.893, -1.8, 0, 'cellular', 'no', 'no', 'no', 'nonexistent'],
  [-41.8, 94.465, 1.4, 0, 'telephone', 'unknown', 'no', 'no', 'nonexistent'],
  [-36.4, 93.994, 1.1, 0, 'telephone', 'no', 'yes', 'no', 'nonexistent'],
  [-46.2, 92.893, -1.8, 1, 'cellular', 'no', 'no', 'no', 'success'],
  [-26.9, 92.431, -3.4, 0, 'telephone', 'no', 'yes', 'no', 'nonexistent'],
  [-33.0, 92.713, -3.0, 0, 'cellular', 'no', 'yes', 'no', 'nonexistent'],
  [-47.1, 93.075, -1.8, 0, 'cellular', 'no', 'yes', 'no', 'nonexistent'],
  [-31.4, 92.201, -2.9, 1, 'cellular', 'no', 'yes', 'no', 'success'],
  [-38.3, 94.027, -1.7, 1, 'cellular', 'no', 'yes', 'no', 'failure'],
  [-36.4, 93.994, 1.1, 0, 'telephone', 'no', 'yes', 'no', 'nonexistent'],
  [-36.4, 93.994, 1.1, 0, 'telephone', 'unknown', 'yes', 'no', 'nonexistent'],
  [-36.1, 93.444, 1.4, 0, 'cellular', 'no', 'no', 'no', 'nonexistent'],
  [-42.7, 93.918, 1.4, 0, 'cellular', 'no', 'no', 'no', 'nonexistent'],
  [-30.1, 92.649, -3.4, 0, 'telephone', 'no', 'no', 'no', 'nonexistent'],
  [-42.7, 93.918, 1.4, 0, 'cellular', 'no', 'yes', 'no', 'nonexistent'],
  [-46.2, 92.893, -1.8, 1, 'cellular', 'unknown', 'no', 'no', 'failure'],
  [-33.6, 92.469, -2.9, 0, 'telephone', 'no', 'yes', 'no', 'nonexistent'],
  [-47.1, 93.075, -1.8, 0, 'cellular', 'no', 'yes', 'no', 'nonexistent'],
  [-42.0, 93.2, -0.1, 1, 'cellular', 'unknown', 'yes', 'no', 'failure'],
  [-36.4, 93.994, 1.1, 0, 'telephone', 'unknown', 'no', 'no', 'nonexistent'],
  [-36.4, 93.994, 1.1, 0, 'telephone', 'no', 'yes', 'no', 'nonexistent'],
  [-46.2, 92.893, -1.8, 1, 'cellular', 'no', 'yes', 'no', 'failure'],
  [-36.4, 93.994, 1.1, 0, 'telephone', 'no', 'no', 'no', 'nonexistent'],
  [-40.3, 94.215, -1.7, 0, 'cellular', 'unknown', 'yes', 'no', 'nonexistent'],
  [-41.8, 94.465, 1.4, 0, 'telephone', 'no', 'no', 'no', 'nonexistent'],
  [-42.7, 93.918, 1.4, 0, 'telephone', 'no', 'yes', 'no', 'nonexistent'],
  [-42.7, 93.918, 1.4, 0, 'cellular', 'no', 'no', 'no', 'nonexistent'],
];

// Regroupe chaque libellé et son champ pour la grille.
form.querySelectorAll(':scope > label').forEach((label) => {
  const field = label.nextElementSibling;
  const wrapper = document.createElement('div');
  wrapper.className = 'field';
  form.insertBefore(wrapper, label);
  wrapper.append(label, field);
});

const errorMessage = async (res) => {
  const body = await res.json().catch(() => ({}));
  const detail = body.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.colonnes_manquantes) return `Colonnes manquantes : ${detail.colonnes_manquantes.join(', ')}`;
  if (detail?.erreurs) {
    const first = detail.erreurs[0];
    return `${detail.nb_erreurs} valeur(s) invalide(s). Première erreur : ligne ${first.ligne}, colonne ${first.colonne} — ${first.message}`;
  }
  if (Array.isArray(detail)) return detail.map((e) => `${e.loc.at(-1)} : ${e.msg}`).join(' ; ');
  return `Erreur ${res.status}`;
};

document.getElementById('randomClient').addEventListener('click', () => {
  const row = referenceRows[Math.floor(Math.random() * referenceRows.length)];
  referenceColumns.forEach((column, index) => { form.elements[column].value = row[index]; });
  result.style.display = 'none';
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const payload = Object.fromEntries(
    [...new FormData(form)].map(([key, value]) => [key, numericFields.includes(key) ? Number(value) : value]),
  );
  result.className = 'result-card';
  result.style.display = 'block';
  result.textContent = 'Calcul en cours…';
  try {
    const res = await fetch('/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await errorMessage(res));
    const data = await res.json();
    document.getElementById('feedbackClient').value = payload.client_id;
    document.getElementById('feedbackCampaign').value = payload.campaign_id;
    document.getElementById('monitorCampaign').value = payload.campaign_id;
    const debutTranche = parseInt(data.tranche, 10);
    result.classList.add(debutTranche < 30 ? 'ok' : debutTranche < 50 ? 'warn' : 'ko');
    result.innerHTML = `
      <span class="result-label">Place dans le classement</span>
      <strong>Tranche ${data.tranche}</strong>
      <span class="result-hint">La tranche 0-10 % regroupe les clients les plus susceptibles de souscrire.</span>
      <span class="probability">${percent(data.taux_reel_tranche)}</span>
      <span class="probability-label">des clients de cette tranche ont souscrit</span>
      <span class="result-meta">Score du modèle : ${data.score.toLocaleString('fr-FR')}<br>Modèle ${data.model_version}<br>Requête <code>${data.request_id}</code></span>
    `;
  } catch (err) {
    result.classList.add('ko');
    result.textContent = `Erreur : ${err.message}`;
  }
});

// Fichier de clients : envoi à /rank, filtre par tranche, aperçu et téléchargement.
const dropZone = document.getElementById('dropZone');
const csvFile = document.getElementById('csvFile');
const rankStatus = document.getElementById('rankStatus');
const rankResult = document.getElementById('rankResult');
const tranchesKept = document.getElementById('tranchesKept');
const preview = document.getElementById('preview');
const PREVIEW_ROWS = 20;
const FIRST_COLUMNS = ['rang', 'tranche', 'taux_reel_tranche', 'score'];
let ranked = null;

const splitCsvLine = (line, sep) => {
  const cells = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"' && quoted && line[i + 1] === '"') { cell += '"'; i += 1; }
    else if (char === '"') quoted = !quoted;
    else if (char === sep && !quoted) { cells.push(cell); cell = ''; }
    else cell += char;
  }
  cells.push(cell);
  return cells;
};

const parseRanked = (text) => {
  const lines = text.split(/\r?\n/).filter(Boolean);
  const sep = lines[0].includes(';') ? ';' : ',';
  const header = splitCsvLine(lines[0], sep);
  const rows = lines.slice(1).map((line) => splitCsvLine(line, sep));
  return { lines, sep, header, rows, col: (name) => header.indexOf(name) };
};

const keptRows = () => {
  const limit = Number(tranchesKept.value) * 10;
  const trancheCol = ranked.col('tranche');
  return ranked.rows.filter((row) => parseInt(row[trancheCol], 10) < limit);
};

const meanRate = (rows) => rows.reduce((sum, row) => sum + Number(row[ranked.col('taux_reel_tranche')]), 0) / rows.length;

const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

const renderRanked = () => {
  const rows = keptRows();
  document.getElementById('keptPercent').textContent = Number(tranchesKept.value) * 10;
  document.getElementById('statKept').textContent = `${rows.length.toLocaleString('fr-FR')} / ${ranked.rows.length.toLocaleString('fr-FR')}`;
  document.getElementById('statRate').textContent = percent(meanRate(rows));
  document.getElementById('statAll').textContent = percent(meanRate(ranked.rows));

  const columns = [...FIRST_COLUMNS, ...ranked.header.filter((name) => !FIRST_COLUMNS.includes(name))];
  const indexes = columns.map(ranked.col);
  preview.innerHTML = `
    <thead><tr>${columns.map((name) => `<th>${escapeHtml(name)}</th>`).join('')}</tr></thead>
    <tbody>${rows.slice(0, PREVIEW_ROWS).map((row) => `<tr>${indexes.map((i) => `<td>${escapeHtml(row[i])}</td>`).join('')}</tr>`).join('')}</tbody>
  `;
};

const driftDialog = document.getElementById('driftDialog');
let lastFile = null;
const DRIFT_VERDICTS = {
  stable: 'Faible',
  watch: 'Modéré',
  investigate: 'Fort',
  insufficient_counts: 'Pas assez de clients',
  no_data: 'Aucune donnée',
};
const formatNumber = (value, digits) => value.toLocaleString('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits });

const renderDrift = (drift) => {
  const flagged = drift.variables.filter((row) => row.status === 'investigate').length;
  document.getElementById('driftSummary').textContent = `${drift.n_clients.toLocaleString('fr-FR')} clients comparés aux ${drift.n_reference.toLocaleString('fr-FR')} clients du test historique : `
    + (flagged ? `${flagged} variable(s) avec un écart fort.` : 'aucun écart fort.');
  document.getElementById('driftTable').innerHTML = `
    <thead><tr><th>Variable</th><th>Écart</th><th>Mesure</th></tr></thead>
    <tbody>${drift.variables.map((row) => {
      const measure = row.psi != null ? `PSI ${formatNumber(row.psi, 2)}`
        : row.chi2_pvalue != null ? `Chi², p = ${formatNumber(row.chi2_pvalue, 3)}` : '—';
      return `<tr><td>${escapeHtml(row.feature)}</td><td><span class="drift-badge drift-${row.status}">${DRIFT_VERDICTS[row.status]}</span></td><td>${measure}</td></tr>`;
    }).join('')}</tbody>
  `;
};

const showLoading = (element, text) => {
  element.className = 'rank-status loading';
  element.textContent = text;
};

document.getElementById('openDrift').addEventListener('click', async (e) => {
  const button = e.currentTarget;
  button.disabled = true;
  showLoading(rankStatus, 'Comparaison avec l’historique en cours…');
  const body = new FormData();
  body.append('file', lastFile);
  try {
    const res = await fetch('/drift', { method: 'POST', body });
    if (!res.ok) throw new Error(await errorMessage(res));
    renderDrift(await res.json());
    rankStatus.className = 'rank-status';
    rankStatus.textContent = `« ${lastFile.name} » : ${ranked.rows.length.toLocaleString('fr-FR')} clients classés.`;
    driftDialog.showModal();
  } catch (err) {
    rankStatus.className = 'rank-status error';
    rankStatus.textContent = `Erreur : ${err.message}`;
  } finally {
    button.disabled = false;
  }
});

const sendFile = async (file) => {
  rankResult.hidden = true;
  lastFile = file;
  showLoading(rankStatus, `Classement de « ${file.name} » en cours…`);
  dropZone.classList.add('busy');
  const body = new FormData();
  body.append('file', file);
  try {
    const res = await fetch('/rank', { method: 'POST', body });
    if (!res.ok) throw new Error(await errorMessage(res));
    ranked = parseRanked(await res.text());
    rankStatus.className = 'rank-status';
    rankStatus.textContent = `« ${file.name} » : ${ranked.rows.length.toLocaleString('fr-FR')} clients classés.`;
    renderRanked();
    rankResult.hidden = false;
  } catch (err) {
    rankStatus.className = 'rank-status error';
    rankStatus.textContent = `Erreur : ${err.message}`;
  } finally {
    dropZone.classList.remove('busy');
    csvFile.value = '';
  }
};

csvFile.addEventListener('change', () => { if (csvFile.files[0]) sendFile(csvFile.files[0]); });
['dragenter', 'dragover'].forEach((type) => dropZone.addEventListener(type, (e) => {
  e.preventDefault();
  dropZone.classList.add('dragging');
}));
['dragleave', 'drop'].forEach((type) => dropZone.addEventListener(type, () => dropZone.classList.remove('dragging')));
dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  if (e.dataTransfer.files[0]) sendFile(e.dataTransfer.files[0]);
});
tranchesKept.addEventListener('input', renderRanked);

document.getElementById('download').addEventListener('click', () => {
  const limit = Number(tranchesKept.value) * 10;
  const trancheCol = ranked.col('tranche');
  const kept = ranked.lines.filter((line, i) => i === 0 || parseInt(splitCsvLine(line, ranked.sep)[trancheCol], 10) < limit);
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([kept.join('\n') + '\n'], { type: 'text/csv' }));
  link.download = `clients_top_${limit}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
});


const feedbackForm = document.getElementById('feedbackForm');
const feedbackStatus = document.getElementById('feedbackStatus');
feedbackForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const payload = Object.fromEntries(new FormData(feedbackForm));
  payload.true_label = Number(payload.true_label);
  const button = feedbackForm.querySelector('button[type="submit"]');
  button.disabled = true;
  feedbackStatus.className = 'rank-status';
  feedbackStatus.textContent = 'Enregistrement en cours…';
  try {
    const res = await fetch('/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await errorMessage(res));
    const data = await res.json();
    feedbackStatus.textContent = data.status === 'already_stored'
      ? 'Ce résultat est déjà enregistré.' : 'Résultat enregistré.';
  } catch (err) {
    feedbackStatus.classList.add('error');
    feedbackStatus.textContent = `Erreur : ${err.message}`;
  } finally {
    button.disabled = false;
  }
});


const campaignStatus = document.getElementById('campaignStatus');
const campaignDialog = document.getElementById('campaignDialog');
const TRIGGERS = { volume: 'assez de nouveaux résultats', degradation: 'campagne sous l’objectif' };
const renderRetraining = (data) => {
  const progress = `${data.unused_results.toLocaleString('fr-FR')} nouveaux résultats sur ${data.retrain_threshold.toLocaleString('fr-FR')} nécessaires`;
  const run = data.retraining;
  if (!run) return `<p>Aucun réentraînement : ${progress}, et objectif atteint.</p>`;
  const reasons = run.trigger.split('+').map((name) => TRIGGERS[name]).join(' et ');
  const row = (label, key, format) => `<tr><td>${label}</td><td>${format(run.served[key])}</td><td>${format(run.candidate[key])}</td></tr>`;
  const auc = (value) => formatNumber(value, 3);
  return `
    <p>Réentraînement lancé (${reasons}) : ${run.n_history.toLocaleString('fr-FR')} clients historiques
      et ${run.n_new_results.toLocaleString('fr-FR')} nouveaux résultats.</p>
    <table>
      <thead><tr><th>Sur le jeu de test</th><th>Modèle actuel</th><th>Nouveau modèle</th></tr></thead>
      <tbody>${row('Rappel à 50 %', 'rappel_top50', percent)}${row('ROC AUC', 'roc_auc', auc)}</tbody>
    </table>
    <p class="${run.accepted ? 'above' : 'below'}">${run.accepted ? 'Garde-fous respectés' : 'Garde-fous non respectés'} : ${run.reasons.map(escapeHtml).join(' ; ')}.</p>
    <p class="table-note">Le nouveau modèle est enregistré à part (${escapeHtml(run.run_id)}). Sa mise en production reste une décision humaine.</p>`;
};

const campaignAction = async () => {
  const campaign = document.getElementById('monitorCampaign').value.trim();
  if (!campaign) {
    campaignStatus.textContent = 'Renseigner l’identifiant de la campagne.';
    return;
  }
  const button = document.getElementById('closeCampaign');
  button.disabled = true;
  showLoading(campaignStatus, 'Calcul du bilan et réentraînement éventuel en cours…');
  try {
    const res = await fetch(`/campaigns/${encodeURIComponent(campaign)}/close`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error(await errorMessage(res));
    const data = await res.json();
    campaignStatus.className = 'rank-status';
    if (data.subscription_rate === null) {
      campaignStatus.textContent = 'Campagne terminée. Aucun résultat connu dans le top 50 % d’un fichier classé : le taux ne peut pas être calculé.';
      return;
    }
    campaignStatus.textContent = 'Campagne terminée.';
    document.getElementById('campaignTitle').textContent = `Bilan de la campagne ${campaign}`;
    document.getElementById('campaignSummary').innerHTML = `<strong>${percent(data.subscription_rate)}</strong> de souscription,
      soit ${data.subscriptions} sur ${data.selected_known} résultats connus parmi les ${data.selected_expected} clients du top 50 %.`;
    const verdict = document.getElementById('campaignVerdict');
    verdict.className = data.below_threshold ? 'below' : 'above';
    verdict.textContent = data.below_threshold
      ? `Sous l’objectif de ${percent(data.threshold)}.`
      : `Objectif de ${percent(data.threshold)} atteint.`;
    document.getElementById('campaignTranches').innerHTML = `
      <thead><tr><th>Tranche</th><th>Résultats connus</th><th>Taux annoncé</th><th>Taux observé</th><th>Écart</th></tr></thead>
      <tbody>${data.tranches.map((row) => `<tr>
        <td>${escapeHtml(row.tranche)}</td><td>${row.n}</td><td>${percent(row.displayed_rate)}</td>
        <td>${percent(row.observed_rate)}</td><td>${row.gap > 0 ? '+' : ''}${formatNumber(row.gap * 100, 1)} pts</td>
      </tr>`).join('')}</tbody>`;
    document.getElementById('campaignRetraining').innerHTML = renderRetraining(data);
    campaignDialog.showModal();
  } catch (err) {
    campaignStatus.className = 'rank-status error';
    campaignStatus.textContent = err.message;
  } finally {
    button.disabled = false;
  }
};
document.getElementById('closeCampaign').addEventListener('click', campaignAction);
