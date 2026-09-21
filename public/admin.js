const status = document.querySelector('#status');
const leads = document.querySelector('#leads');

function element(tag, text, className = '') {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = className;
  return node;
}

async function load() {
  status.textContent = 'Loading…';
  try {
    const response = await fetch('/api/admin/leads', { cache: 'no-store' });
    if (!response.ok) throw new Error(`Could not load requests (HTTP ${response.status}).`);
    const data = await response.json();
    leads.replaceChildren();
    for (const lead of data) {
      const card = element('article', '', 'admin-lead');
      card.append(element('h2', lead.name), element('p', lead.email), element('p', lead.url),
        element('p', new Date(lead.created * 1000).toLocaleString() + ' · ' + lead.language.toUpperCase() + ' · ' + lead.status),
        element('p', lead.message, 'lead-message'));
      if (lead.audit_id) {
        const report = element('a', 'Open technical report (JSON)');
        report.href = '/api/audits/' + lead.audit_id;
        card.append(report);
      }
      const actions = element('div', '', 'admin-actions');
      for (const [action, label] of [['done', 'Mark handled'], ['delete', 'Delete']]) {
        if (action === 'done' && lead.status === 'done') continue;
        const button = element('button', label, 'button');
        button.addEventListener('click', async () => {
          if (action === 'delete' && !confirm('Permanently delete this request?')) return;
          button.disabled = true;
          try {
            const result = await fetch('/api/admin/leads/' + lead.id, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action }) });
            if (!result.ok) throw new Error('The request could not be updated.');
            await load();
          } catch (error) { status.textContent = error.message; button.disabled = false; }
        });
        actions.append(button);
      }
      card.append(actions);
      leads.append(card);
    }
    status.textContent = `${data.length} request${data.length === 1 ? '' : 's'}`;
  } catch (error) { status.textContent = error.message; }
}
document.querySelector('#refresh').addEventListener('click', load);
load();
