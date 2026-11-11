"""Persistent local collection jobs. No posting and no external CRM writes."""
import json
import hashlib
from pathlib import Path
import re
import threading
import uuid
from urllib.parse import urlsplit
from filelock import FileLock

from config.settings import RUNTIME_DIR, PROFILE_DIR
from core.filter_engine import REGISTRY_DIR, RegistryFilterEngine
from models.schema import utc_now_iso
from services.facebook_browser import profile_operation
from services.facebook_comment_collector import FacebookCommentCollector, normalize_post_url
from services.report_service import parse_comment_records, prepare_comment_report
from services.customer_records import aggregate_customers
from services.storage import ExclusiveOperation, ResourceBusyError, atomic_json


REGISTRIES = [
    ('intent_registry.json', 'intents', 'Ý định', 'keywords', 'weight'),
    ('variants_registry.json', 'variants', 'Từ viết tắt / biến thể', 'tokens', 'weight'),
    ('negation_registry.json', 'negations', 'Phủ định / từ chối', 'patterns', 'penalty'),
    ('spam_registry.json', 'spam_categories', 'Spam / ngoài ngành', 'patterns', 'penalty'),
    ('location_registry.json', 'locations', 'Địa điểm', 'aliases', None),
]


def registry_inventory():
    result = []
    for filename, section, name, tokens, score in REGISTRIES:
        data = json.loads((REGISTRY_DIR / filename).read_text(encoding='utf-8'))
        source = data[section]
        entries = source.items() if isinstance(source, dict) else ((r['name'], r) for r in source)
        rules = [{'key': key, 'description': row.get('description', row.get('canonical', row.get('name', key))),
                  'tokens': row[tokens], 'score': row.get(score) if score and not row.get('review_only') else None,
                  'score_type': score, 'strength': row.get('strength'), 'family': row.get('family'),
                  'review_only': bool(row.get('review_only')),
                  'requires_contact': bool(row.get('requires_contact')),
                  'question_safe': bool(row.get('question_safe'))} for key, row in entries]
        result.append({'file': filename, 'name': name, 'version': data.get('version'),
                       'rule_count': len(rules), 'token_count': sum(len(r['tokens']) for r in rules), 'rules': rules})
    return result


def filter_records(payload):
    records = prepare_comment_report(parse_comment_records(payload))
    return summarize_records(records)


def summarize_records(records):
    summary = {key: sum(r['classification'] == key for r in records)
               for key in ('LEAD_POTENTIAL', 'NEEDS_REVIEW', 'IGNORE')}
    return {'records': records, 'summary': {'total': len(records), **summary}}


def refresh_classifications(records):
    """Apply updated rules to saved results without rewriting collection history."""
    engine = RegistryFilterEngine()
    outdated = [i for i, row in enumerate(records) if row.get('registry_version') != engine.version]
    refreshed = [dict(row) for row in records]
    for offset in range(0, len(outdated), 5000):
        indices = outdated[offset:offset + 5000]
        evaluated = prepare_comment_report(parse_comment_records([records[i] for i in indices]), engine)
        for i, current in zip(indices, evaluated):
            for key in ('classification', 'score', 'contacts', 'reasons', 'signals', 'registry_version',
                        'interest_level', 'interest_evidence', 'identity_status', 'contact_channels', 'fb_user_url'):
                refreshed[i][key] = current[key]
    return refreshed


def record_key(row):
    # Comment IDs are scoped to the source post, including across refreshes.
    source = normalize_post_url(row['source_url'])
    identity = row.get('id') or row.get('comment_url') or hashlib.sha256(
        (str(row.get('fb_user_url', '')) + str(row.get('fb_user_name', '')) + row.get('raw_content', '')).encode()).hexdigest()
    return source, identity


def customer_group_key(row):
    path = urlsplit(row.get('source_url') or '').path
    group = re.match(r'^/groups/([^/]+)', path)
    return 'https://www.facebook.com/groups/' + group[1] if group else (row.get('group_name') or '__external__')


def select_customer_records(records, campaign_id=None, group_key=None, classification=None, q='', posting_task_id=None, interest_level=None):
    if classification not in (None, '', 'LEAD_POTENTIAL', 'NEEDS_REVIEW', 'IGNORE'):
        raise ValueError('Phân loại không hợp lệ.')
    if interest_level not in (None, '', 'strong', 'moderate', 'weak', 'unclear', 'none'):
        raise ValueError('Mức quan tâm không hợp lệ.')
    query = (q or '').strip().lower()
    result = []
    for row in records:
        if interest_level and row.get('interest_level', 'unclear') != interest_level:
            continue
        sources = row.get('sources') or [{**row, 'group_key': row.get('group_key', customer_group_key(row))}]
        if not any((not campaign_id or (source.get('campaign_id') or '__external__') == campaign_id)
                   and (not group_key or source.get('group_key') == group_key)
                   and (not posting_task_id or source.get('posting_task_id') == posting_task_id)
                   for source in sources):
            continue
        if classification and row['classification'] != classification:
            continue
        contacts = row.get('contacts', {})
        searchable = ' '.join(str(value) for value in (row.get('fb_user_name'), row.get('raw_content'),
            contacts.get('primary_phone'), contacts.get('zalo'), ' '.join(contacts.get('emails', []))) if value)
        if query and query not in searchable.lower():
            continue
        result.append(row)
    return result


class LeadFilterService:
    def __init__(self, data_dir=None, profile_dir=None, collector=None):
        self.data_dir = Path(data_dir or RUNTIME_DIR / 'data' / 'lead_runs')
        self.profile_dir = Path(profile_dir or PROFILE_DIR)
        self.collector = collector or FacebookCommentCollector(self.profile_dir)
        self._guard = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._active_id = None

    def _path(self, run_id):
        if not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise ValueError('Mã phiên lọc không hợp lệ.')
        return self.data_dir / (run_id + '.json')

    def get(self, run_id):
        path = self._path(run_id)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        # Windows may deny os.replace while a polling request is reading the
        # destination file. Readers and writers share this cross-process lock.
        with FileLock(str(self.data_dir / 'storage.lock'), timeout=5):
            if not path.exists():
                raise ValueError('Không tìm thấy phiên lọc.')
            return json.loads(path.read_text(encoding='utf-8'))

    def _save(self, run):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.data_dir / 'storage.lock'), timeout=5):
            atomic_json(self._path(run['id']), run)

    def get_for_display(self, run_id):
        run = self.get(run_id)
        run.update(summarize_records(aggregate_customers(refresh_classifications(run['records']))))
        return run

    def list_runs(self):
        if not self.data_dir.exists():
            return []
        result = []
        for path in self.data_dir.glob('*.json'):
            run = self.get(path.stem)
            # Detect interrupted runs when they are read; never pretend completion.
            if run['status'] == 'running' and run['id'] != self._active_id:
                try:
                    with ExclusiveOperation(self.data_dir / 'collection.lock'):
                        # The worker may finish after our first read. Re-read so
                        # a stale snapshot cannot overwrite the final results.
                        run = self.get(path.stem)
                        if run['status'] == 'running':
                            run.update(status='interrupted', message='Lần lấy trước bị gián đoạn. Kết quả đã lưu vẫn có thể xuất Excel.')
                            self._save(run)
                except ResourceBusyError:
                    pass
            result.append({key: value for key, value in run.items() if key != 'records'})
        return sorted(result, key=lambda r: r['created_at'], reverse=True)

    def start(self, post_url, limit=100, context=None):
        return self.start_batch([{'post_url': post_url, 'context': context or {}}], limit, context)

    def customer_results(self):
        """Latest saved version of each comment; history snapshots stay intact."""
        runs = self.list_runs()
        merged = {}
        metadata = ('campaign_id', 'listing_id', 'posting_task_id', 'group_name', 'listing_source_url')
        for info in reversed(runs):
            run = self.get(info['id'])
            for original in run['records']:
                if not original.get('source_url'):
                    continue
                key = record_key(original)
                old = merged.get(key, {})
                row = dict(original)
                for field in metadata:
                    row[field] = row.get(field) or old.get(field) or run.get('context', {}).get(field)
                row.update(group_key=customer_group_key(row), latest_run_id=run['id'],
                           last_collected_at=run.get('finished_at') or run['created_at'])
                merged[key] = row
        records = refresh_classifications(sorted(merged.values(), key=lambda r: r['last_collected_at'], reverse=True))
        return {**summarize_records(aggregate_customers(records)), 'active_runs': [r for r in runs if r['status'] == 'running'],
                'last_collected_at': records[0]['last_collected_at'] if records else None}

    def _previous_records(self, targets):
        """Merge saved snapshots oldest first so the newest edit wins."""
        saved = [self.get(r['id']) for r in reversed(self.list_runs())]
        records = {}
        for target in targets:
            url = target['post_url']
            for run in saved:
                previous_urls = {t['post_url'] for t in run.get('targets', [])}
                if run.get('post_url'):
                    previous_urls.add(run['post_url'])
                # A share URL can resolve to a canonical source URL. Keep that
                # alias so a later direct link refresh updates the same records.
                matching_run = url in previous_urls
                for row in run['records']:
                    if not row.get('source_url'):
                        continue
                    source = normalize_post_url(row['source_url'])
                    belongs = source == url or source in target['source_urls']
                    if matching_run:
                        belongs = belongs or not run.get('targets') or source in next(
                            (t.get('source_urls', []) for t in run.get('targets', []) if t['post_url'] == url), [])
                    if belongs:
                        target['source_urls'] = sorted(set(target['source_urls']) | {source})
                        row = {**row, **target.get('context', {})}
                        records[record_key(row)] = row
        return list(records.values())

    def start_batch(self, targets, limit=100, context=None):
        if not 1 <= len(targets) <= 100:
            raise ValueError('Chọn từ 1 đến 100 bài đã đăng để lấy bình luận.')
        normalized = {}
        for target in targets:
            url = normalize_post_url(target['post_url'])
            normalized[url] = {'post_url': url, 'context': target.get('context', {}),
                               'source_urls': [url], 'status': 'pending'}
        targets = list(normalized.values())
        if not 1 <= limit <= 500:
            raise ValueError('Giới hạn bình luận từ 1 đến 500.')
        with self._guard:
            if self._thread and self._thread.is_alive():
                raise ResourceBusyError('Đang lấy bình luận. Dừng hoặc chờ phiên hiện tại hoàn tất.')
            operation = ExclusiveOperation(self.data_dir / 'collection.lock')
            operation.__enter__()
            profile = profile_operation(self.profile_dir)
            try:
                profile.__enter__()
            except Exception:
                operation.__exit__()
                raise
            try:
                previous = self._previous_records(targets)
                run = {'id': uuid.uuid4().hex, 'post_url': targets[0]['post_url'] if len(targets) == 1 else None,
                       'targets': targets, 'limit': limit, 'context': context or {},
                       'status': 'running', 'message': 'Đang mở bài viết Facebook...',
                       'created_at': utc_now_iso(), **summarize_records(previous)}
                self._save(run)
                self._stop.clear()
                self._active_id = run['id']
                self._thread = threading.Thread(target=self._worker, args=(run, profile, operation), daemon=True, name='facebook-comments')
                self._thread.start()
            except Exception:
                self._active_id = None
                profile.__exit__()
                operation.__exit__()
                raise
            return run.copy()

    def _worker(self, run, profile, operation):
        merged = {record_key(row): row for row in run['records']}
        known_sources = {url for target in run['targets'] for url in target['source_urls']}
        try:
            for index, target in enumerate(run['targets'], 1):
                if self._stop.is_set():
                    run.update(status='stopped', message='Đã dừng; giữ toàn bộ bình luận đã lưu.')
                    break
                target['status'] = 'running'

                def progress(rows):
                    prepared = []
                    for row in rows:
                        row = {**row, 'source_url': row.get('source_url') or target['post_url'],
                               **target.get('context', {})}
                        source = normalize_post_url(row['source_url'])
                        if source not in known_sources:
                            # A new share token may lead to a post already collected.
                            historical = self._previous_records([{'post_url': source,
                                'source_urls': [source], 'context': target.get('context', {})}])
                            for old in historical:
                                merged.setdefault(record_key(old), old)
                            known_sources.add(source)
                        if not row.get('id'):
                            row['id'] = record_key(row)[1]
                        prepared.append(row)
                    for row in filter_records(prepared)['records']:
                        target['source_urls'] = sorted(set(target['source_urls']) | {row['source_url']})
                        merged[record_key(row)] = row
                    run.update(summarize_records(list(merged.values())),
                               message=f'Đang lấy bài {index}/{len(run["targets"])}; đã lưu {len(merged)} bình luận không trùng.')
                    self._save(run)

                try:
                    status, rows, message = self.collector.collect(target['post_url'], run['limit'], self._stop, progress)
                    progress(rows)
                except Exception as exc:
                    status, message = 'failed', f'Lấy bình luận bị gián đoạn ({type(exc).__name__}). Kết quả đã lưu được giữ lại.'
                target.update(status=status, message=message)
                if status in ('stopped', 'action_required'):
                    run.update(status=status, message=message)
                    break
            else:
                failed = sum(t['status'] == 'failed' for t in run['targets'])
                status = 'failed' if failed == len(run['targets']) else 'partial'
                message = run['targets'][0]['message'] if len(run['targets']) == 1 else (
                    f'Đã xử lý {len(run["targets"])} bài; {failed} bài lỗi. Đã lưu {len(merged)} bình luận không trùng. Chưa xác nhận lấy đủ bình luận.')
                run.update(status=status, message=message)
        except Exception as exc:
            # Preserve the last successful snapshot on timeout/browser closure.
            run.update(status='failed', message=f'Lấy bình luận bị gián đoạn ({type(exc).__name__}). Kiểm tra mạng, cửa sổ Facebook và phiên đăng nhập; kết quả đã lưu được giữ lại.')
        finally:
            try:
                run['finished_at'] = utc_now_iso()
                self._save(run)
            finally:
                self._active_id = None
                profile.__exit__()
                operation.__exit__()

    def stop(self, run_id):
        with self._guard:
            if self._active_id != run_id or not self._thread or not self._thread.is_alive():
                raise ValueError('Phiên này không đang chạy trong tiến trình hiện tại.')
            self._stop.set()
        return {'success': True, 'message': 'Đã yêu cầu dừng. Chờ thao tác đọc hiện tại hoàn tất.'}
