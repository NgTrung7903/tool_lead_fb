'use strict';
const labels = {LEAD_POTENTIAL: 'Khách tiềm năng', NEEDS_REVIEW: 'Cần xem lại', IGNORE: 'Bỏ qua'};
const runLabels = {running: 'Đang lấy bình luận...', partial: 'Đã lấy xong', completed: 'Đã lấy xong', stopped: 'Đã dừng', action_required: 'Cần đăng nhập/xác minh', failed: 'Bị lỗi', interrupted: 'Bị gián đoạn', imported: 'Dữ liệu nhập tay'};
const PAGE_SIZE = 50;
const CUSTOMER_PREVIEW_HEIGHT = 240;
const FACEBOOK_GROUP_PREFIX = 'https://www.facebook.com/groups/';
const expandedCustomerSections = new Set();
const interestLabels = {strong: 'Mạnh', moderate: 'Vừa', weak: 'Yếu', unclear: 'Chưa rõ', none: 'Chưa thấy nhu cầu'};
const contactLabels = {phone: 'Có SĐT', zalo: 'Có Zalo', email: 'Có email', profile: 'Có link hồ sơ', comment: 'Có link comment'};
let current = {records: []}, mode = 'all', poll = null, pageIndex = 0, hubData = null, activeRunId = null, refreshVersion = 0;
const requested = new URLSearchParams(location.search);
let postingTaskFilter = requested.get('posting_task_id') || '';

function customerPreview(parent, customer, section, label) {
  const key = JSON.stringify([customer.fb_user_url || [customer.source_url, customer.id], section]);
  const content = node('div', undefined, parent, 'customer-preview');
  const toggle = node('button', undefined, parent, 'link small customer-preview-toggle');
  toggle.type = 'button';
  toggle.hidden = true;
  const apply = () => {
    const expanded = expandedCustomerSections.has(key);
    content.classList.toggle('is-collapsed', !expanded);
    content.classList.toggle('has-overflow', content.scrollHeight > CUSTOMER_PREVIEW_HEIGHT);
    toggle.textContent = expanded ? 'Thu gọn' : `Xem đầy đủ ${label}`;
    toggle.setAttribute('aria-expanded', String(expanded));
  };
  toggle.onclick = () => {
    if (expandedCustomerSections.has(key)) expandedCustomerSections.delete(key);
    else expandedCustomerSections.add(key);
    apply();
  };
  apply();
  requestAnimationFrame(() => {
    if (!content.isConnected) return;
    toggle.hidden = content.scrollHeight <= CUSTOMER_PREVIEW_HEIGHT;
    apply();
  });
  return content;
}

function groupKey(row) {
  if (row.group_key) return row.group_key;
  try { const match = new URL(row.source_url).pathname.match(/^\/groups\/([^/]+)/); if (match) return FACEBOOK_GROUP_PREFIX + match[1]; } catch {}
  return row.group_name || '__external__';
}
function fillOptions(select, rows, empty, key, title) {
  const chosen = select.value;
  select.replaceChildren(); node('option', empty, select).value = '';
  for (const row of rows) node('option', row[title], select).value = row[key];
  if (chosen && !rows.some(r => r[key] === chosen)) node('option', chosen, select).value = chosen;
  select.value = chosen;
}
function queryParams() {
  const q = new URLSearchParams();
  for (const [name, id] of [['campaign_id', 'campaign-filter'], ['group_key', 'group-filter'], ['classification', 'classification'], ['interest_level', 'interest-filter'], ['q', 'search']]) {
    const value = $(id).value.trim(); if (value) q.set(name, value);
  }
  if (postingTaskFilter) q.set('posting_task_id', postingTaskFilter);
  return q;
}
function scopedRecords(withClassification = true) {
  const campaign = $('campaign-filter').value, group = $('group-filter').value;
  const query = $('search').value.trim().toLocaleLowerCase('vi');
  const cls = withClassification ? $('classification').value : '';
  const level = $('interest-filter').value;
  return (current?.records || []).filter(r => (r.sources || [r]).some(source =>
    (!campaign || (source.campaign_id || '__external__') === campaign) && (!group || groupKey(source) === group) &&
    (!postingTaskFilter || source.posting_task_id === postingTaskFilter)) &&
    (!cls || r.classification === cls) && (!level || r.interest_level === level) && (!query || [r.fb_user_name, r.raw_content, r.contacts?.primary_phone,
      r.contacts?.zalo, r.contacts?.emails?.join(' ')].filter(Boolean).join(' ').toLocaleLowerCase('vi').includes(query)));
}
function resetScope() {
  for (const id of ['campaign-filter', 'group-filter', 'classification', 'interest-filter', 'search']) $(id).value = '';
  postingTaskFilter = ''; pageIndex = 0;
}
function render() {
  const scope = scopedRecords(false), records = scopedRecords();
  for (const [id, key] of [['total', null], ['potential', 'LEAD_POTENTIAL'], ['review', 'NEEDS_REVIEW'], ['ignored', 'IGNORE']]) {
    $(id).textContent = key ? scope.filter(r => r.classification === key).length : scope.length;
  }
  for (const b of document.querySelectorAll('.stats button')) b.classList.toggle('selected', b.dataset.filter === $('classification').value);
  const pages = Math.max(1, Math.ceil(records.length / PAGE_SIZE)); pageIndex = Math.min(pageIndex, pages - 1);
  $('results').replaceChildren();
  for (const r of records.slice(pageIndex * PAGE_SIZE, pageIndex * PAGE_SIZE + PAGE_SIZE)) {
    const tr = node('tr', undefined, $('results'));
    const author = node('td', undefined, tr);
    node('strong', r.fb_user_name || 'Chưa xác định tác giả', author);
    if (r.identity_status === 'anonymous') node('p', 'Ẩn danh', author, 'hint');
    else if (r.identity_status === 'unknown') node('p', 'Chưa xác định tác giả', author, 'hint');
    const contact = node('td', undefined, tr), c = r.contacts || {};
    node('p', [c.primary_phone, c.zalo && 'Zalo: ' + c.zalo, c.emails?.join(', ')].filter(Boolean).join(' · ') || 'Chưa có liên hệ', contact, 'contact');
    node('p', (r.contact_channels || []).map(key => contactLabels[key]).filter(Boolean).join(' · ') || 'Chưa có kênh liên hệ', contact, 'hint');
    if (r.contact_channels?.includes('profile') && r.fb_user_url) safeLink(contact, 'Mở hồ sơ ↗', r.fb_user_url);
    if (c.primary_phone && navigator.clipboard) {
      const copy = node('button', 'Chép SĐT', contact, 'link small');
      copy.onclick = async () => { await navigator.clipboard.writeText(c.primary_phone); copy.textContent = 'Đã chép ✓'; };
    }
    const body = node('td', undefined, tr, 'customer-discussion');
    body.colSpan = 2;
    node('strong', `${r.comment_count || 1} bình luận`, body, 'customer-comment-total');
    const commentPreview = customerPreview(body, r, 'comments', 'bình luận');
    const commentGroups = new Map();
    for (const comment of r.comments || [r]) {
      const group = groupKey(comment);
      const key = group === '__external__' ? comment.source_url || group : group;
      if (!commentGroups.has(key)) commentGroups.set(key, []);
      commentGroups.get(key).push(comment);
    }
    for (const comments of commentGroups.values()) {
      const section = node('div', undefined, commentPreview, 'customer-comment-group');
      const group = node('div', undefined, section);
      const name = comments.find(comment => comment.group_name)?.group_name;
      const key = groupKey(comments[0]);
      const fallbackName = key.startsWith(FACEBOOK_GROUP_PREFIX) ? key.slice(FACEBOOK_GROUP_PREFIX.length) : 'Bài ngoài nhóm';
      node('strong', name || fallbackName, group);
      node('p', `${comments.length} bình luận`, group, 'hint');
      const items = node('div', undefined, section);
      for (const comment of comments) {
        const item = node('div', undefined, items, 'customer-comment');
        if (comment.source_url) safeLink(item, 'Mở bài viết ↗', comment.source_url);
        node('p', comment.raw_content || comment.intent_summary || '', item);
        if (comment.comment_url) { try { const u = new URL(comment.comment_url); if (u.protocol === 'https:' && ['www.facebook.com', 'facebook.com', 'm.facebook.com'].includes(u.hostname)) safeLink(item, 'Mở bình luận ↗', u.href); } catch {} }
      }
    }
    const source = node('td', undefined, tr);
    node('strong', `${r.group_count || 1} nhóm · ${(r.sources || [r]).length} bài`, source);
    const sourcePreview = customerPreview(source, r, 'sources', 'đợt đăng / bài');
    for (const entry of r.sources || [r]) {
      const item = node('div', undefined, sourcePreview, 'customer-comment');
      node('p', entry.campaign_title || entry.campaign_id || 'Bài ngoài đợt đăng', item, 'hint');
      if (entry.source_url) safeLink(item, 'Mở bài viết ↗', entry.source_url);
    }
    if (r.last_collected_at) node('p', 'Lấy gần nhất: ' + formatTime(r.last_collected_at), source, 'hint');
    const category = node('td', undefined, tr);
    node('span', labels[r.classification] || r.classification, category, 'badge ' + r.classification);
    node('p', 'Mức quan tâm: ' + (interestLabels[r.interest_level] || 'Chưa rõ'), category, 'hint');
    const reasons = node('td', undefined, tr), details = node('details', undefined, reasons);
    node('summary', 'Điểm ' + r.score + ' · Xem lý do', details);
    node('p', (r.reasons || []).join('\n'), details); signalChips(r.signals, details);
    if (r.interest_evidence?.length) node('p', 'Cụm từ đánh giá mức độ: ' + r.interest_evidence.join(', '), details, 'hint');
  }
  if (!records.length) { const td = node('td', current.records.length ? 'Không có kết quả khớp bộ lọc.' : 'Chưa có kết quả. Chọn đợt đăng hoặc nhập link bài viết để lấy và lọc comment tại tab này.', node('tr', undefined, $('results'))); td.colSpan = 7; }
  $('result-count').textContent = `Hiển thị ${records.length} / ${current.records.length} khách hàng · Trang ${pageIndex + 1} / ${pages}`;
  $('page-number').textContent = `Trang ${pageIndex + 1} / ${pages}`;
  $('previous').disabled = pageIndex === 0; $('next').disabled = pageIndex >= pages - 1;
  $('export').disabled = !records.length;
  $('back-to-results').hidden = mode === 'all'; $('article-scope').hidden = !postingTaskFilter;
  const latest = scope.map(r => r.last_collected_at).filter(Boolean).sort().at(-1) || (mode === 'history' ? current.finished_at || current.created_at : null);
  $('latest-collection').textContent = latest ? 'Lần lấy gần nhất trong phạm vi đang xem: ' + formatTime(latest) : '';
  $('run-status').textContent = mode === 'all'
    ? `Kết quả tổng hợp mới nhất${$('group-filter').value ? ' · ' + $('group-filter').selectedOptions[0].textContent : ''}. ${hubData?.active_runs.length ? 'Có tác vụ đang lấy comment; kết quả sẽ tự cập nhật.' : ''}`
    : `${mode === 'history' ? 'Lịch sử: ' : ''}${current.context?.group_name || ''} — ${runLabels[current.status] || current.status || ''} ${current.message || ''}`;
  $('collection-targets').replaceChildren();
  if (mode === 'history') for (const t of current.targets || []) node('p', `${t.context?.group_name || t.post_url}: ${runLabels[t.status] || t.status} — ${t.message || ''}`, $('collection-targets'), 'hint');
  $('collect').disabled = !!activeRunId; $('stop').disabled = !activeRunId;
  updateCollectionButtons();
}
function renderHistory(rows) {
  const selected = mode === 'history' ? current.id : '';
  $('history').replaceChildren(); node('option', '— Chọn lần lấy —', $('history')).value = '';
  for (const r of rows) node('option', `${formatTime(r.created_at)} · ${r.context?.group_name || r.post_url || 'Nhiều bài'} · ${r.summary.total} comment · ${runLabels[r.status] || r.status}`, $('history')).value = r.id;
  $('history').value = selected || '';
}
async function loadHub() {
  clearTimeout(poll); const version = ++refreshVersion;
  const [result, runs] = await Promise.all([api('/api/leads/results'), api('/api/leads/runs')]);
  if (mode !== 'all' || version !== refreshVersion) return;
  hubData = result; current = result; activeRunId = result.active_runs[0]?.id || null;
  fillOptions($('campaign-filter'), result.campaigns.map(c => ({...c, title: c.created_at ? c.title + ' · ' + formatTime(c.created_at) : c.title})), 'Tất cả đợt đăng', 'id', 'title');
  fillOptions($('group-filter'), result.groups, 'Tất cả nhóm', 'key', 'name');
  renderHistory(runs); render();
  poll = setTimeout(() => loadHub().catch(showRefreshError), activeRunId ? 1500 : 10000);
}
function showRefreshError(error) {
  notice(error.message, 'error'); if (mode === 'all') poll = setTimeout(() => loadHub().catch(showRefreshError), 4000);
}
async function watchSnapshot(id) {
  clearTimeout(poll); const version = ++refreshVersion;
  const run = await api('/api/leads/runs/' + encodeURIComponent(id));
  if (mode !== 'history' || version !== refreshVersion) return;
  current = run; activeRunId = run.status === 'running' ? run.id : null;
  const campaigns = new Map(), groups = new Map();
  for (const r of run.records.flatMap(row => row.sources || [row])) {
    if (r.campaign_id) campaigns.set(r.campaign_id, r.campaign_title || r.campaign_id);
    groups.set(groupKey(r), r.group_name || (groupKey(r) === '__external__' ? 'Bài ngoài nhóm' : groupKey(r)));
  }
  fillOptions($('campaign-filter'), [...campaigns].map(([id, title]) => ({id, title})), 'Tất cả đợt đăng', 'id', 'title');
  fillOptions($('group-filter'), [...groups].map(([key, name]) => ({key, name})), 'Tất cả nhóm', 'key', 'name');
  render();
  if (activeRunId) poll = setTimeout(() => watchSnapshot(id).catch(e => notice(e, 'error')), 1500);
  else renderHistory(await api('/api/leads/runs'));
}
async function openSnapshot(id) {
  mode = 'history'; resetScope(); $('history-box').open = true;
  await watchSnapshot(id);
}
let publicationCampaigns = [];
function selectedCollectionCampaign() {
  return publicationCampaigns.find(c => c.id === $('collection-campaign').value);
}
function eligiblePublications(campaign) {
  if (!campaign || campaign.source_mode !== 'live') return [];
  return campaign.tasks.filter(task => task.status === 'posted' && task.post_url && task.evidence);
}
function updateCollectionButtons() {
  const selected = selectedCollectionCampaign();
  $('collect-selected').disabled = !!activeRunId || !eligiblePublications(selected).length || ['running', 'queued'].includes(selected?.status);
  $('collection-stop').disabled = !activeRunId;
  $('collection-status').textContent = activeRunId ? 'Đang lấy comment. Kết quả sẽ tự cập nhật bên dưới.' :
    selected ? `${eligiblePublications(selected).length} bài đã xác nhận đăng có thể lấy comment.` : 'Chọn đợt đăng và bài muốn lọc.';
}
function fillPublicationTasks() {
  const selected = selectedCollectionCampaign();
  if (!eligiblePublications(selected).some(t => t.task_id === $('collection-task').value)) $('collection-task').value = '';
  fillOptions($('collection-task'), eligiblePublications(selected), 'Tất cả bài đã đăng trong đợt', 'task_id', 'group_name');
  updateCollectionButtons();
}
async function loadPublications() {
  publicationCampaigns = await api('/api/campaigns');
  const chosen = $('collection-campaign').value || requested.get('campaign_id');
  fillOptions($('collection-campaign'), publicationCampaigns.map(c => ({...c, title: `${c.listing_title} · ${formatTime(c.created_at)}`})), '— Chọn đợt đăng —', 'id', 'title');
  if (publicationCampaigns.some(c => c.id === chosen)) $('collection-campaign').value = chosen;
  fillPublicationTasks();
  const requestedTask = requested.get('posting_task_id');
  if (eligiblePublications(selectedCollectionCampaign()).some(t => t.task_id === requestedTask)) $('collection-task').value = requestedTask;
}
$('collection-campaign').onchange = () => { $('collection-task').value = ''; fillPublicationTasks(); };
$('reload-publications').onclick = busy($('reload-publications'), loadPublications);
$('collect-selected').onclick = busy($('collect-selected'), async () => {
  const selected = selectedCollectionCampaign();
  if (!selected) throw new InputIssueError('Chọn một đợt đăng.', 'collection-campaign');
  const limit = Number($('comment-limit').value);
  if (!$('comment-limit').value.trim() || !Number.isInteger(limit) || limit < 1 || limit > 500) throw new InputIssueError('Số bình luận cần từ 1 đến 500.', 'comment-limit');
  const task = $('collection-task').value;
  const endpoint = `/api/workflow/campaigns/${encodeURIComponent(selected.id)}` + (task ? `/tasks/${encodeURIComponent(task)}` : '') + '/comments';
  const run = await api(endpoint, 'POST', {limit});
  activeRunId = run.id;
  clearTimeout(poll); mode = 'all'; resetScope();
  await loadHub();
  notice('Đang lấy và lọc comment. Kết quả được gom theo khách hàng ở bảng bên dưới.', 'info');
}, updateCollectionButtons);
$('collection-stop').onclick = busy($('collection-stop'), async () => {
  if (activeRunId) notice((await api('/api/leads/runs/' + activeRunId + '/stop', 'POST')).message, 'info');
}, updateCollectionButtons);

$('history').onchange = () => { if ($('history').value) openSnapshot($('history').value).catch(e => notice(e, 'error')); };
$('back-to-results').onclick = () => { mode = 'all'; resetScope(); loadHub().catch(showRefreshError); };
$('refresh-results').onclick = busy($('refresh-results'), async () => { if (mode === 'history') await watchSnapshot(current.id); else if (mode === 'all') await loadHub(); });
$('clear-article').onclick = () => { postingTaskFilter = ''; render(); };
for (const id of ['campaign-filter', 'group-filter', 'classification', 'interest-filter', 'search']) $(id).addEventListener('input', () => { if (['campaign-filter', 'group-filter'].includes(id)) postingTaskFilter = ''; pageIndex = 0; render(); });
for (const b of document.querySelectorAll('.stats button')) b.onclick = () => { $('classification').value = b.dataset.filter; pageIndex = 0; render(); };
$('previous').onclick = () => { pageIndex--; render(); }; $('next').onclick = () => { pageIndex++; render(); };
$('collect-form').onsubmit = busy($('collect'), async () => {
  const run = await api('/api/leads/collect', 'POST', {post_url: $('post-url').value.trim(), limit: Number($('limit').value)});
  notice('Đang lấy comment từ bài ngoài tool.', 'info'); await openSnapshot(run.id);
}, render);
$('stop').onclick = busy($('stop'), async () => { if (activeRunId) notice((await api('/api/leads/runs/' + activeRunId + '/stop', 'POST')).message, 'info'); }, render);
async function filter(payload) {
  const result = await api('/api/leads/filter', 'POST', payload);
  clearTimeout(poll); refreshVersion++; mode = 'imported'; resetScope();
  current = {...result, status: 'imported'}; activeRunId = null; render();
  $('history').value = '';
  notice('Kết quả nhập tay chưa lưu. Hãy tải Excel nếu cần giữ.', 'info');
}
$('filter-manual').onclick = busy($('filter-manual'), async () => {
  const rows = $('manual-text').value.split(/\r?\n/).filter(t => t.trim()).map(text => ({text}));
  if (!rows.length) throw new Error('Hãy dán ít nhất một bình luận.'); await filter(rows);
});
$('sample').onclick = busy($('sample'), async () => { await filter(await api('/api/exports/comments/example')); notice('Đang xem dữ liệu mẫu, không phải comment Facebook thật.', 'info'); });
$('json-file').onchange = async () => {
  try { const file = $('json-file').files[0]; if (!file) return; if (file.size > 5 * 1024 * 1024) throw new Error('File tối đa 5 MB.'); await filter(JSON.parse((await file.text()).replace(/^\uFEFF/, ''))); }
  catch (e) { notice(e, 'error'); } finally { $('json-file').value = ''; }
};
$('export').onclick = busy($('export'), async () => {
  let response;
  if (mode === 'all') response = await fetch('/api/leads/results/excel?' + queryParams());
  else if (mode === 'history') response = await fetch('/api/leads/runs/' + current.id + '/excel?' + queryParams());
  else response = await fetch('/api/exports/comments', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Revoland-Client': 'local'}, body: JSON.stringify(scopedRecords().flatMap(r => r.comments || [r]))});
  if (!response.ok) throw new Error('Không tạo được Excel. Hãy thử lại.');
  const url = URL.createObjectURL(await response.blob()); downloadUrl(url, 'facebook_leads.xlsx'); setTimeout(() => URL.revokeObjectURL(url), 10000);
}, render);
function signalChips(signals, parent) {
  if (!signals) return;
  const box = node('div', undefined, parent, 'chips');
  const groups = [
    ['intents', 'Nhu cầu', 'chip plus'],
    ['variants', 'Từ khóa', 'chip plus'],
    ['locations', 'Khu vực', 'chip'],
    ['negations', 'Từ chối', 'chip minus'],
    ['spam', 'Spam', 'chip minus'],
  ];
  for (const [key, title, cls] of groups) {
    const raw = signals[key];
    const words = Array.isArray(raw) ? raw : Object.values(raw || {}).flat();
    if (words.length) node('span', `${title}: ${words.join(', ')}`, box, cls);
  }
  const c = signals.contacts;
  if (c?.primary_phone) node('span', 'Có SĐT', box, 'chip plus');
  if (c?.zalo && c.zalo !== c.primary_phone) node('span', 'Có Zalo', box, 'chip plus');
  if (c?.emails?.length) node('span', 'Có Email', box, 'chip plus');
  if (!box.children.length) box.remove();
}

async function loadRegistries() {
  const registries = await api('/api/leads/registries');
  for (const r of registries) {
    const d = node('details', undefined, $('registries'));
    const s = node('summary', r.name, d);
    node('span', `${r.rule_count} nhóm quy tắc · ${r.token_count} từ khóa`, s);
    for (const rule of r.rules) {
      const box = node('div', undefined, d, 'rule');
      node('strong', rule.description, box);
      node('code', rule.score === null ? '' : ` (${rule.score_type === 'penalty' ? '−' : '+'}${rule.score} điểm)`, box);
      if (rule.strength) node('span', ' · Mức ' + interestLabels[rule.strength], box, 'hint');
      if (rule.family) node('p', 'Họ tín hiệu: ' + rule.family + ' · Chỉ lấy điểm cao nhất trong cùng họ.', box, 'hint');
      if (rule.review_only) node('p', 'Chuyển Cần xem lại; không trừ điểm hay tự coi là spam.', box, 'hint');
      if (rule.requires_contact) node('p', 'Chỉ cộng khi có thông tin liên hệ hợp lệ.', box, 'hint');
      if (rule.question_safe) node('p', 'Xét câu hỏi/phủ định theo ngữ cảnh trước khi áp dụng.', box, 'hint');
      node('p', rule.tokens.join(' · '), box);
    }
  }
}

async function init() {
  try {
    for (const [name, id] of [['campaign_id', 'campaign-filter'], ['group_key', 'group-filter']]) {
      const value = requested.get(name); if (value) { node('option', value, $(id)).value = value; $(id).value = value; }
    }
    await loadRegistries();
    await loadPublications();
    if (requested.get('run')) await openSnapshot(requested.get('run')); else await loadHub();
  } catch (e) { notice(e, 'error'); }
}
window.addEventListener('focus', () => { if (mode === 'all') loadHub().catch(showRefreshError); });
init();
