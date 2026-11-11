"""Manual refreshes merge comments across runs and retain source post identity."""
import threading

from services.lead_filter_service import LeadFilterService


URL = 'https://www.facebook.com/groups/test/posts/123'
OTHER = 'https://www.facebook.com/groups/other/posts/456'


def row(cid, text='xin giá', source=URL):
    return {'id': cid, 'fb_user_name': 'Khách', 'raw_content': text, 'source_url': source,
            'comment_url': source + '?comment_id=' + cid}


def finish(service, run):
    service._thread.join(5)
    assert not service._thread.is_alive()
    return service.get(run['id'])


class Collector:
    def __init__(self):
        self.rows = [row('c1'), row('c2')]
        self.calls = []

    def collect(self, url, limit, stop, progress):
        self.calls.append((url, limit))
        progress(self.rows[:limit])
        return 'partial', self.rows[:limit], 'Offline'


def test_refresh_updates_edits_adds_new_and_preserves_unseen_comments(tmp_path):
    collector = Collector()
    service = LeadFilterService(tmp_path / 'runs', tmp_path / 'profile', collector)
    first = finish(service, service.start(URL))
    collector.rows = [row('c1', 'Cần mua 0912345678'), row('c3')]
    restored = LeadFilterService(service.data_dir, service.profile_dir, collector)
    second = finish(restored, restored.start(URL))
    records = {r['id']: r for r in second['records']}
    assert set(records) == {'c1', 'c2', 'c3'}
    assert records['c1']['classification'] == 'LEAD_POTENTIAL'
    assert records['c1']['raw_content'] == 'Cần mua 0912345678'
    assert first['summary']['total'] == 2
    assert restored.get(first['id'])['records'][0]['raw_content'] == 'xin giá'
    collector.rows = []
    assert finish(restored, restored.start(URL))['summary']['total'] == 3


def test_batch_retains_separate_ids_for_each_post_and_single_refresh_stays_scoped(tmp_path):
    class PerPost(Collector):
        def collect(self, url, limit, stop, progress):
            rows = [row('same-id', source=url)]
            self.calls.append((url, limit))
            progress(rows)
            return 'partial', rows, 'Offline'
    collector = PerPost()
    service = LeadFilterService(tmp_path / 'runs', tmp_path / 'profile', collector)
    targets = [{'post_url': URL, 'context': {'group_name': 'A'}},
               {'post_url': OTHER, 'context': {'group_name': 'B'}}]
    saved = finish(service, service.start_batch(targets, 20))
    assert saved['summary']['total'] == 2
    assert {r['group_name'] for r in saved['records']} == {'A', 'B'}
    assert collector.calls == [(URL, 20), (OTHER, 20)]
    single = finish(service, service.start(URL, context={'group_name': 'A'}))
    assert single['summary']['total'] == 1
    again = finish(service, service.start_batch(targets))
    assert again['summary']['total'] == 2


def test_new_share_alias_merges_canonical_history_after_resolving(tmp_path):
    collector = Collector()
    service = LeadFilterService(tmp_path / 'runs', tmp_path / 'profile', collector)
    finish(service, service.start('https://www.facebook.com/share/p/first'))
    collector.rows = [row('c1', 'Cần mua'), row('c3')]
    saved = finish(service, service.start('https://www.facebook.com/share/newtoken'))
    assert saved['summary']['total'] == 3
    assert {r['id'] for r in saved['records']} == {'c1', 'c2', 'c3'}


def test_batch_stop_does_not_start_next_post(tmp_path):
    ready = threading.Event()
    class Blocking(Collector):
        def collect(self, url, limit, stop, progress):
            self.calls.append(url)
            progress([row('c1')])
            ready.set()
            assert stop.wait(5)
            return 'stopped', [row('c1')], 'Stopped'
    collector = Blocking()
    service = LeadFilterService(tmp_path / 'runs', tmp_path / 'profile', collector)
    run = service.start_batch([{'post_url': URL}, {'post_url': OTHER}])
    assert ready.wait(5)
    service.stop(run['id'])
    saved = finish(service, run)
    assert saved['status'] == 'stopped' and saved['summary']['total'] == 1
    assert collector.calls == [URL]
    assert saved['targets'][1]['status'] == 'pending'


def test_batch_preserves_partial_failure_and_continues_other_posts(tmp_path):
    class Failing(Collector):
        def collect(self, url, limit, stop, progress):
            progress([row('c1', source=url)])
            if url == URL:
                raise RuntimeError('offline failure')
            return 'partial', [row('c1', source=url)], 'Offline'
    service = LeadFilterService(tmp_path / 'runs', tmp_path / 'profile', Failing())
    saved = finish(service, service.start_batch([{'post_url': URL}, {'post_url': OTHER}]))
    assert saved['status'] == 'partial' and saved['summary']['total'] == 2
    assert [t['status'] for t in saved['targets']] == ['failed', 'partial']
