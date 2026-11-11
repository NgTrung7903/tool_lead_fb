'use strict';
let allListings = [], allGroups = [], selectedListingId = null;
let currentActiveCampaignId = null, campaignBusy = false, previewGeneration = 0;
let mockMode = true, sessionAuthenticated = false, sessionBusy = false;
let previewToken = null;
let campaignTimer = null, loginTimer = null;
const byId = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function safeUrl(value) {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? escapeHtml(url.href) : ''; }
  catch { return ''; }
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {'Content-Type':'application/json', 'X-Revoland-Client':'local', ...options.headers}});
  const raw = await response.text();
  let data;
  try { data = JSON.parse(raw); }
  catch { throw new Error('Máy chủ không trả dữ liệu hợp lệ. Kiểm tra cửa sổ chạy ứng dụng.'); }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Dữ liệu không hợp lệ. Kiểm tra các trường nhập.');
  return data;
}
function updateButtons() {
  byId('btn-start-posting').disabled = campaignBusy || mockMode || !sessionAuthenticated || sessionBusy || !selectedListingId;
  byId('mode-banner').textContent = mockMode
    ? 'DỮ LIỆU MẪU — chỉ xem thử. Cấu hình API thật trước khi đăng Facebook.'
    : 'Dữ liệu API thật. Hãy kiểm tra nội dung và ảnh trước khi đăng.';
}
async function checkSessionStatus() {
  try {
    const data = await api('/api/session/status');
    sessionAuthenticated = data.is_authenticated; sessionBusy = data.busy;
    byId('session-status-badge').className = data.is_authenticated ? 'status-posted' : 'status-action';
    byId('session-status-badge').textContent = data.busy ? 'Đang thao tác' : data.is_authenticated ? 'Phiên hoạt động' : 'Cần đăng nhập';
    byId('session-status-desc').textContent = data.login_result && !data.login_result.success ? data.login_result.message : data.status_text;
    byId('header-fb-badge').textContent = data.busy ? 'Facebook đang thao tác' : data.is_authenticated ? 'Facebook sẵn sàng' : 'Facebook cần đăng nhập';
    if (data.login_in_progress) {
      clearTimeout(loginTimer); loginTimer = setTimeout(checkSessionStatus, 3000);
    }
  } catch (error) { byId('session-status-desc').textContent = error.message; sessionAuthenticated = false; }
  updateButtons();
}
async function triggerFbLogin() {
  try {
    const data = await api('/api/session/login', {method:'POST'});
    byId('session-status-desc').textContent = data.message;
    sessionBusy = true; updateButtons();
    clearTimeout(loginTimer); loginTimer = setTimeout(checkSessionStatus, 1500);
  } catch (error) { alert(error.message); }
}
async function logoutFbSession() {
  if (!confirm('Xóa phiên Facebook lưu trên máy này?')) return;
  try { alert((await api('/api/session/logout', {method:'POST'})).message); await checkSessionStatus(); }
  catch (error) { alert(error.message); }
}
async function loadMode() {
  const config = await api('/api/config'); mockMode = config.revoland_mock_mode; updateButtons(); return config;
}
async function loadRevolandListings() {
  selectedListingId = null; ++previewGeneration; updateButtons();
  byId('preview-post-text').value = ''; byId('preview-images-container').replaceChildren();
  byId('listings-container').textContent = 'Đang tải căn...';
  try {
    await loadMode(); allListings = await api('/api/revoland/listings');
    byId('listings-container').innerHTML = allListings.length ? allListings.map(it => `
      <button type="button" data-listing="${escapeHtml(it.id)}" class="listing-card w-full text-left border border-slate-200 p-3 rounded-xl flex gap-3">
        ${safeUrl(it.media_urls[0]) ? `<img alt="Ảnh căn" src="${safeUrl(it.media_urls[0])}" class="w-20 h-20 object-cover rounded-lg">` : ''}
        <span><strong>${escapeHtml(it.title)}</strong><br>${escapeHtml(it.code)} · ${escapeHtml(it.price_text)}<br>${escapeHtml(it.location)}</span>
      </button>`).join('') : 'Không có căn nào trên Revoland.';
    if (allListings.length) await selectListing(allListings[0].id);
  } catch (error) { byId('listings-container').textContent = error.message; }
}
async function selectListing(id) {
  selectedListingId = null; updateButtons();
  const generation = ++previewGeneration;
  byId('preview-post-text').value = ''; byId('preview-images-container').replaceChildren();
  try {
    const data = await api(`/api/revoland/listings/${encodeURIComponent(id)}/preview`);
    if (generation !== previewGeneration) return;
    selectedListingId = id; previewToken = data.preview_token;
    byId('preview-post-text').value = data.formatted_text;
    byId('preview-images-container').innerHTML = data.media_urls.map(url => `<img alt="Ảnh sẽ gửi" src="${safeUrl(url)}" class="w-full rounded-lg border">`).join('');
    document.querySelectorAll('[data-listing]').forEach(el => el.classList.toggle('bg-blue-50', el.dataset.listing === id));
  } catch (error) { if (generation === previewGeneration) alert(error.message); }
  updateButtons();
}
async function loadGroups() {
  try {
    allGroups = await api('/api/groups');
    byId('groups-table-body').innerHTML = allGroups.length ? allGroups.map(g => `<tr>
      <td class="p-3"><input type="checkbox" class="group-checkbox" value="${escapeHtml(g.id)}" ${g.status === 'active' ? '' : 'disabled'}></td>
      <td class="p-3"><strong>${escapeHtml(g.name)}</strong><br><a href="${safeUrl(g.group_url)}" target="_blank" rel="noopener noreferrer" class="text-blue-600">${escapeHtml(g.group_url)}</a></td>
      <td class="p-3">${escapeHtml(g.category || 'Chung')}</td>
      <td class="p-3"><button data-delete-group="${escapeHtml(g.id)}" class="text-rose-600">Xóa</button></td>
      </tr>`).join('') : '<tr><td colspan="4" class="p-4">Chưa có nhóm. Hãy thêm nhóm bạn có quyền đăng.</td></tr>';
  } catch (error) { byId('groups-table-body').textContent = error.message; }
}
function toggleAllCheckboxes(master) { selectAllGroups(master.checked); }
function selectAllGroups(check) {
  byId('check-all-groups').checked = check;
  document.querySelectorAll('.group-checkbox:not(:disabled)').forEach(el => el.checked = check);
}
async function deleteGroup(id) {
  if (!confirm('Xóa nhóm khỏi danh sách?')) return;
  try { await api('/api/groups/' + encodeURIComponent(id), {method:'DELETE'}); await loadGroups(); }
  catch (error) { alert(error.message); }
}
async function startPostingCampaign() {
  if (campaignBusy || mockMode || !sessionAuthenticated || !selectedListingId) return;
  const ids = [...document.querySelectorAll('.group-checkbox:checked')].map(el => el.value);
  if (!ids.length) return alert('Chọn ít nhất một nhóm.');
  const listingId = selectedListingId;
  const content = byId('preview-post-text').value;
  campaignBusy = true; updateButtons();
  try {
    const data = await api('/api/campaigns/create', {method:'POST', body:JSON.stringify({listing_id:listingId, target_group_ids:ids, custom_content:content, preview_token:previewToken})});
    currentActiveCampaignId = data.campaign.id;
    renderCampaignResults(data.campaign);
    byId('results-section').scrollIntoView({behavior:'smooth'});
    await runCampaign(false);
    await loadHistory();
  } catch (error) { campaignBusy = false; updateButtons(); alert(error.message); }
}
async function runCampaign(retry) {
  if (!currentActiveCampaignId) return;
  campaignBusy = true; updateButtons();
  try {
    const data = await api(`/api/campaigns/${encodeURIComponent(currentActiveCampaignId)}/${retry ? 'retry' : 'execute'}`, {method:'POST'});
    renderCampaignResults(data.campaign);
    scheduleCampaignPoll();
  } catch (error) { campaignBusy = false; updateButtons(); alert(error.message); }
}
async function retryFailedGroups() { await runCampaign(true); }
function scheduleCampaignPoll() {
  clearTimeout(campaignTimer); campaignTimer = setTimeout(pollCampaign, 1000);
}
async function pollCampaign() {
  if (!currentActiveCampaignId) return;
  try {
    const data = await api('/api/campaigns/' + encodeURIComponent(currentActiveCampaignId));
    renderCampaignResults(data);
    campaignBusy = ['running','queued'].includes(data.status); updateButtons();
    if (campaignBusy) scheduleCampaignPoll();
    else { await loadHistory(); await checkSessionStatus(); }
  } catch (error) {
    byId('campaign-status-label').textContent = 'Mất kết nối theo dõi: ' + error.message + '. Đang thử kết nối lại; không bấm đăng mới.';
    scheduleCampaignPoll();
  }
}
function renderCampaignResults(campaign) {
  const labels = {pending:'Chưa gửi', running:'Đang thao tác', posted:'Đã xác nhận đăng', pending_approval:'Chờ duyệt',
    failed:'Thất bại trước gửi', action_required:'Cần thao tác', unknown:'Chưa rõ kết quả — cần kiểm tra', skipped_duplicate:'Bỏ qua trùng'};
  const active = ['running','queued'].includes(campaign.status);
  byId('results-table-body').innerHTML = campaign.tasks.map(t => `<tr>
    <td class="px-4 py-3">${escapeHtml(t.group_name)}</td>
    <td class="px-4 py-3"><span class="${t.status === 'posted' ? 'status-posted' : t.status === 'failed' ? 'status-failed' : 'status-pending'}">${labels[t.status] || escapeHtml(t.status)}</span></td>
    <td class="px-4 py-3">${t.post_url ? `<a class="text-blue-600" href="${safeUrl(t.post_url)}" target="_blank" rel="noopener noreferrer">Xem bài đăng</a><br>` : ''}${escapeHtml(t.error_message || '')}
      ${!active && ['unknown','pending_approval'].includes(t.status) ? `<br><button data-resolve-task="${escapeHtml(t.task_id)}" class="text-blue-600 underline">Kiểm tra và xác nhận</button>` : ''}</td>
    <td class="px-4 py-3">${t.retry_count}</td><td class="px-4 py-3">${t.posted_at ? escapeHtml(new Date(t.posted_at).toLocaleString('vi-VN')) : '—'}</td>
    </tr>`).join('');
  byId('campaign-status-label').textContent = `${campaign.listing_title} · ${campaign.status} · ${campaign.source_mode}${campaign.error_message ? ' · ' + campaign.error_message : ''}`;
  byId('btn-retry-failed').classList.toggle('hidden', active || campaign.source_mode !== 'live' || !campaign.tasks.some(t => ['failed','action_required','unknown'].includes(t.status)));
  byId('btn-retry-failed').disabled = active;
  byId('btn-resume-campaign').classList.toggle('hidden', active || campaign.source_mode !== 'live' || !campaign.tasks.some(t => t.status === 'pending'));
}
async function resolveTask(taskId) {
  const outcome = prompt('Sau khi kiểm tra trực tiếp nhóm Facebook, nhập:\n1 = đã đăng (cần link bài)\n2 = đang chờ duyệt\n3 = chắc chắn chưa gửi hoặc đã bị từ chối, cho phép thử lại');
  const mapping = {'1':'posted','2':'pending_approval','3':'not_submitted'};
  if (!mapping[outcome]) return;
  const postUrl = outcome === '1' ? prompt('Dán permalink bài viết đúng nhóm:') : null;
  if (outcome === '1' && !postUrl) return;
  if (!confirm('Xác nhận bạn đã kiểm tra kết quả trực tiếp trên Facebook? Nếu chọn chưa gửi, lần thử lại có thể tạo bài mới.')) return;
  try {
    const data = await api(`/api/campaigns/${encodeURIComponent(currentActiveCampaignId)}/tasks/${encodeURIComponent(taskId)}/resolve`,
      {method:'POST', body:JSON.stringify({outcome:mapping[outcome], post_url:postUrl, confirmed:true})});
    renderCampaignResults(data.campaign); await loadHistory();
  } catch (error) { alert(error.message); }
}
async function loadHistory() {
  const campaigns = await api('/api/campaigns');
  byId('campaign-history').innerHTML = '<option value="">Chọn chiến dịch trong lịch sử</option>' + campaigns.map(c =>
    `<option value="${escapeHtml(c.id)}">${escapeHtml(c.listing_title)} · ${escapeHtml(c.status)} · ${escapeHtml(c.created_at)}</option>`).join('');
  byId('campaign-history').value = currentActiveCampaignId || '';
  return campaigns;
}
async function selectHistory() {
  if (campaignBusy) return alert('Đợi chiến dịch đang chạy hoàn tất.');
  const id = byId('campaign-history').value;
  if (!id) return;
  currentActiveCampaignId = id; await pollCampaign();
}
async function openConfigModal() {
  try {
    const cfg = await loadMode();
    for (const [id, key] of [['cfg-api-url','revoland_api_url'],['cfg-contact-phone','contact_phone'],['cfg-contact-name','contact_name'],['cfg-min-delay','min_delay_seconds'],['cfg-max-delay','max_delay_seconds']]) byId(id).value = cfg[key];
    byId('cfg-api-key').value = ''; byId('cfg-api-key').placeholder = cfg.api_key_configured ? 'Đã lưu API key — để trống để giữ nguyên' : 'Nhập API key';
    byId('cfg-mock-mode').checked = cfg.revoland_mock_mode;
    byId('modal-config').classList.remove('hidden');
  } catch (error) { alert(error.message); }
}
function closeConfigModal() { byId('modal-config').classList.add('hidden'); byId('test-connection-result').classList.add('hidden'); }
function configPayload() {
  return {revoland_api_url:byId('cfg-api-url').value.trim(), revoland_api_key:byId('cfg-api-key').value.trim(),
    revoland_mock_mode:byId('cfg-mock-mode').checked, contact_phone:byId('cfg-contact-phone').value.trim(),
    contact_name:byId('cfg-contact-name').value.trim(), min_delay_seconds:Number(byId('cfg-min-delay').value), max_delay_seconds:Number(byId('cfg-max-delay').value)};
}
async function testRevolandPing() {
  const box = byId('test-connection-result'); box.classList.remove('hidden'); box.textContent = 'Đang lưu và kiểm tra cấu hình...';
  try {
    await api('/api/config', {method:'POST',body:JSON.stringify(configPayload())});
    const data = await api('/api/revoland/test-connection', {method:'POST'}); box.textContent = data.message;
    await loadRevolandListings();
  } catch (error) { box.textContent = error.message; }
}
async function saveSystemConfig(event) {
  event.preventDefault();
  try { await api('/api/config', {method:'POST', body:JSON.stringify(configPayload())}); closeConfigModal(); await loadRevolandListings(); }
  catch (error) { alert(error.message); }
}
function openAddGroupModal() {
  ['new-group-name','new-group-url','new-group-category','bulk-groups-text'].forEach(id => byId(id).value = '');
  byId('modal-group').classList.remove('hidden');
}
function closeAddGroupModal() { byId('modal-group').classList.add('hidden'); }
async function submitNewGroup() {
  try {
    const raw = byId('bulk-groups-text').value.trim();
    if (raw) alert((await api('/api/groups/import', {method:'POST',body:JSON.stringify({raw_text:raw})})).message);
    else await api('/api/groups', {method:'POST',body:JSON.stringify({name:byId('new-group-name').value,group_url:byId('new-group-url').value,category:byId('new-group-category').value})});
    closeAddGroupModal(); await loadGroups();
  } catch (error) { alert(error.message); }
}
async function downloadExcel(path, options, filename) {
  const response = await fetch(path, {...options, headers:{'Content-Type':'application/json','X-Revoland-Client':'local'}});
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Không xuất được Excel. Kiểm tra dữ liệu và server.');
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = filename;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function exportPostingResults(allHistory) {
  if (!allHistory && !currentActiveCampaignId) return alert('Chọn một chiến dịch trong lịch sử trước.');
  const btn = byId(allHistory ? 'btn-export-all' : 'btn-export-campaign');
  btn.disabled = true;
  byId('export-status').textContent = 'Đang tạo báo cáo kết quả đăng bài...';
  try {
    const query = allHistory ? '' : '?campaign_id=' + encodeURIComponent(currentActiveCampaignId);
    await downloadExcel('/api/exports/campaigns' + query, {method:'GET'}, 'ket_qua_dang_bai.xlsx');
    byId('export-status').textContent = 'Đã tạo báo cáo. Xem danh sách tải xuống của trình duyệt; kết quả là trạng thái tại thời điểm xuất.';
  } catch (error) { byId('export-status').textContent = error.message; }
  finally { btn.disabled = false; }
}
async function exportCommentResults() {
  const file = byId('comments-json-file').files[0];
  if (!file) return alert('Chọn file JSON bình luận trước, hoặc tải file mẫu bên cạnh.');
  if (file.size > 5 * 1024 * 1024) return alert('File JSON vượt 5 MB.');
  const btn = byId('btn-export-comments'); btn.disabled = true;
  byId('export-status').textContent = 'Đang lọc bình luận và tạo Excel...';
  try {
    let payload;
    try { payload = JSON.parse((await file.text()).replace(/^\uFEFF/, '')); }
    catch { throw new Error('File cần là JSON hợp lệ, mã hóa UTF-8. Hãy tham khảo file mẫu.'); }
    await downloadExcel('/api/exports/comments', {method:'POST',body:JSON.stringify(payload)}, 'binh_luan_lead.xlsx');
    byId('export-status').textContent = 'Đã tạo Excel bình luận/lead. Xem danh sách tải xuống; không có lead nào được gửi lên Revoland.';
  } catch (error) { byId('export-status').textContent = error.message; }
  finally { btn.disabled = false; }
}

document.addEventListener('click', event => {
  const listing = event.target.closest('[data-listing]'); if (listing) selectListing(listing.dataset.listing);
  const group = event.target.closest('[data-delete-group]'); if (group) deleteGroup(group.dataset.deleteGroup);
  const task = event.target.closest('[data-resolve-task]'); if (task) resolveTask(task.dataset.resolveTask);
});
window.onload = async () => {
  await Promise.all([checkSessionStatus(), loadRevolandListings(), loadGroups()]);
  try {
    const history = await loadHistory();
    const campaign = history.find(c => ['running','queued'].includes(c.status)) || history[0];
    if (campaign) { currentActiveCampaignId = campaign.id; await pollCampaign(); }
  } catch (error) { byId('campaign-status-label').textContent = error.message; }
};
