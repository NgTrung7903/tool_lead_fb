'use strict';
/* Trang Đăng tin: lấy tin → duyệt nội dung/ảnh → chọn nhóm → đăng. Dùng hàm chung trong common.js. */
let preview = null, campaign = null, poll = null, groupRows = [], maxGroupsPerBatch = 100;
let savedOffset = 0, savedTotal = 0, savedAllCount = 0;
let listingSelectionVersion = 0, sourceImagesLoading = false, importingJson = false;
function imageCount(row) { return row.image_count ?? (row.media_urls || []).length; }
function contentChanged() {
  updateCount();
  $('reviewed').checked = false;
}

$('json-form').onsubmit = busy($('json-import'), async () => {
  const file = $('post-json').files[0];
  if (!file || !file.name.toLowerCase().endsWith('.json')) throw new InputIssueError('Hãy chọn file .json chứa bài đăng.', 'post-json');
  let data;
  try {
    const buf = await file.arrayBuffer();
    const head = new Uint8Array(buf, 0, Math.min(2, buf.byteLength));
    const encoding = (head[0] === 0xff && head[1] === 0xfe) ? 'utf-16le'
      : (head[0] === 0xfe && head[1] === 0xff) ? 'utf-16be' : 'utf-8';
    const rawText = new TextDecoder(encoding, {fatal: true}).decode(buf).replace(/^\uFEFF/, '');
    data = JSON.parse(rawText);
  } catch { throw new InputIssueError('Không đọc được file JSON. Hãy kiểm tra định dạng JSON hợp lệ.', 'post-json', 'Sửa cấu trúc file JSON rồi chọn và nạp lại.'); }
  $('json-summary').textContent = 'Đang nạp bài và tải ảnh về máy… Nếu ảnh nằm sau Cloudflare, cửa sổ trình duyệt có thể mở ra — hãy bấm xác minh nếu được yêu cầu.';
  const imported = new Map();
  const fast = $('json-fast').checked;
  const batchSize = fast ? 200 : 20;
  importingJson = true; updateSavedButtons();
  try {
    const wrapped = data && !Array.isArray(data) && typeof data === 'object'
      ? ['posts', 'listings', 'data', 'items', 'records', 'results'].map(key => data[key]).find(Array.isArray) : null;
    const records = Array.isArray(data) ? data : wrapped;
    // Large exports are saved in small requests, so completed batches remain
    // available even if a later request is interrupted.
    const entries = records ? records.map((row, index) => ({row, index})) : null;
    const pending = entries && entries.length > batchSize
      ? entries.filter(item => !(item.row && item.row.isDeleted === true)) : null;
    const chunks = pending && pending.length
      ? Array.from({length: Math.ceil(pending.length / batchSize)}, (_, i) => pending.slice(i * batchSize, (i + 1) * batchSize)) : null;
    const batches = chunks ? chunks.map(chunk => chunk.map(item => item.row)) : [data];
    const sourceRows = chunks ? chunks.map(chunk => chunk.map(item => item.index)) : [entries?.map(item => item.index) || [0]];
    for (let i = 0; i < batches.length; i++) {
      const doneImages = [...imported.values()].reduce((n, r) => n + imageCount(r), 0);
      $('json-summary').textContent = fast
        ? `Đang nạp nhanh đợt ${i + 1}/${batches.length}. Đã lưu ${imported.size} bài; ảnh sẽ tải khi chọn xem bài.`
        : `Đang nạp đợt ${i + 1}/${batches.length}. Đã lưu ${imported.size} bài, ${doneImages} ảnh. Hãy giữ cửa sổ tool đang mở.`;
      const batchRows = await api('/api/sources/json', 'POST', {filename: file.name, data: batches[i], defer_images: fast, compact: true}, {sourceRows: sourceRows[i]});
      for (const row of batchRows) imported.set(row.id, row);
      if (!fast && i === 0 && batchRows.length) await loadListings(batchRows[0].id);
    }
    const rows = [...imported.values()];
    await loadListings(rows[0].id);
    const images = rows.reduce((n, r) => n + imageCount(r), 0);
    const failed = rows.filter(r => (r.image_errors || []).length);
    const failedCount = failed.reduce((n, r) => n + r.image_errors.length, 0);
    $('json-summary').textContent = (fast
      ? `Đã nạp ${rows.length} bài. Chế độ nạp nhanh: ảnh được tải và lưu khi chọn xem từng bài.`
      : `Đã nạp ${rows.length} bài, ${images} ảnh.`) +
      (failedCount ? ` ${failedCount} ảnh chưa tải được ở ${failed.length} bài (xem chi tiết khi chọn bài).` : '') +
      ' Chọn từng bài trong danh sách để duyệt và đăng.';
    notice(failedCount
      ? `Đã nạp ${rows.length} bài nhưng ${failedCount} ảnh chưa tải được: ${failed.slice(0, 3).map(r => `"${r.title.slice(0, 40)}" — ${r.image_errors[0]}`).join(' | ')}`
      : `Đã nạp ${rows.length} bài từ file JSON. Hãy đọc lại nội dung và ảnh ở bước 3.`, failedCount ? 'warn' : 'success');
  } catch (e) {
    $('json-summary').textContent = imported.size
      ? `Đã lưu ${imported.size} bài trước khi bị gián đoạn. Hãy nạp lại file để tải lại ảnh.`
      : 'Chưa nạp được file. Hãy kiểm tra thông báo lỗi và thử lại.';
    if (imported.size) await loadListings([...imported.keys()][0]);
    throw e;
  } finally { importingJson = false; updateSavedButtons(); }
});

const postCheckLabels = {unchecked: 'Chưa kiểm tra lại link', available: 'Bài còn truy cập được',
  unavailable: 'Bài không còn hiển thị', action_required: 'Cần đăng nhập/xác minh', unknown: 'Chưa kết luận được tình trạng link'};

const taskLabels = {pending: 'Chưa đăng', queued: 'Đang chờ', running: 'Đang đăng...', posted: 'Đã xác nhận đăng',
  pending_approval: 'Chờ admin nhóm duyệt', unknown: 'Chưa rõ kết quả', failed: 'Lỗi', action_required: 'Cần bạn thao tác',
  skipped_duplicate: 'Bỏ qua — đã đăng trước đó'};
const campaignLabels = {created: 'Sẵn sàng đăng', queued: 'Đang chờ', running: 'Đang đăng...', completed: 'Hoàn tất',
  partial_failed: 'Có nhóm bị lỗi', needs_review: 'Cần bạn kiểm tra', interrupted: 'Bị gián đoạn', paused: 'Tạm dừng',
  action_required: 'Cần bạn thao tác', failed: 'Lỗi'};
const taskHelp = {
  unknown: 'Facebook chưa kịp hiển thị bài ngay lúc gửi. Bấm “Tự kiểm tra trên Facebook” bên dưới để tool tự vào nhóm xác nhận (không cần kiểm tra tay).',
  pending_approval: 'Bài đã gửi và đang chờ admin nhóm duyệt. Khi muốn kiểm tra xem admin đã duyệt chưa, bấm “Tự kiểm tra trên Facebook” bên dưới.',
  action_required: 'Facebook cần bạn đăng nhập hoặc xác minh. Bấm “Đăng nhập Facebook” ở góc trên, xong rồi bấm “Đăng lại các nhóm bị lỗi”.',
  failed: 'Chưa gửi được bài. Bạn có thể bấm “Đăng lại các nhóm bị lỗi”.',
  skipped_duplicate: 'Tin này đã được đăng vào nhóm này trước đó nên tool bỏ qua để tránh đăng trùng.'};


/* ---------- Thanh tiến trình ---------- */
function updateStepper() {
  const logged = !!fb.status?.is_authenticated;
  const done = {1: logged, 2: !!preview, 3: !!campaign, 4: !!campaign?.tasks.some(t => ['posted', 'pending_approval'].includes(t.status))};
  const current = [1, 2, 3, 4].find(n => !done[n]) || 4;
  for (const li of document.querySelectorAll('#stepper li')) {
    const n = Number(li.dataset.step);
    li.className = done[n] ? 'done' : n === current ? 'current' : '';
    li.querySelector('span').textContent = done[n] ? '✓' : n;
  }
  for (const n of [2, 3, 4]) $('step-' + n).classList.toggle('done', !!done[n]);
}

window.addEventListener('fb-session', e => {
  const s = e.detail;
  $('login-banner').hidden = !!(s.is_authenticated || s.login_in_progress) || /lưu|Kiểm tra/.test(s.status_text || '');
  updateStepper();
});
$('banner-login').onclick = () => $('login').click();

/* ---------- Bước 2: lấy tin ---------- */
function updateSavedButtons() {
  $('saved-delete-current').disabled = importingJson || !$('listings').value;
  $('saved-delete-selected').disabled = importingJson || !document.querySelector('.saved-delete-choice:checked');
  $('saved-delete-all').disabled = importingJson || !savedAllCount;
}
async function loadListings(selected) {
  const params = new URLSearchParams({summary: 'true', q: $('saved-search').value.trim(),
    offset: savedOffset, limit: 100, selected_id: selected || ''});
  const catalog = await api('/api/sources/listings?' + params);
  savedTotal = catalog.total; savedAllCount = catalog.all_count;
  if (savedOffset && savedOffset >= savedTotal) { savedOffset = Math.max(0, Math.ceil(savedTotal / 100) * 100 - 100); return loadListings(selected); }
  const rows = catalog.items;
  $('listings').replaceChildren(); $('saved-delete-list').replaceChildren();
  $('saved-check-page').checked = false;
  node('option', savedTotal ? `— Chọn bài để xem (${savedTotal} bài phù hợp / ${savedAllCount} bài đã lưu) —` : 'Chưa có bài phù hợp', $('listings')).value = '';
  for (const row of rows) {
    const label = node('label', undefined, $('saved-delete-list'));
    label.style.display = 'block';
    const checkbox = node('input', undefined, label);
    checkbox.type = 'checkbox'; checkbox.value = row.id; checkbox.className = 'saved-delete-choice';
    checkbox.onchange = updateSavedButtons;
    label.append(document.createTextNode(' ' + row.title));
  }
  if (catalog.selected && !rows.some(row => row.id === catalog.selected.id)) rows.push(catalog.selected);
  for (const row of rows) {
    const prefix = row.source_mode === 'mock' ? '[TIN GIẢ — KHÔNG ĐĂNG FB] ' : '';
    node('option', prefix + row.title, $('listings')).value = row.id;
  }
  $('saved-page').textContent = savedTotal ? `${savedOffset + 1}–${Math.min(savedOffset + 100, savedTotal)} / ${savedTotal} bài` : '0 bài';
  $('saved-prev').disabled = !savedOffset; $('saved-next').disabled = savedOffset + 100 >= savedTotal;
  if (selected) $('listings').value = selected;
  updateSavedButtons();
  await selectListing();
}
$('saved-search-btn').onclick = () => { savedOffset = 0; loadListings().catch(e => notice(e, 'error')); };
$('saved-search').onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); $('saved-search-btn').click(); } };
$('saved-prev').onclick = () => { savedOffset = Math.max(0, savedOffset - 100); loadListings().catch(e => notice(e, 'error')); };
$('saved-next').onclick = () => { savedOffset += 100; loadListings().catch(e => notice(e, 'error')); };
$('saved-check-page').onchange = () => { for (const box of document.querySelectorAll('.saved-delete-choice')) box.checked = $('saved-check-page').checked; updateSavedButtons(); };
async function deleteSavedPosts(ids, deleteAll = false) {
  if (importingJson) throw new Error('Hãy chờ nạp file xong trước khi xóa bài.');
  if (!deleteAll && !ids.length) throw new InputIssueError('Hãy chọn bài cần xóa.', 'saved-delete-list');
  const count = deleteAll ? savedAllCount : ids.length;
  if (!confirm(`Xóa ${count} bài khỏi kho trên máy? Bài trên Facebook và các đợt đăng đã lưu vẫn giữ nguyên.`)) return;
  const result = await api('/api/sources/listings/delete', 'POST', {ids, delete_all: deleteAll});
  savedOffset = 0;
  await loadListings();
  notice(`Đã xóa ${result.deleted} bài khỏi kho trên máy.`, 'success');
}
$('saved-delete-current').onclick = busy($('saved-delete-current'), () => deleteSavedPosts([$('listings').value]), updateSavedButtons);
$('saved-delete-selected').onclick = busy($('saved-delete-selected'), () => deleteSavedPosts([...document.querySelectorAll('.saved-delete-choice:checked')].map(box => box.value)), updateSavedButtons);
$('saved-delete-all').onclick = busy($('saved-delete-all'), () => deleteSavedPosts([], true), updateSavedButtons);

function updateCount() {
  const n = $('content').value.length;
  $('content-count').textContent = n ? n.toLocaleString('vi-VN') + ' ký tự' : '';
}

function switchToManualCompose(rawTitle = '', rawBody = '') {
  $('other-sources').open = true;
  $('manual-box').open = true;
  const cleanTitle = String(rawTitle || '').replace(/^\[TIN MẪU\]\s*/i, '').replace(/^DỮ LIỆU MẪU\s*[—-]\s*/i, '').trim();
  if (cleanTitle && !$('manual-title').value.trim()) $('manual-title').value = cleanTitle;
  const cleanBody = String(rawBody || '').replace(/^DỮ LIỆU MẪU[^\n]*\n*/i, '').trim();
  if (cleanBody && !$('manual-desc').value.trim()) $('manual-desc').value = cleanBody;
  $('manual-box').scrollIntoView({behavior: 'smooth', block: 'start'});
  setTimeout(() => $('manual-title').focus(), 250);
}

function updateCreateButton() {
  $('create').disabled = !preview || sourceImagesLoading;
  $('create').textContent = preview?.listing?.source_mode === 'mock'
    ? 'Lưu bản xem thử (Tin mẫu — không gửi Facebook)'
    : 'Lưu & chuẩn bị đăng';
}

async function selectListing() {
  const version = ++listingSelectionVersion;
  const id = $('listings').value;
  preview = null; sourceImagesLoading = false; updateCreateButton(); updateSavedButtons(); $('reviewed').checked = false;
  $('photos').replaceChildren(); $('content').value = ''; updateCount();
  $('source-info').textContent = 'Hãy chọn một tin ở bước 2 để xem trước bài đăng.';
  if (!id) { updateStepper(); return; }
  let result = await api('/api/sources/listings/' + encodeURIComponent(id) + '/preview');
  if (version !== listingSelectionVersion) return;
  preview = result;
  sourceImagesLoading = !!preview.listing.pending_image_count;
  renderListingPreview(true);
  if (sourceImagesLoading) {
    try {
      result = await api('/api/sources/listings/' + encodeURIComponent(id) + '/load-images', 'POST');
      if (version !== listingSelectionVersion) return;
      preview = result; sourceImagesLoading = false;
      $('reviewed').checked = false;
      renderListingPreview(false);
    } catch (error) {
      if (version !== listingSelectionVersion) return;
      sourceImagesLoading = true; updateCreateButton();
      $('photos').textContent = 'Chưa tải được ảnh. Chọn lại bài để thử lại.';
      throw error;
    }
  }
}
function renderListingPreview(setContent) {
  if (setContent) { $('content').value = preview.formatted_text; updateCount(); }
  $('photos').replaceChildren();
  const info = $('source-info'); info.replaceChildren();
  if (preview.listing.source_mode === 'mock') {
    node('b', '⚠ Đang chọn DỮ LIỆU MẪU — chỉ dùng để xem thử giao diện, hệ thống sẽ khóa nút đăng Facebook. ', info);
    const btn = node('button', 'Soạn tin thật để đăng Facebook', info, 'secondary small');
    btn.type = 'button';
    btn.onclick = () => switchToManualCompose('', '');
  } else if (preview.listing.folder_name) {
    node('span', `Folder: ${preview.listing.folder_name} · Nội dung: ${preview.listing.content_file}. Bạn có thể sửa bài và bỏ chọn ảnh bên dưới.`, info);
  } else if (preview.listing.source_url) {
    node('span', 'Nguồn tin: ', info); safeLink(info, preview.listing.source_url, preview.listing.source_url);
  } else if (preview.listing.id.startsWith('json_')) {
    node('span', 'Bài đã nạp từ file JSON. Hãy đọc lại nội dung và ảnh trước khi đăng.', info);
  } else {
    node('span', 'Tin bạn tự soạn trên máy tính (sẵn sàng đăng thật).', info);
  }
  for (const [i, url] of preview.media_urls.entries()) {
    const label = node('label', undefined, $('photos'), 'photo');
    const checkbox = node('input', undefined, label);
    checkbox.type = 'checkbox'; checkbox.checked = true; checkbox.value = i; checkbox.className = 'photo-choice';
    const image = node('img', undefined, label); image.src = url; image.alt = 'Ảnh ' + (i + 1); image.loading = 'lazy';
    node('span', 'Ảnh ' + (i + 1), label);
  }
  if (!preview.media_urls.length) node('div', sourceImagesLoading
    ? `Đang tải ${preview.listing.pending_image_count} ảnh của bài này… Nội dung đã sẵn sàng để đọc.`
    : 'Tin này không có ảnh.', $('photos'), 'empty');
  const imageErrors = preview.listing.image_errors || [];
  if (imageErrors.length) {
    const box = node('div', `⚠ ${imageErrors.length} ảnh trong file chưa tải được (bài vẫn đăng được với các ảnh hiển thị ở trên):`, $('photos'), 'empty');
    const list = node('ul', undefined, box);
    for (const err of imageErrors) node('li', err, list);
  }
  updateCreateButton(); updateStepper();
  $('step-3').scrollIntoView({behavior: 'smooth', block: 'start'});
}

$('listings').onchange = () => selectListing().catch(e => notice(e, 'error'));
$('clean-content').onclick = busy($('clean-content'), async () => {
  const before = $('content').value;
  const result = await api('/api/sources/clean-content', 'POST', {content: before});
  if ($('content').value !== before) throw new InputIssueError('Nội dung vừa thay đổi. Hãy bấm làm sạch lại.', 'content');
  if (result.changed) {
    $('content').value = result.content; contentChanged();
    notice('Đã bỏ mã HTML và sắp xếp xuống dòng. Hãy đọc lại nội dung rồi đánh dấu đã duyệt.', 'success');
  } else notice('Nội dung hiện không có mã HTML cần làm sạch.', 'info');
});
$('content').addEventListener('input', () => {
  contentChanged();
});
$('source-form').onsubmit = busy($('import'), async () => {
  notice('Đang đọc dữ liệu từ link, soạn nội dung và tải ảnh, vui lòng chờ...', 'info');
  const rows = await api('/api/sources/import', 'POST', {url: $('source-url').value.trim()});
  await loadListings(rows[0]?.id);
  const failedImages = rows.reduce((total, row) => total + (row.image_errors || []).length, 0);
  notice(`Đã lấy ${rows.length} tin và soạn nội dung.` +
    (failedImages ? ` Có ${failedImages} ảnh tải lỗi; xem chi tiết bên dưới.` : '') +
    ' Hãy đọc lại nội dung và ảnh ở bước 3 trước khi đăng.', failedImages ? 'warn' : 'success');
});
$('demo').onclick = busy($('demo'), async () => {
  const rows = await api('/api/sources/demo', 'POST');
  await loadListings(rows[0].id);
  notice('Đã tải dữ liệu giả để xem thử giao diện. Dữ liệu giả không được đăng lên Facebook.', 'warn');
});

async function loadQuinlandCatalog(query = '') {
  const rows = await api('/api/sources/quinland?limit=100' + (query ? '&q=' + encodeURIComponent(query) : ''));
  const sel = $('quinland-select');
  sel.replaceChildren();
  if (!rows.length) {
    node('option', query ? 'Không tìm thấy căn nào khớp từ khóa' : 'Chưa có kho dữ liệu QuinLand', sel).value = '';
    $('quinland-box').hidden = !query;
    return;
  }
  $('quinland-box').hidden = false;
  for (const r of rows) {
    const area = r.area_m2 ? ` · ${r.area_m2}m²` : '';
    node('option', `[#${r.index + 1}] ${r.property_type} · ${r.price_text}${area} (${r.image_count} ảnh) — ${r.title}`, sel).value = r.oid;
  }
}
$('quinland-search-btn').onclick = busy($('quinland-search-btn'), () => loadQuinlandCatalog($('quinland-search').value.trim()));
$('quinland-search').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); $('quinland-search-btn').click(); }
});
$('quinland-pack').onclick = busy($('quinland-pack'), async () => {
  notice('Đang nạp 8 bài tin BĐS TP.HCM và tải ảnh thực tế từ QuinLand, vui lòng chờ vài giây...', 'info');
  const rows = await api('/api/sources/quinland/import', 'POST', {record_ids: [], max_images: 4});
  await loadListings(rows[0]?.id);
  notice(`Đã nạp ${rows.length} bài tin BĐS TP.HCM kèm ảnh thật! Bạn có thể chọn nhóm ở Bước 3 và bấm “Bắt đầu đăng” ở Bước 4.`, 'success');
});
$('quinland-import-one').onclick = busy($('quinland-import-one'), async () => {
  const oid = $('quinland-select').value;
  if (!oid) throw new InputIssueError('Hãy chọn một căn trong danh sách QuinLand.', 'quinland-select');
  notice('Đang tải thông tin và ảnh BĐS từ QuinLand...', 'info');
  const rows = await api('/api/sources/quinland/import', 'POST', {record_ids: [oid], max_images: 4});
  await loadListings(rows[0]?.id);
  notice('Đã tải xong bài tin và ảnh! Kiểm tra nội dung ở Bước 3 rồi lưu để đăng.', 'success');
});

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('Không đọc được file ảnh: ' + file.name));
    reader.readAsDataURL(file);
  });
}

$('manual-photos').onchange = () => {
  const files = [...$('manual-photos').files];
  $('manual-photo-hint').textContent = files.length ? `Đã chọn ${files.length} ảnh từ máy tính.` : '';
};
$('manual-form').onsubmit = busy($('manual-submit'), async () => {
  const files = [...$('manual-photos').files];
  if (files.length > 12) throw new InputIssueError('Mỗi bài tối đa 12 ảnh. Vui lòng chọn bớt ảnh.', 'manual-photos');
  if (files.some(f => f.size > 15 * 1024 * 1024)) throw new InputIssueError('Mỗi ảnh không vượt quá 15 MB.', 'manual-photos');
  if (files.length) notice(`Đang chuẩn bị ${files.length} ảnh...`, 'info');
  const images = await Promise.all(files.map(fileToDataUrl));
  const areaRaw = $('manual-area').value.trim();
  const rows = await api('/api/sources/manual', 'POST', {
    title: $('manual-title').value.trim(),
    price_text: $('manual-price').value.trim(),
    location: $('manual-location').value.trim(),
    area_m2: areaRaw === '' ? null : Number(areaRaw),
    description: $('manual-desc').value.trim(),
    images_base64: images,
  });
  $('manual-form').reset();
  $('manual-photo-hint').textContent = '';
  $('manual-box').open = false;
  await loadListings(rows[0].id);
  notice('Đã lưu tin của bạn. Hãy kiểm tra lại bài đăng và chọn nhóm ở bước 3.', 'success');
});

/* ---------- Bước 3: nhóm ---------- */
async function loadGroups() {
  const selected = new Set([...document.querySelectorAll('.group-choice:checked')].map(e => e.value));
  groupRows = await api('/api/groups');
  $('groups').replaceChildren();
  for (const g of groupRows) {
    const label = node('label', undefined, $('groups'), 'group-item');
    const c = node('input', undefined, label);
    c.type = 'checkbox'; c.value = g.id; c.className = 'group-choice'; c.checked = selected.has(g.id); c.disabled = g.status !== 'active';
    const meta = node('div', undefined, label, 'meta');
    node('b', g.name, meta); node('small', g.group_url.replace('https://www.facebook.com/', 'facebook.com/') + (g.status !== 'active' ? ' · tạm dừng' : ''), meta);
    const remove = node('button', '×', label, 'remove'); remove.type = 'button'; remove.title = 'Xóa nhóm khỏi danh sách';
    remove.onclick = busy(remove, async e => {
      e.stopPropagation();
      if (!confirm(`Xóa nhóm “${g.name}” khỏi danh sách?\n(Không ảnh hưởng gì trên Facebook.)`)) return;
      await api('/api/groups/' + encodeURIComponent(g.id), 'DELETE');
      await loadGroups();
      notice('Đã xóa nhóm khỏi danh sách.', 'success');
    });
  }
  if (!groupRows.length) {
    node('div', 'Chưa có nhóm nào. Bấm “+ Thêm nhóm Facebook” bên dưới.', $('groups'), 'empty');
    $('add-group-box').open = true;
  } else if (groupRows.length < 2) {
    $('add-group-box').open = true;
  }
  updateSelectAll();
}
function updateSelectAll() {
  const boxes = [...document.querySelectorAll('.group-choice:not(:disabled)')];
  const checked = boxes.filter(b => b.checked);
  const cap = Math.min(boxes.length, maxGroupsPerBatch);
  if ($('group-count-badge')) {
    $('group-count-badge').textContent = `Đã chọn ${checked.length} / ${maxGroupsPerBatch} nhóm`;
    $('group-count-badge').className = 'badge ' + (checked.length ? 'posted' : 'pending');
  }
  if ($('group-batch-hint')) {
    const hint = $('group-batch-hint');
    hint.replaceChildren();
    node('span', 'Lưu sẵn danh sách nhóm của bạn và tích chọn ', hint);
    node('b', `tối đa ${maxGroupsPerBatch} nhóm cho mỗi đợt đăng`, hint);
    node('span', '.', hint);
  }
  $('select-all').hidden = !boxes.length;
  const fullSelected = cap > 0 && checked.length >= cap;
  $('select-all').textContent = fullSelected
    ? 'Bỏ chọn tất cả'
    : (boxes.length > maxGroupsPerBatch ? `Chọn ${maxGroupsPerBatch} nhóm đầu` : 'Chọn tất cả');
}
$('groups').addEventListener('change', e => {
  const checked = [...document.querySelectorAll('.group-choice:not(:disabled):checked')];
  if (checked.length > maxGroupsPerBatch && e.target?.classList?.contains('group-choice')) {
    e.target.checked = false;
    notice(`Mỗi đợt chỉ đăng tối đa ${maxGroupsPerBatch} nhóm trong hàng chờ.`, 'warn');
  }
  updateSelectAll();
});
$('select-all').onclick = () => {
  const boxes = [...document.querySelectorAll('.group-choice:not(:disabled)')];
  const checked = boxes.filter(b => b.checked);
  const cap = Math.min(boxes.length, maxGroupsPerBatch);
  if (cap > 0 && checked.length >= cap) {
    boxes.forEach(b => { b.checked = false; });
  } else {
    boxes.forEach((b, idx) => { b.checked = idx < maxGroupsPerBatch; });
  }
  updateSelectAll();
};
$('group-form').onsubmit = busy($('add-group'), async () => {
  const url = $('group-url').value.trim();
  await api('/api/groups', 'POST', {name: $('group-name').value.trim(), group_url: url});
  $('group-form').reset();
  await loadGroups();
  const added = groupRows.find(g => url.toLowerCase().includes(g.group_url.split('/groups/')[1]));
  const currentChecked = document.querySelectorAll('.group-choice:not(:disabled):checked').length;
  if (added && currentChecked < maxGroupsPerBatch) {
    const box = document.querySelector(`.group-choice[value="${CSS.escape(added.id)}"]`);
    if (box) box.checked = true;
  }
  updateSelectAll();
  notice('Đã thêm nhóm.', 'success');
});
$('bulk-import').onclick = busy($('bulk-import'), async () => {
  const text = $('bulk-groups').value;
  if (!text.trim()) throw new InputIssueError('Hãy dán ít nhất một link nhóm.', 'bulk-groups');
  const r = await api('/api/groups/import', 'POST', {raw_text: text});
  $('bulk-groups').value = '';
  await loadGroups();
  const boxes = [...document.querySelectorAll('.group-choice:not(:disabled)')];
  if (!boxes.some(b => b.checked)) {
    boxes.forEach((b, idx) => { b.checked = idx < maxGroupsPerBatch; });
    updateSelectAll();
  }
  notice(r.imported_count ? `Đã thêm ${r.imported_count} nhóm mới.` : 'Không có nhóm mới (các nhóm đã có sẵn hoặc link chưa đúng dạng facebook.com/groups/...).', r.imported_count ? 'success' : 'warn');
});

$('create').onclick = busy($('create'), async () => {
  if (!preview) throw new InputIssueError('Hãy chọn tin ở bước 2 trước.', 'listings');
  const groupIds = [...document.querySelectorAll('.group-choice:checked')].map(e => e.value);
  if (!groupIds.length) throw new InputIssueError('Hãy chọn ít nhất một nhóm để đăng.', 'groups', 'Tích chọn nhóm bên dưới hoặc mở phần Thêm nhóm Facebook để bổ sung nhóm.');
  if (groupIds.length > maxGroupsPerBatch) throw new InputIssueError(`Mỗi đợt chỉ đăng tối đa ${maxGroupsPerBatch} nhóm trong hàng chờ.`, 'groups');
  if (!$('content').value.trim()) throw new InputIssueError('Nội dung bài đăng đang trống.', 'content');
  if (!$('reviewed').checked) throw new InputIssueError('Hãy đọc lại bài và tích vào ô “Tôi đã đọc lại nội dung...” trước khi tiếp tục.', 'reviewed');
  const minimum = Number($('min-delay').value), maximum = Number($('max-delay').value);
  if (!$('min-delay').value.trim() || !$('max-delay').value.trim() || !Number.isInteger(minimum) || !Number.isInteger(maximum) || minimum < 0 || maximum < minimum || maximum > 3600) throw new InputIssueError('Chọn khoảng nghỉ từ 0 đến 3600 giây; tối đa phải lớn hơn hoặc bằng tối thiểu.', 'min-delay');
  const result = await api('/api/workflow/campaigns', 'POST', {listing_id: preview.listing.id, preview_token: preview.preview_token,
    custom_content: $('content').value, reviewed: true, target_group_ids: groupIds,
    min_delay_seconds: minimum, max_delay_seconds: maximum,
    image_indices: [...document.querySelectorAll('.photo-choice:checked')].map(e => Number(e.value))});
  await history(result.campaign.id);
  $('step-4').scrollIntoView({behavior: 'smooth', block: 'start'});
  notice(result.campaign.source_mode === 'mock'
    ? 'Đây là đợt xem thử bằng DỮ LIỆU MẪU nên nút “Bắt đầu đăng” bị khóa (không gửi lên Facebook). Hãy tự soạn tin ở Bước 2 để đăng thật.'
    : `Đã lưu đợt đăng cho ${groupIds.length} nhóm. Bấm “Bắt đầu đăng” ở bước 4 để gửi bài.`,
    result.campaign.source_mode === 'mock' ? 'warn' : 'success');
}, updateCreateButton);

/* ---------- Bước 4: đăng & theo dõi ---------- */
async function history(selected) {
  const rows = await api('/api/campaigns');
  const id = selected || campaign?.id || $('campaigns').value;
  $('campaigns').replaceChildren();
  node('option', rows.length ? '— Chọn đợt đăng —' : 'Chưa có đợt đăng', $('campaigns')).value = '';
  for (const r of rows) {
    node('option', `${formatTime(r.created_at)} · ${r.listing_title} · ${campaignLabels[r.status] || r.status}`, $('campaigns')).value = r.id;
  }
  if (id && rows.some(r => r.id === id)) { $('campaigns').value = id; await selectCampaign(); }
  else if (!id && rows.length) { $('campaigns').value = rows[0].id; await selectCampaign(); }
}

async function selectCampaign() {
  clearTimeout(poll);
  const id = $('campaigns').value;
  if (!id) { campaign = null; renderCampaign(); return; }
  campaign = await api('/api/campaigns/' + encodeURIComponent(id));
  renderCampaign();
 
  if (['running', 'queued'].includes(campaign.status)) poll = setTimeout(() => selectCampaign().catch(e => notice(e, 'error')), 1500);
}

function updateCampaignButtons() {
  const c = campaign;
  const running = c && ['running', 'queued'].includes(c.status);
  const checkable = c?.tasks.some(t => t.post_url || ['unknown', 'pending_approval'].includes(t.status));
  const hasPending = c?.tasks.some(t => t.status === 'pending');
  const live = c?.source_mode === 'live';
  $('execute').disabled = !c || running || !live || !hasPending;
  if ($('auto-check')) {
    $('auto-check').hidden = !(c && live && checkable);
    $('auto-check').disabled = running;
    $('auto-check').className = 'secondary';
    $('auto-check').textContent = 'Kiểm tra kết quả & các link đã đăng';
  }
  $('retry').disabled = !c || running || !live || !c.tasks.some(t => ['failed', 'action_required', 'unknown'].includes(t.status));
  $('retry').textContent = 'Đăng lại nhóm lỗi / chưa rõ kết quả';
  $('export-posts').disabled = !c;

}

function renderCampaign() {
  $('tasks').replaceChildren(); $('campaign-chips').replaceChildren(); $('campaign-status').textContent = '';
  const mockWarn = $('mock-step4-warning');
  mockWarn.replaceChildren(); mockWarn.hidden = true;
  updateCampaignButtons(); updateStepper();
  $('view-leads').hidden = !campaign;
  if (campaign) $('view-leads').href = '/leads?campaign_id=' + encodeURIComponent(campaign.id);
  if (!campaign) { node('div', 'Chưa có đợt đăng. Hoàn thành bước 3 để tạo.', $('tasks'), 'empty'); return; }
  if (campaign.source_mode === 'mock') {
    mockWarn.hidden = false;
    node('strong', '⚠ Tại sao nút “Bắt đầu đăng” bị khóa? ', mockWarn);
    node('span', 'Vì đợt đăng này đang dùng “DỮ LIỆU MẪU” (chỉ để xem thử giao diện, hệ thống chặn gửi tin giả lên nhóm Facebook thật). Để đăng bài thật vào nhóm của bạn, bấm nút bên cạnh: ', mockWarn);
    const fixBtn = node('button', 'Tự soạn tin thật để đăng ngay', mockWarn, 'small');
    fixBtn.type = 'button'; fixBtn.style.marginLeft = '6px';
    fixBtn.onclick = () => switchToManualCompose('', '');
  }
  const status = $('campaign-status');
  status.textContent = (campaign.source_mode === 'mock' ? '[TIN MẪU — không gửi Facebook] ' : '') +
    'Trạng thái: ' + (campaignLabels[campaign.status] || campaign.status) + (campaign.error_message ? ' — ' + campaign.error_message : '');
  if (campaign.min_delay_seconds != null && campaign.max_delay_seconds != null) node('p', `Đăng lần lượt · Nghỉ giữa hai nhóm: ${campaign.min_delay_seconds}–${campaign.max_delay_seconds} giây`, status, 'hint');
  const counts = {};
  for (const t of campaign.tasks) counts[t.status] = (counts[t.status] || 0) + 1;
  for (const [key, n] of Object.entries(counts)) node('span', `${taskLabels[key] || key}: ${n}`, $('campaign-chips'), 'badge ' + key);
  if (campaign.tasks.some(t => t.status === 'unknown')) {
    node('p', 'Có nhóm chưa rõ kết quả. Bạn vẫn có thể đăng tiếp nhóm chưa đăng hoặc chủ động bấm đăng lại nhóm lỗi / chưa rõ; kiểm tra kết quả là thao tác riêng.', $('tasks'), 'hint');
  }
  for (const t of campaign.tasks) {
    const box = node('div', undefined, $('tasks'), 'task');
    box.dataset.taskId = t.task_id;
    const head = node('div', undefined, box, 'task-head');
    node('strong', t.group_name, head);
    const unavailable = t.status === 'posted' && t.post_check_status === 'unavailable';
    node('span', unavailable ? 'Đã đăng · hiện không hiển thị' : taskLabels[t.status] || t.status,
      head, 'badge ' + (unavailable ? 'failed' : t.status));
    if (taskHelp[t.status]) node('p', taskHelp[t.status], box, 'hint');
    if (t.error_message) node('p', t.error_message, box);
    const links = node('div', undefined, box, 'links');
    safeLink(links, 'Mở nhóm ↗', t.group_url);
    if (t.post_url) safeLink(links, 'Mở bài đã đăng ↗', t.post_url);
    if (t.post_url && campaign.source_mode === 'live') {
      const check = node('button', 'Kiểm tra link bài này', links, 'small secondary');
      check.disabled = ['running', 'queued'].includes(campaign.status);
      check.onclick = busy(check, async () => {
        await api(`/api/campaigns/${campaign.id}/auto-check`, 'POST', {task_id: t.task_id, continue_pending: false});
        await selectCampaign();
        notice('Đang kiểm tra link bài đã lưu; thao tác này không đăng bài.', 'info');
      }, updateCampaignButtons);
      if (t.post_check_status && t.post_check_status !== 'unchecked') {
        node('p', `${postCheckLabels[t.post_check_status]} · ${formatTime(t.post_checked_at)} — ${t.post_check_message || ''}`, box, 'hint');
      }
    }
    if (t.status === 'posted' && t.post_url && t.evidence && campaign.source_mode === 'live') {
      safeLink(links, 'Lọc comment tại tab Khách hàng →', '/leads?campaign_id=' + encodeURIComponent(campaign.id) + '&posting_task_id=' + encodeURIComponent(t.task_id));
    }
    if (['unknown', 'pending_approval'].includes(t.status)) {
      if (campaign.source_mode === 'live') {
        const autoBtn = node('button', 'Tự kiểm tra trên Facebook', links, 'small');
        autoBtn.type = 'button';
        autoBtn.disabled = ['running', 'queued'].includes(campaign.status);
        autoBtn.onclick = busy(autoBtn, async () => {
          notice(`Đang tự kiểm tra bài đăng trên nhóm “${t.group_name}”...`, 'info');
          await api(`/api/campaigns/${campaign.id}/auto-check`, 'POST', {task_id: t.task_id, continue_pending: false});
          await selectCampaign();
        }, updateCampaignButtons);
      }
      const d = node('details', undefined, box);
      node('summary', 'Hoặc xác nhận thủ công (chỉ khi cần)', d);
      const label = node('label', 'Link bài viết trong nhóm (bắt buộc nếu bài đã lên)', d);
      const input = node('input', undefined, label); input.type = 'url'; input.placeholder = 'https://www.facebook.com/groups/.../posts/...';
      const row = node('div', undefined, d, 'actions');
      for (const [outcome, title, cls] of [['posted', 'Bài đã lên nhóm', ''], ['pending_approval', 'Đang chờ admin duyệt', 'secondary'], ['not_submitted', 'Bài chưa được gửi', 'secondary']]) {
        if (outcome === 'pending_approval' && t.status === 'pending_approval') continue;
        const b = node('button', title, row, cls + ' small');
        b.onclick = busy(b, async () => {
          if (outcome === 'posted' && !input.value.trim()) throw new InputIssueError('Hãy dán link bài viết trong nhóm để xác nhận bài đã lên.', input);
          if (!confirm(`Xác nhận “${title}” cho nhóm “${t.group_name}”?\nChỉ xác nhận khi bạn đã tự kiểm tra trên Facebook.`)) return;
          await api(`/api/campaigns/${campaign.id}/tasks/${t.task_id}/resolve`, 'POST', {outcome, post_url: input.value.trim() || null, confirmed: true});
          await selectCampaign();
          notice('Đã cập nhật kết quả.', 'success');
        });
      }
    }
  }
}

$('campaigns').onchange = () => selectCampaign().catch(e => notice(e, 'error'));
$('refresh').onclick = busy($('refresh'), () => history(), updateCampaignButtons);
for (const [id, action] of [['execute', 'execute'], ['retry', 'retry']]) {
  $(id).onclick = busy($(id), async () => {
    const current = campaign;
    if (!current) throw new InputIssueError('Hãy chọn một đợt đăng.', 'campaigns');
    const n = current.tasks.filter(t => action === 'retry' ? ['failed', 'action_required', 'unknown'].includes(t.status) : t.status === 'pending').length;
    const warnLogin = fb.status?.is_authenticated ? '' : '\n\nLưu ý: tool chưa xác nhận bạn đã đăng nhập Facebook. Nếu chưa, hãy bấm Hủy và đăng nhập trước.';
    if (!confirm(`Đăng bài lên ${n} nhóm ${action === 'retry' ? 'bị lỗi / chưa rõ kết quả' : 'chưa đăng'} của đợt này?\nGiữ máy và cửa sổ tool mở trong lúc đăng.` + warnLogin)) return;
    await api(`/api/campaigns/${current.id}/${action}`, 'POST');
    notice('Đang đăng bài. Theo dõi kết quả từng nhóm bên dưới.', 'info');
    await selectCampaign();
  }, updateCampaignButtons);
}
if ($('auto-check')) {
  $('auto-check').onclick = busy($('auto-check'), async () => {
    const current = campaign;
    if (!current) throw new InputIssueError('Hãy chọn một đợt đăng.', 'campaigns');
    notice('Đang kiểm tra kết quả và các link bài đã lưu. Thao tác này không đăng bài.', 'info');
    await api(`/api/campaigns/${current.id}/auto-check`, 'POST', {continue_pending: false});
    await selectCampaign();
  }, updateCampaignButtons);
}
$('export-posts').onclick = () => { if (campaign) downloadUrl('/api/exports/campaigns?campaign_id=' + encodeURIComponent(campaign.id), 'ket_qua_dang_bai.xlsx'); };

/* ---------- Cài đặt ---------- */
async function loadSettings() {
  const cfg = await api('/api/config');
  maxGroupsPerBatch = Math.min(100, Math.max(1, Number(cfg.max_groups_per_batch || 100)));
  if ($('max-groups')) $('max-groups').value = maxGroupsPerBatch;
  $('min-delay').value = cfg.min_delay_seconds; $('max-delay').value = cfg.max_delay_seconds;
  updateSelectAll();
}
$('save-settings').onclick = busy($('save-settings'), async () => {
  const maxGroups = Number($('max-groups') ? $('max-groups').value : 100);
  const min = Number($('min-delay').value), max = Number($('max-delay').value);
  if (!Number.isInteger(maxGroups) || maxGroups < 1 || maxGroups > 100) throw new InputIssueError('Số nhóm tối đa mỗi đợt phải từ 1 đến 100 nhóm.', 'max-groups');
  if (!(min >= 0 && max >= min && max <= 3600)) throw new InputIssueError('Nghỉ tối thiểu phải ≥ 0 và không lớn hơn nghỉ tối đa (tối đa 3600 giây).', min < 0 ? 'min-delay' : 'max-delay');
  await api('/api/config', 'POST', {max_groups_per_batch: maxGroups, min_delay_seconds: min, max_delay_seconds: max});
  await loadSettings();
  maxGroupsPerBatch = maxGroups;
  const checked = [...document.querySelectorAll('.group-choice:not(:disabled):checked')];
  if (checked.length > maxGroupsPerBatch) {
    checked.slice(maxGroupsPerBatch).forEach(b => { b.checked = false; });
  }
  updateSelectAll();
  notice('Đã lưu cài đặt.', 'success');
});
if (location.hash === '#settings') $('settings').open = true;
window.addEventListener('hashchange', () => { if (location.hash === '#settings') { $('settings').open = true; closeMenus(); } });

async function init() {
  try { await loadSettings(); await loadListings(); await loadQuinlandCatalog(); await loadGroups(); await history(); }
  catch (e) { notice(e, 'error'); }
  updateStepper();
}
init();
