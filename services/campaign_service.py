from services.input_errors import InputError
"""Durable campaigns, serialized execution, evidence-aware retries."""
import json
from pathlib import Path
import random
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager, closing, nullcontext
import hashlib

from config.settings import RUNTIME_DIR, load_config
from models.schema import GroupPostStatusEnum as S, GroupTaskResult, PostingCampaign, utc_now_iso
from services.group_manager import GroupManager, normalize_group_url
from services.poster_engine import FacebookPosterEngine, post_permalink
from services.revoland_service import RevolandService
from services.storage import ExclusiveOperation, ResourceBusyError

CAMPAIGNS_FILE = RUNTIME_DIR / 'data' / 'campaigns_history.json'
SUCCESS = {S.POSTED, S.PENDING_APPROVAL}
RETRYABLE = {S.FAILED, S.ACTION_REQUIRED}
MAX_GROUPS_PER_BATCH_CAP = 100


class CampaignService:
    def __init__(self, revoland_service=None, group_manager=None, poster_engine=None, db_path=None, recover_on_start=True):
        self.revoland_service = revoland_service or RevolandService()
        self.group_manager = group_manager or GroupManager()
        self.poster_engine = poster_engine or FacebookPosterEngine()
        self.config = load_config()
        self.db_path = Path(db_path or RUNTIME_DIR / 'data' / 'campaigns.sqlite3')
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._runner = threading.Lock()
        self._run_lock_path = self.db_path.with_suffix('.run.lock')
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS campaigns (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        # Do not recover another process's active job.
        try:
            with ExclusiveOperation(self._run_lock_path):
                self._migrate_legacy()
                if recover_on_start:
                    self._recover()
        except ResourceBusyError:
            pass

    @contextmanager
    def _db(self):
        with closing(sqlite3.connect(self.db_path, timeout=15)) as db:
            with db:
                yield db

    def _save(self, campaign):
        with self._db() as db:
            db.execute('INSERT INTO campaigns(id, body) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                       (campaign.id, campaign.model_dump_json()))

    def _migrate_legacy(self):
        with self._db() as db:
            if db.execute("SELECT 1 FROM metadata WHERE key='legacy_import'").fetchone():
                return
            if CAMPAIGNS_FILE.exists() and self.db_path.parent == CAMPAIGNS_FILE.parent:
                for raw in json.loads(CAMPAIGNS_FILE.read_text(encoding='utf-8')):
                    campaign = PostingCampaign(**raw)
                    campaign.source_mode = 'legacy'
                    campaign.status = 'needs_review'
                    for task in campaign.tasks:
                        if task.status in SUCCESS or task.status == S.RUNNING:
                            task.status = S.UNKNOWN
                            task.post_url = None
                            task.error_message = 'Lịch sử cũ có thể là mô phỏng. Khách cần kiểm tra nhóm và xác nhận.'
                            task.evidence = None
                    db.execute('INSERT OR IGNORE INTO campaigns VALUES (?, ?)', (campaign.id, campaign.model_dump_json()))
            db.execute("INSERT INTO metadata VALUES ('legacy_import', 'done')")

    def _recover(self):
        for campaign in self.list_campaigns():
            if campaign.status not in ('running', 'queued'):
                continue
            for task in campaign.tasks:
                if task.status == S.RUNNING:
                    task.status = S.UNKNOWN if task.submission_started else S.FAILED
                    task.error_message = 'Ứng dụng dừng giữa tác vụ. Kiểm tra nhóm trước khi thử lại.' if task.submission_started else 'Ứng dụng dừng trước bước gửi; có thể thử lại.'
            campaign.status = 'interrupted'
            campaign.error_message = 'Lần chạy trước bị gián đoạn. Không tự gửi lại tác vụ chưa rõ kết quả.'
            self._save(campaign)

    def get_campaign(self, campaign_id):
        with self._db() as db:
            row = db.execute('SELECT body FROM campaigns WHERE id=?', (campaign_id,)).fetchone()
        return PostingCampaign.model_validate_json(row[0]) if row else None

    def list_campaigns(self):
        with self._db() as db:
            rows = db.execute('SELECT body FROM campaigns ORDER BY rowid DESC').fetchall()
        return [PostingCampaign.model_validate_json(row[0]) for row in rows]

    def max_groups_per_batch(self) -> int:
        raw = int(self.config.get('max_groups_per_batch', MAX_GROUPS_PER_BATCH_CAP))
        return max(1, min(raw, MAX_GROUPS_PER_BATCH_CAP))

    def create_campaign(self, listing_id, target_group_ids, custom_content=None, preview_token=None,
                        listing_service=None, expected_image_count=None, min_delay_seconds=None, max_delay_seconds=None):
        minimum = self.config.get('min_delay_seconds', 300) if min_delay_seconds is None else min_delay_seconds
        maximum = self.config.get('max_delay_seconds', 300) if max_delay_seconds is None else max_delay_seconds
        if not 0 <= minimum <= maximum <= 3600:
            raise InputError('Khoảng nghỉ cần từ 0 đến 3600 giây; tối đa phải lớn hơn hoặc bằng tối thiểu.', 'max_delay_seconds')
        provider = listing_service if listing_service is not None else self.revoland_service
        if not target_group_ids:
            raise InputError('Chọn ít nhất một nhóm.', 'target_group_ids')
        groups = []
        seen = set()
        for gid in target_group_ids:
            group = self.group_manager.get_group_by_id(gid)
            if not group or group.status != 'active':
                raise InputError('Nhóm không tồn tại hoặc đang tạm dừng: ' + gid, 'target_group_ids', hint='Chọn lại một nhóm đang hoạt động.')
            url = normalize_group_url(group.group_url)
            if url not in seen:
                group.group_url = url
                groups.append(group)
                seen.add(url)
        limit = self.max_groups_per_batch()
        if len(groups) > limit:
            raise InputError(
                f'Mỗi đợt chỉ đăng tối đa {limit} nhóm trong hàng chờ (đang chọn {len(groups)} nhóm).',
                'target_group_ids'
            )
        listing = provider.get_listing_by_id(listing_id)
        if not listing:
            raise InputError('Không tìm thấy tin trong nguồn đã chọn.', 'listing_id')
        if preview_token is not None and preview_token != hashlib.sha256(listing.model_dump_json().encode()).hexdigest():
            raise InputError('Dữ liệu căn đã thay đổi. Hãy tải lại bản xem trước rồi đăng.', 'preview_token', hint='Chọn lại bài để tải dữ liệu mới, sau đó duyệt lại.')
        if listing.status not in ('available', 'published', 'active'):
            raise InputError('Căn không còn ở trạng thái có thể đăng.', 'listing_id')
        content = custom_content if custom_content is not None else provider.format_post_content(listing)
        if not content.strip() or len(content) > 60000:
            raise InputError('Nội dung phải có từ 1 đến 60.000 ký tự.', 'custom_content')
        mode = 'mock' if provider.config.get('revoland_mock_mode', True) else 'live'
        tasks = []
        for group in groups:
            tasks.append(GroupTaskResult(task_id='tsk_' + uuid.uuid4().hex, group_id=group.id,
                group_name=group.name, group_url=group.group_url))
        images = provider.download_listing_images(listing)
        if len(images) != (len(listing.media_urls) if expected_image_count is None else expected_image_count):
            raise InputError('Chưa tải đủ ảnh. Không tạo chiến dịch thiếu ảnh.', 'image_indices')
        campaign = PostingCampaign(id='camp_' + uuid.uuid4().hex, listing_id=listing.id,
            listing_title=listing.title, formatted_content=content, media_urls=images,
            tasks=tasks, total_groups=len(tasks), source_mode=mode,
            min_delay_seconds=minimum, max_delay_seconds=maximum,
            source_url=getattr(listing, 'source_url', None) or listing.revoland_url)
        self._save(campaign)
        return campaign

    @property
    def busy(self):
        return self._runner.locked()

    def start_campaign(self, campaign_id, retry=False):
        if not self._runner.acquire(blocking=False):
            raise ResourceBusyError('Một chiến dịch đang chạy. Hãy đợi hoàn tất.')
        operation = ExclusiveOperation(self._run_lock_path)
        acquired = False
        try:
            operation.__enter__()
            acquired = True
            # Read only after owning both locks. An earlier snapshot may have
            # pending tasks that another request has already finished posting.
            campaign = self._validate_run(campaign_id)
            campaign.status = 'queued'
            self._save(campaign)
            def worker():
                try:
                    self._run(campaign_id, retry, reserved=True)
                except Exception:
                    # _run preserves per-task uncertainty before any external side effect.
                    current = self.get_campaign(campaign_id)
                    for task in current.tasks:
                        if task.status == S.RUNNING:
                            task.status = S.UNKNOWN if task.submission_started else S.FAILED
                            task.error_message = 'Tác vụ bị gián đoạn. Kiểm tra nhóm nếu đã bắt đầu gửi.'
                    current.status = 'interrupted'
                    current.error_message = 'Không hoàn tất chiến dịch. Kiểm tra kết quả từng nhóm trước khi tiếp tục.'
                    self._save(current)
                finally:
                    operation.__exit__(None, None, None)
                    self._runner.release()
            threading.Thread(target=worker, daemon=True, name='posting-campaign').start()
            return campaign
        except Exception:
            if acquired:
                operation.__exit__(None, None, None)
            self._runner.release()
            raise

    def _validate_run(self, campaign_id):
        campaign = self.get_campaign(campaign_id)
        if not campaign:
            raise InputError('Không tìm thấy chiến dịch.', 'campaign_id')
        if campaign.source_mode != 'live':
            raise ValueError('Dữ liệu mẫu/lịch sử cũ chỉ để xem. Chuyển API thật và tạo chiến dịch mới để đăng Facebook.')
        return campaign

    def _begin_task(self, campaign, task):
        if task.status != S.PENDING:
            task.attempt_history.append(task.model_dump(exclude={'attempt_history'}))
        task.status = S.RUNNING
        task.submission_started = False
        task.post_url = task.posted_at = task.evidence = task.error_message = None
        task.post_check_status = 'unchecked'
        task.post_checked_at = task.post_check_message = None
        self._save(campaign)

    def execute_campaign(self, campaign_id):
        self._validate_run(campaign_id)
        if not self._runner.acquire(blocking=False):
            raise ResourceBusyError('Một chiến dịch đang chạy.')
        try:
            return self._run(campaign_id, False)
        finally:
            self._runner.release()

    def retry_failed_tasks(self, campaign_id):
        self._validate_run(campaign_id)
        if not self._runner.acquire(blocking=False):
            raise ResourceBusyError('Một chiến dịch đang chạy.')
        try:
            return self._run(campaign_id, True)
        finally:
            self._runner.release()

    def _apply_task_result(self, campaign, task, result):
        if result.status == S.POSTED and (not result.evidence or not result.post_url or not post_permalink(result.post_url, task.group_url)):
            result.status = S.UNKNOWN
            result.post_url = None
            result.error_message = 'Chưa có đủ bằng chứng bài đã đăng.'
        if result.status == S.PENDING_APPROVAL and not result.evidence:
            result.status = S.UNKNOWN
            result.error_message = 'Chưa có xác nhận bài đang chờ duyệt.'
        if task.submission_started and result.status in (S.FAILED, S.ACTION_REQUIRED):
            result.status = S.UNKNOWN
            result.error_message = 'Đã bắt đầu gửi nhưng chưa xác nhận kết quả. Kiểm tra nhóm trước khi thử lại.'
        task.status, task.post_url = result.status, result.post_url
        task.error_message, task.posted_at = result.error_message, result.posted_at
        task.evidence = result.evidence
        task.submission_started = task.submission_started or result.submission_started
        self._save(campaign)

    def _known_listing_urls(self, listing_id, group_url, exclude_campaign_id=None):
        norm_group = normalize_group_url(group_url)
        urls = set()
        for camp in self.list_campaigns():
            if camp.id == exclude_campaign_id or camp.listing_id != listing_id:
                continue
            for t in camp.tasks:
                if normalize_group_url(t.group_url) == norm_group and t.post_url:
                    urls.add(t.post_url)
        return urls

    def _run(self, campaign_id, retry, reserved=False):
        with nullcontext() if reserved else ExclusiveOperation(self._run_lock_path):
            campaign = self._validate_run(campaign_id)
            campaign.status = 'running'
            campaign.error_message = None
            self._save(campaign)
            eligible = RETRYABLE | {S.UNKNOWN} if retry else RETRYABLE | {S.PENDING}
            batch_limit = self.max_groups_per_batch()
            submitted_in_batch = 0
            for idx, task in enumerate(campaign.tasks):
                if task.status not in eligible:
                    continue
                if submitted_in_batch >= batch_limit:
                    break
                group = self.group_manager.get_group_by_id(task.group_id)
                if not group or group.status != 'active' or normalize_group_url(group.group_url) != normalize_group_url(task.group_url):
                    task.status = S.FAILED
                    task.error_message = 'Nhóm bị xóa, tạm dừng hoặc đổi URL. Chưa gửi bài.'
                    self._save(campaign)
                    continue
                if retry:
                    task.retry_count += 1
                self._begin_task(campaign, task)
                def before_submit():
                    task.submission_started = True
                    self._save(campaign)
                try:
                    result = self.poster_engine.post_to_single_group(
                        task_id=task.task_id, group=group,
                        post_content=campaign.formatted_content, image_paths=campaign.media_urls,
                        before_submit=before_submit,
                    )
                except Exception:
                    result = task.model_copy(update={'status': S.UNKNOWN if task.submission_started else S.FAILED,
                        'error_message': 'Tác vụ bị gián đoạn. Hãy kiểm tra nhóm nếu đã bắt đầu gửi.'})
                submitted_in_batch += 1
                self._apply_task_result(campaign, task, result)
                if task.status == S.ACTION_REQUIRED:
                    break
                has_more = submitted_in_batch < batch_limit and any(
                    t.status in eligible for t in campaign.tasks[idx + 1:]
                )
                if has_more:
                    time.sleep(random.uniform(
                        campaign.min_delay_seconds if campaign.min_delay_seconds is not None else self.config.get('min_delay_seconds', 300),
                        campaign.max_delay_seconds if campaign.max_delay_seconds is not None else self.config.get('max_delay_seconds', 300)))

            self._summarize(campaign)
            self._save(campaign)
            return campaign

    def auto_verify_campaign(self, campaign_id, task_id=None, reserved=False):
        """Check saved links and discover unresolved posts without reposting."""
        with nullcontext() if reserved else ExclusiveOperation(self._run_lock_path):
            campaign = self.get_campaign(campaign_id)
            if not campaign:
                raise InputError('Không tìm thấy chiến dịch.', 'campaign_id')
            if campaign.source_mode != 'live':
                raise ValueError('Chỉ tự động kiểm tra với chiến dịch đăng thật.')
            targets = [
                t for t in campaign.tasks
                if (t.post_url or t.status in (S.UNKNOWN, S.PENDING_APPROVAL)) and (task_id is None or t.task_id == task_id)
            ]
            if not targets:
                self._summarize(campaign)
                self._save(campaign)
                return campaign

            campaign.status = 'running'
            campaign.error_message = None
            self._save(campaign)

            session_cm = (
                self.poster_engine.posting_session(headless=True)
                if isinstance(self.poster_engine, FacebookPosterEngine)
                else nullcontext(None)
            )
            with session_cm as shared_session:
                for task in targets:
                    group = self.group_manager.get_group_by_id(task.group_id)
                    if not group:
                        from models.schema import FBGroup
                        group = FBGroup(id=task.group_id, name=task.group_name, group_url=task.group_url)
                    if task.post_url:
                        from models.schema import FBGroup
                        saved_group = FBGroup(id=task.group_id, name=task.group_name, group_url=task.group_url)
                        checked = self.poster_engine.check_saved_post(
                            task.post_url, saved_group, campaign.formatted_content,
                            headless=True, shared_session=shared_session)
                        task.post_check_status = checked['status']
                        task.post_checked_at = utc_now_iso()
                        task.post_check_message = checked['message']
                        self._save(campaign)
                        continue
                    known_urls = self._known_listing_urls(campaign.listing_id, task.group_url, campaign.id)
                    res = self.poster_engine.auto_verify_group_post(
                        task_id=task.task_id,
                        group=group,
                        post_content=campaign.formatted_content,
                        known_urls=known_urls,
                        headless=True,
                        shared_session=shared_session,
                    )
                    if res.status == S.POSTED and res.post_url and post_permalink(res.post_url, task.group_url):
                        task.status = S.POSTED
                        task.post_url = res.post_url
                        task.posted_at = res.posted_at or utc_now_iso()
                        task.evidence = res.evidence or 'auto_verified'
                        task.error_message = 'Đã tự động xác nhận bài đăng thành công trên nhóm.'
                    elif res.status == S.PENDING_APPROVAL:
                        task.status = S.PENDING_APPROVAL
                        task.posted_at = task.posted_at or res.posted_at or utc_now_iso()
                        task.evidence = res.evidence or 'auto_verified_pending'
                        task.error_message = res.error_message or 'Đã tự xác nhận bài đang chờ admin nhóm duyệt.'
                    else:
                        task.error_message = res.error_message or task.error_message
                    self._save(campaign)

            self._summarize(campaign)
            self._save(campaign)
            return campaign

    def start_auto_verify(self, campaign_id, task_id=None, continue_pending=False):
        if not self._runner.acquire(blocking=False):
            raise ResourceBusyError('Một tác vụ đang chạy. Hãy đợi hoàn tất.')
        operation = ExclusiveOperation(self._run_lock_path)
        acquired = False
        try:
            operation.__enter__()
            acquired = True
            campaign = self.get_campaign(campaign_id)
            if not campaign:
                raise InputError('Không tìm thấy chiến dịch.', 'campaign_id')
            if campaign.source_mode != 'live':
                raise ValueError('Chỉ tự động kiểm tra với chiến dịch đăng thật.')
            campaign.status = 'queued'
            self._save(campaign)

            def worker():
                try:
                    updated = self.auto_verify_campaign(campaign_id, task_id=task_id, reserved=True)
                    if (
                        continue_pending
                        and any(t.status == S.PENDING for t in updated.tasks)
                    ):
                        self._run(campaign_id, False, reserved=True)
                except Exception as exc:
                    current = self.get_campaign(campaign_id)
                    if current:
                        self._summarize(current)
                        current.error_message = str(exc) or 'Không hoàn tất tự kiểm tra.'
                        self._save(current)
                finally:
                    operation.__exit__(None, None, None)
                    self._runner.release()

            threading.Thread(target=worker, daemon=True, name='auto-verify-campaign').start()
            return campaign
        except Exception:
            if acquired:
                operation.__exit__(None, None, None)
            self._runner.release()
            raise

    def _summarize(self, campaign):
        states = {t.status for t in campaign.tasks}
        if S.UNKNOWN in states:
            campaign.status = 'needs_review'
        elif S.ACTION_REQUIRED in states or S.PENDING in states:
            campaign.status = 'paused'
        elif S.FAILED in states:
            campaign.status = 'partial_failed'
        else:
            campaign.status = 'completed'

    def resolve_task(self, campaign_id, task_id, outcome, post_url=None):
        if self.busy:
            raise ResourceBusyError('Đợi chiến dịch hoàn tất trước khi xác minh.')
        with ExclusiveOperation(self._run_lock_path):
            campaign = self.get_campaign(campaign_id)
            if not campaign:
                raise InputError('Không tìm thấy chiến dịch.', 'campaign_id')
            task = next((t for t in campaign.tasks if t.task_id == task_id), None)
            if not task or task.status not in (S.UNKNOWN, S.PENDING_APPROVAL):
                raise ValueError('Chỉ xác minh tác vụ chưa rõ kết quả hoặc đang chờ duyệt.')
            if outcome == 'posted':
                url = post_permalink(post_url or '', task.group_url)
                if not url:
                    raise ValueError('Cần permalink /groups/.../posts/ID hoặc /permalink/ID đúng nhóm.')
                task.status, task.post_url, task.posted_at = S.POSTED, url, utc_now_iso()
            elif outcome == 'pending_approval':
                task.status = S.PENDING_APPROVAL
                task.posted_at = task.posted_at or utc_now_iso()
            elif outcome == 'not_submitted':
                task.status, task.post_url, task.submission_started = S.FAILED, None, False
                task.posted_at = None
            else:
                raise ValueError('Kết quả xác minh không hợp lệ.')
            task.evidence = 'customer_confirmed:' + outcome
            task.error_message = 'Khách đã kiểm tra trực tiếp trên Facebook: ' + outcome
            self._summarize(campaign)
            self._save(campaign)
            return campaign
