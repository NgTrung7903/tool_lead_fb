'use strict';
/* Hàm dùng chung cho các trang giao diện: gọi API, thông báo, nút đang xử lý, trạng thái Facebook. */
const $ = id => document.getElementById(id);

function node(tag, text, parent, cls) {
  const e = document.createElement(tag);
  if (text !== undefined && text !== null) e.textContent = text;
  if (cls) e.className = cls;
  parent?.append(e);
  return e;
}

class InputIssueError extends Error {
  constructor(message, target = null, hint = '') {
    super(message); this.target = target; this.hint = hint;
  }
}
let activeInputIssue = null, errorFocusVersion = 0;
function clearInputIssue() {
  errorFocusVersion++;
  if (!activeInputIssue) return;
  const {target, note, invalid, described, tab} = activeInputIssue;
  target.classList.remove('input-issue-focus'); note.remove();
  for (const [name, value] of [['aria-invalid', invalid], ['aria-describedby', described], ['tabindex', tab]]) {
    if (value === null) target.removeAttribute(name); else target.setAttribute(name, value);
  }
  activeInputIssue = null;
}
function focusInputIssue(error) {
  const target = typeof error.target === 'string' ? $(error.target) : error.target;
  if (!target || !target.isConnected) return false;
  for (let parent = target.parentElement; parent; parent = parent.parentElement) {
    if (parent.tagName === 'DETAILS') parent.open = true;
  }
  const note = document.createElement('p');
  note.id = 'active-input-issue'; note.className = 'input-issue-message'; note.setAttribute('role', 'alert');
  note.textContent = error.message + (error.hint ? ' ' + error.hint : '');
  activeInputIssue = {target, note, invalid: target.getAttribute('aria-invalid'),
    described: target.getAttribute('aria-describedby'), tab: target.getAttribute('tabindex')};
  const label = target.closest('label');
  (label || target).insertAdjacentElement('afterend', note);
  target.classList.add('input-issue-focus'); target.setAttribute('aria-invalid', 'true');
  target.setAttribute('aria-describedby', [activeInputIssue.described, note.id].filter(Boolean).join(' '));
  if (!target.matches('input,select,textarea,button,a[href],[tabindex]')) target.tabIndex = -1;
  const version = errorFocusVersion;
  // Wait until busy() has re-enabled the initiating button before focusing it.
  requestAnimationFrame(() => {
    if (version !== errorFocusVersion || !target.isConnected) return;
    target.scrollIntoView({behavior: 'smooth', block: 'center'});
    target.focus({preventScroll: true});
  });
  return true;
}
document.addEventListener('input', event => {
  if (activeInputIssue?.target.contains(event.target)) clearInputIssue();
});
document.addEventListener('change', event => {
  if (activeInputIssue?.target.contains(event.target)) clearInputIssue();
});
/** A located error moves directly to the input and explains the fix beside it. */
function notice(value = '', type = 'info') {
  const box = $('notice');
  if (!box) return;
  clearInputIssue();
  const error = value instanceof Error ? value : null;
  const message = error ? error.message : String(value || '');
  box.textContent = message; box.className = message ? type : '';
  if (message && type === 'error' && !focusInputIssue(error || {})) {
    box.scrollIntoView({behavior: 'smooth', block: 'center'});
  }
}
function issueTarget(field, path) {
  if (path.startsWith('/api/sources/json') && ['data', 'filename'].includes(field)) return 'post-json';
  if (path.startsWith('/api/sources/import') && field === 'url') return 'source-url';
  if (path.startsWith('/api/sources/quinland') && field === 'record_ids') return 'quinland-select';
  if (path.startsWith('/api/sources/manual')) return ({title: 'manual-title', description: 'manual-desc',
    area_m2: 'manual-area', price_text: 'manual-price', location: 'manual-location', images_base64: 'manual-photos'})[field];
  if (path.startsWith('/api/groups')) return ({name: 'group-name', group_url: 'group-url', raw_text: 'bulk-groups'})[field];
  return ({listing_id: 'listings', preview_token: 'listings', custom_content: 'content', reviewed: 'reviewed',
    target_group_ids: 'groups', group_url: 'groups', image_indices: 'photos', campaign_id: 'campaigns',
    facebook_session: 'login', source_url: 'source-url', saved_ids: 'saved-delete-list',
    max_groups_per_batch: 'max-groups', min_delay_seconds: 'min-delay', max_delay_seconds: 'max-delay',
    limit: path.startsWith('/api/workflow/') ? 'comment-limit' : 'limit'})[field];
}
async function api(path, method = 'GET', data, context = {}) {
  let response;
  try {
    response = await fetch(path, {method, headers: {'Content-Type': 'application/json', 'X-Revoland-Client': 'local'},
      ...(data === undefined ? {} : {body: JSON.stringify(data)})});
  } catch {
    throw new Error('Không kết nối được với tool. Hãy kiểm tra cửa sổ chạy tool (màn hình đen) vẫn còn mở, rồi tải lại trang.');
  }
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const issue = (err.issues || [])[0];
    let message = typeof err.detail === 'string' ? err.detail : 'Thông tin nhập chưa hợp lệ. Vui lòng kiểm tra lại các ô đã điền.';
    if (issue) {
      message = issue.message || message;
      const location = issue.location || [];
      if (issue.field === 'data' && location[0] === 'data' && Number.isInteger(location[1])) {
        const row = context.sourceRows?.[location[1]] ?? location[1];
        const field = location.slice(2).map(part => Number.isInteger(part) ? `[${part}]` : `.${part}`).join('').replace(/^\./, '');
        message = `Bài ${row + 1}${field ? ' · trường ' + field : ''}: ` + message.replace(/^Bài \d+:\s*/, '');
      }
      throw new InputIssueError(message, issueTarget(issue.field, path), issue.hint || '');
    }
    throw new Error(message);
  }
  return response.json();
}

/** Bọc thao tác của nút: khóa nút + hiệu ứng đang xử lý, báo lỗi dễ hiểu.
 *  after(): chạy sau khi mở khóa nút, dùng để tính lại trạng thái bật/tắt theo dữ liệu. */
function busy(button, action, after) {
  return async event => {
    event?.preventDefault();
    if (button.disabled) return;
    button.disabled = true;
    button.classList.add('loading');
    try { await action(event); }
    catch (err) { notice(err, 'error'); }
    finally { button.classList.remove('loading'); button.disabled = false; after?.(); }
  };
}

function safeLink(parent, label, url, cls) {
  try {
    const u = new URL(url, location.href);
    if (!['http:', 'https:'].includes(u.protocol)) return null;
    const a = node('a', label, parent, cls);
    a.href = u.href;
    if (u.origin !== location.origin) { a.target = '_blank'; a.rel = 'noopener noreferrer'; }
    return a;
  } catch { return null; }
}

function downloadUrl(url, filename) {
  const a = document.createElement('a');
  a.href = url; a.download = filename; document.body.append(a); a.click(); a.remove();
}

function formatTime(value) {
  try { return new Date(value).toLocaleString('vi-VN', {hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', year: 'numeric'}); }
  catch { return value || ''; }
}

/* ---------- Trạng thái kết nối Facebook (thanh trên cùng) ---------- */
const fb = {status: null, poll: null, waitingLogin: false};

function renderSession(s) {
  fb.status = s;
  const saved = /lưu|Kiểm tra/.test(s.status_text || '');
  const pill = $('session-status');
  if (pill) {
    pill.textContent = s.status_text;
    pill.className = 'pill ' + (s.login_in_progress || s.busy ? 'busy' : s.is_authenticated ? 'ok' : saved ? 'warn' : 'bad');
  }
  const quickCheck = $('quick-check');
  if (quickCheck) quickCheck.hidden = !saved || !!s.login_in_progress || !!s.busy;
  const login = $('login');
  if (login) {
    login.hidden = !!s.is_authenticated;
    login.disabled = !!s.login_in_progress;
    login.className = saved ? 'secondary small' : 'small';
    login.textContent = s.login_in_progress ? 'Đang chờ đăng nhập...' : saved ? 'Đăng nhập lại' : 'Đăng nhập Facebook';
  }
  window.dispatchEvent(new CustomEvent('fb-session', {detail: s}));
}

async function quickSession() {
  const s = await api('/api/session/status?quick=true');
  renderSession(s);
  clearTimeout(fb.poll);
  if (s.login_in_progress) {
    fb.waitingLogin = true;
    fb.poll = setTimeout(() => quickSession().catch(() => {}), 2500);
  } else if (fb.waitingLogin) {
    fb.waitingLogin = false;
    const r = s.login_result;
    if (r) notice(r.success ? 'Đăng nhập Facebook thành công. Bạn có thể tiếp tục.' : r.message, r.success ? 'success' : 'warn');
  }
  return s;
}

function initSessionWidget() {
  const login = $('login'), check = $('check-session'), logout = $('logout');
  if (login) login.onclick = busy(login, async () => {
    await api('/api/session/login', 'POST');
    notice('Đã mở cửa sổ Facebook. Hãy đăng nhập (nhập mật khẩu/mã OTP ngay trên cửa sổ đó). Tool sẽ tự nhận khi bạn đăng nhập xong — tối đa 3 phút.', 'info');
    fb.waitingLogin = true;
    fb.poll = setTimeout(() => quickSession().catch(() => {}), 1500);
  });
  const runCheck = async () => {
    closeMenus();
    renderSession({...(fb.status || {}), status_text: 'Đang kiểm tra kết nối...', busy: true, is_authenticated: false});
    const s = await api('/api/session/status');
    renderSession(s);
    notice(s.is_authenticated ? 'Kết nối Facebook đang hoạt động.' : s.status_text, s.is_authenticated ? 'success' : 'warn');
  };
  if (check) check.onclick = busy(check, runCheck);
  const quickCheck = $('quick-check');
  if (quickCheck) quickCheck.onclick = busy(quickCheck, runCheck);
  if (logout) logout.onclick = busy(logout, async () => {
    closeMenus();
    if (!confirm('Đăng xuất và xóa phiên Facebook đã lưu trên máy này?\nLần sau bạn sẽ cần đăng nhập lại.')) return;
    notice((await api('/api/session/logout', 'POST')).message, 'success');
    await quickSession();
  });
  document.addEventListener('click', e => { if (!e.target.closest('.more')) closeMenus(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMenus(); });
  quickSession().catch(e => notice(e, 'error'));
}

function closeMenus() { document.querySelectorAll('details.more[open]').forEach(d => d.removeAttribute('open')); }

document.addEventListener('DOMContentLoaded', initSessionWidget);
