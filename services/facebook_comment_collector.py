"""Bounded, read-only collection from one Facebook post in the customer's session."""
import hashlib
import re
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from services.facebook_browser import authenticated, launch_context


def normalize_post_url(value, *, allow_share=True):
    parts = urlsplit(value.strip())
    if (parts.scheme != 'https' or parts.hostname not in
            ('facebook.com', 'www.facebook.com', 'm.facebook.com') or parts.port not in (None, 443)
            or parts.username or parts.password):
        raise ValueError('Nhập URL HTTPS của một bài viết trên facebook.com.')
    path = parts.path.rstrip('/')
    query = parse_qs(parts.query)
    if (allow_share and re.fullmatch(r'/share/(?:p/)?[A-Za-z0-9_-]+', path)
            and path not in ('/share/p', '/share/r', '/share/v')):
        pass
    elif re.fullmatch(r'/groups/[A-Za-z0-9._-]+/(?:posts|permalink)/[A-Za-z0-9._-]+', path):
        pass
    elif re.fullmatch(r'/[A-Za-z0-9._-]+/posts/[A-Za-z0-9._-]+', path):
        pass
    elif path in ('/permalink.php', '/story.php') and query.get('story_fbid') and query.get('id'):
        return 'https://www.facebook.com' + path + '?' + urlencode({
            'story_fbid': query['story_fbid'][0], 'id': query['id'][0]})
    else:
        raise ValueError('Nhập link chia sẻ bài viết /share/... hoặc link bài trực tiếp /posts/..., /groups/.../posts/... hay permalink.php?story_fbid=...&id=... .')
    return 'https://www.facebook.com' + path


def resolve_post_url(page):
    """Resolve a share from its redirect or page metadata, never feed links."""
    try:
        return normalize_post_url(page.url, allow_share=False)
    except ValueError:
        pass
    candidates = page.locator('link[rel="canonical"], meta[property="og:url"]').evaluate_all(
        "nodes => nodes.map(e => e.getAttribute('href') || e.getAttribute('content'))")
    urls = set()
    for candidate in candidates:
        if not candidate:
            continue
        try:
            urls.add(normalize_post_url(urljoin(page.url, candidate), allow_share=False))
        except ValueError:
            continue
    return next(iter(urls)) if len(urls) == 1 else None


# Only accept articles with a comment permalink tied to this post. Do not read
# suggested posts, the main post body or a site's private network endpoints.
EXTRACT_COMMENTS = r"""(root, target) => {
  const key = value => {
    try {
      const u = new URL(value, location.href);
      if (!['facebook.com','www.facebook.com','m.facebook.com'].includes(u.hostname)) return '';
      return u.searchParams.get('story_fbid') || u.pathname.match(/\/(?:posts|permalink)\/([^/]+)/)?.[1] || '';
    } catch { return ''; }
  };
  const targetKey = key(target);
  const rows = [];
  for (const article of root.querySelectorAll('[role="article"]')) {
    if (!article.getClientRects().length) continue;
    const links = [...article.querySelectorAll('a[href]')].filter(a => a.closest('[role="article"]') === article);
    const permalink = links.find(a => {
      const u = new URL(a.href, location.href);
      return (u.searchParams.has('comment_id') || u.searchParams.has('reply_comment_id')) && key(a.href) === targetKey;
    });
    if (!permalink) continue;
    const author = links.find(a => {
      if (a === permalink || !a.innerText.trim() || /[?&](comment_id|reply_comment_id)=/.test(a.href) || a.closest('[data-ad-comet-preview="message"]')) return false;
      const u = new URL(a.href, location.href);
      return ['facebook.com','www.facebook.com','m.facebook.com'].includes(u.hostname) &&
        (/^\/(?:profile\.php|people\/[^/]+\/[^/]+\/?|groups\/[^/]+\/user\/[^/]+\/?|[^/]+\/?)$/.test(u.pathname)) &&
        !/^\/(?:photo|photos|watch|reel|share|groups)\/?$/.test(u.pathname);
    });
    const own = e => e.closest('[role="article"]') === article && e.getClientRects().length;
    const anonymous = /^(?:anonymous (?:participant|member|user)|người (?:tham gia|dùng) ẩn danh|thành viên ẩn danh)(?:\s+\d+)?$/i;
    const labels = [...article.querySelectorAll('[data-author-name],[data-ad-rendering-role="profile_name"],[data-testid="comment-author"],h3,span,strong')]
      .filter(e => own(e) && !e.closest('[data-ad-comet-preview="message"]'));
    const authorLabel = labels.find(e => anonymous.test(e.innerText.trim())) ||
      labels.find(e => e.hasAttribute('data-author-name') || e.hasAttribute('data-ad-rendering-role') || e.hasAttribute('data-testid') || e.tagName === 'H3') || author;
    const authorName = authorLabel?.innerText.trim() || 'Chưa xác định tác giả';
    const identityStatus = anonymous.test(authorName) ? 'anonymous' : (authorLabel ? 'known' : 'unknown');
    const explicit = article.querySelector('[data-ad-comet-preview="message"]');
    let text = explicit && explicit.getClientRects().length && explicit.closest('[role="article"]') === article ? explicit.innerText.trim() : '';
    if (!text) {
      text = [...article.querySelectorAll('[dir="auto"]')]
        .filter(e => e.getClientRects().length && e.closest('[role="article"]') === article && !e.closest('a,button,[role="button"]') &&
          !e.querySelector('[dir="auto"]') && !e.isContentEditable && e !== authorLabel && !authorLabel?.contains(e))
        .map(e => e.innerText.trim()).filter(Boolean).join('\n');
    }
    if (!text || text.length > 20000) continue;
    const url = new URL(permalink.href);
    const cid = url.searchParams.get('reply_comment_id') || url.searchParams.get('comment_id');
    const truncated = [...article.querySelectorAll('button,[role="button"]')].some(e =>
      e.closest('[role="article"]') === article && e.getClientRects().length && /^(See more|Xem thêm)$/i.test(e.innerText.trim()));
    rows.push({id: cid, fb_user_name: authorName, identity_status: identityStatus, raw_content: text, text_truncated: truncated,
      source_url: target, comment_url: permalink.href, fb_user_url: identityStatus === 'known' && author ? author.href : null});
  }
  return rows;
}"""


class CollectionDeadline(Exception):
    pass


class FacebookCommentCollector:
    def __init__(self, profile_dir, timeout_seconds=300, max_rounds=None):
        self.profile_dir = profile_dir
        self.timeout_seconds = min(float(timeout_seconds), 300.0)
        if self.timeout_seconds <= 0:
            raise ValueError('Thời gian lấy bình luận phải lớn hơn 0.')
        self.max_rounds = max_rounds

    def collect(self, post_url, limit, stop, progress):
        """Caller owns the shared profile lock; progress persists partial results."""
        records = {}
        deadline = time.monotonic() + self.timeout_seconds

        def budget(maximum=1500):
            remaining = (deadline - time.monotonic()) * 1000
            if remaining <= 0:
                raise CollectionDeadline()
            return max(1, min(maximum, remaining))

        def pause(milliseconds):
            page.wait_for_timeout(budget(milliseconds))
            budget()

        def timed_out():
            label = '5 phút' if self.timeout_seconds == 300 else f'{self.timeout_seconds:g} giây'
            return ('stopped' if stop.is_set() else 'partial', list(records.values()),
                    f'Đã hết thời gian tối đa {label} cho bài này; giữ {len(records)} bình luận đã lấy. Chưa xác nhận lấy đủ.')

        with sync_playwright() as playwright:
            context = launch_context(playwright, self.profile_dir, False)
            try:
                page = context.new_page()
                page.set_default_timeout(budget())
                # Stop redirects/links to non-Facebook origins in the main frame.
                def navigation(route):
                    req = route.request
                    if req.is_navigation_request() and req.frame == page.main_frame:
                        host = urlsplit(req.url).hostname or ''
                        if host not in ('facebook.com', 'www.facebook.com', 'm.facebook.com'):
                            return route.abort()
                    return route.fallback()
                page.route('**/*', navigation)
                page.goto(post_url, wait_until='domcontentloaded', timeout=budget(45000))
                pause(2000)
                stale = 0
                sorted_all = False
                target_url = None
                rounds = 0
                while self.max_rounds is None or rounds < self.max_rounds:
                    rounds += 1
                    if stop.is_set():
                        return 'stopped', list(records.values()), 'Đã dừng theo yêu cầu; giữ các bình luận đã lấy.'
                    page.set_default_timeout(budget())
                    if not authenticated(page, context):
                        return 'action_required', list(records.values()), 'Cần đăng nhập/xác minh Facebook. Hoàn tất đăng nhập rồi chạy lại.'
                    if page.get_by_text(re.compile(r"^(This content isn't available|This content isn't available right now|Nội dung này hiện không hiển thị|Bạn hiện không xem được nội dung này)", re.I)).count():
                        return 'action_required', list(records.values()), 'Không truy cập được bài viết bằng tài khoản hiện tại.'
                    if target_url is None:
                        target_url = resolve_post_url(page)
                        if target_url is None:
                            budget()
                            pause(1000)
                            continue
                    # Post dialogs isolate the discussion from the background feed.
                    dialogs = page.locator('[role="dialog"]').filter(has=page.locator('[role="article"]'))
                    scope = next((dialogs.nth(i) for i in range(dialogs.count()) if dialogs.nth(i).is_visible()), page.locator('body'))
                    if not sorted_all:
                        sort = scope.get_by_role('button', name=re.compile(r'^(Most relevant|Phù hợp nhất|Liên quan nhất|Newest|Mới nhất)$', re.I))
                        if sort.count() and sort.first.is_visible():
                            sort.first.click(timeout=budget())
                            all_comments = page.get_by_role('menuitem', name=re.compile(r'^(All comments|Tất cả bình luận)$', re.I))
                            if all_comments.count() and all_comments.first.is_visible():
                                all_comments.first.click(timeout=budget())
                            else:
                                page.keyboard.press('Escape')
                        sorted_all = True
                    before = len(records)
                    # Expand text before enforcing the comment limit; otherwise
                    # the first batch could be classified from truncated text.
                    expanders = scope.get_by_role('button', name=re.compile(r'^(See more|Xem thêm)$', re.I))
                    had_expanders = bool(expanders.count())
                    for control in expanders.all()[:12]:
                        if control.is_visible():
                            control.click(timeout=budget())
                    if had_expanders:
                        pause(200)
                    budget()
                    for row in scope.evaluate(EXTRACT_COMMENTS, target_url):
                        identity = row['id'] or hashlib.sha256(((row.get('fb_user_url') or '') + row['raw_content']).encode()).hexdigest()
                        row['id'] = identity
                        records[identity] = row
                        if len(records) >= limit:
                            break
                    progress(list(records.values()))
                    if len(records) >= limit:
                        return 'partial', list(records.values()), f'Đã đạt giới hạn {limit} bình luận; chưa xác nhận đã lấy toàn bộ.'
                    budget()
                    stale = stale + 1 if len(records) == before else 0
                    if stale >= 4:
                        break
                    # Only expand read controls. Never click Like, Reply or Submit.
                    controls = scope.get_by_role('button', name=re.compile(
                        r'^(View (?:more|previous) comments|See more comments|View \d+ (?:more )?(?:comments|replies)|'
                        r'View (?:more|previous) replies|See more|Xem thêm|Xem (?:thêm|các) bình luận(?: trước)?|'
                        r'Xem (?:thêm )?\d+ (?:bình luận|phản hồi)|Xem (?:thêm|các) (?:câu trả lời|phản hồi))$', re.I))
                    for index in range(min(controls.count(), 8)):
                        control = controls.nth(index)
                        if control.is_visible():
                            control.click(timeout=budget())
                            break
                    # Scroll the discussion rather than only the background feed.
                    scope.evaluate("e => {const a=[e,...e.querySelectorAll('*')].filter(x=>x.scrollHeight>x.clientHeight+100 && ['auto','scroll'].includes(getComputedStyle(x).overflowY)); const s=a.sort((x,y)=>y.clientHeight-x.clientHeight)[0]; if(s)s.scrollTop+=600;else window.scrollBy(0,600);}")
                    pause(1000)
                if target_url is None:
                    return 'action_required', [], 'Chưa mở được bài gốc từ link chia sẻ. Kiểm tra link còn hoạt động và tài khoản có quyền xem bài, rồi thử lại.'
                if not records:
                    return 'action_required', [], 'Chưa nhận diện được bình luận. Bài có thể không có bình luận, bị giới hạn hoặc giao diện Facebook đã đổi; không coi là đã lấy đủ.'
                return 'partial', list(records.values()), 'Đã lấy các bình luận nhận diện được. Facebook có thể ẩn/xếp hạng bình luận; chưa xác nhận đã lấy toàn bộ.'
            except CollectionDeadline:
                return timed_out()
            except PlaywrightTimeoutError:
                if time.monotonic() >= deadline:
                    return timed_out()
                raise
            finally:
                context.close()
