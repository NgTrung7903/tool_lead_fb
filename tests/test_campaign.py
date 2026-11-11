import threading
from unittest.mock import Mock

import pytest

from models.schema import GroupPostStatusEnum as S, GroupTaskResult, PropertyListing
from services.campaign_service import CampaignService
from services.group_manager import GroupManager
from services.storage import ResourceBusyError


@pytest.fixture
def system(tmp_path):
    groups = GroupManager(tmp_path / 'groups.json')
    group = groups.add_group('Test', 'https://facebook.com/groups/test/')
    revo = Mock()
    revo.config = {'revoland_mock_mode': False}
    revo.get_listing_by_id.return_value = PropertyListing(id='listing', code='A', title='Test',
        price_text='1 tỷ', location='HCM', description='Test', media_urls=[])
    revo.format_post_content.return_value = 'Nội dung đã duyệt'
    revo.download_listing_images.return_value = []
    engine = Mock()
    def posted(**kw):
        kw['before_submit']()
        return GroupTaskResult(task_id=kw['task_id'], group_id=group.id, group_name=group.name,
            group_url=group.group_url, status=S.POSTED, post_url=group.group_url + '/posts/123',
            evidence='test-confirmation', submission_started=True)
    engine.post_to_single_group.side_effect = posted
    svc = CampaignService(revo, groups, engine, tmp_path / 'campaigns.sqlite3')
    svc.config.update(min_delay_seconds=0, max_delay_seconds=0)
    return svc, group, engine


def test_new_campaigns_can_repost_and_completed_tasks_do_not_resubmit_on_resume(system):
    svc, group, engine = system
    first = svc.create_campaign('listing', [group.id])
    second = svc.create_campaign('listing', [group.id, group.id])
    assert len(second.tasks) == 1
    svc.execute_campaign(first.id)
    result = svc.execute_campaign(second.id)
    assert result.tasks[0].status == S.POSTED
    svc.execute_campaign(second.id)
    assert engine.post_to_single_group.call_count == 2


def test_delete_readd_group_does_not_block_reposting(system):
    svc, group, engine = system
    svc.execute_campaign(svc.create_campaign('listing', [group.id]).id)
    svc.group_manager.delete_group(group.id)
    new = svc.group_manager.add_group('New name', 'https://m.facebook.com/groups/test?ref=share')
    campaign = svc.create_campaign('listing', [new.id])
    assert campaign.tasks[0].status == S.PENDING


def test_unknown_allows_new_campaign_and_explicit_retry_preserves_history(system):
    svc, group, engine = system
    def uncertain(**kw):
        kw['before_submit']()
        raise RuntimeError('crash after click')
    engine.post_to_single_group.side_effect = uncertain
    campaign = svc.create_campaign('listing', [group.id])
    result = svc.execute_campaign(campaign.id)
    assert result.tasks[0].status == S.UNKNOWN
    svc.execute_campaign(campaign.id)  # Resume does not resubmit uncertain tasks.
    assert engine.post_to_single_group.call_count == 1
    assert svc.create_campaign('listing', [group.id]).tasks[0].status == S.PENDING
    retried = svc.retry_failed_tasks(campaign.id)
    assert engine.post_to_single_group.call_count == 2
    assert retried.tasks[0].attempt_history[0]['status'] == 'unknown'
    with pytest.raises(ValueError, match='permalink'):
        svc.resolve_task(campaign.id, campaign.tasks[0].task_id, 'posted', group.group_url)
    resolved = svc.resolve_task(campaign.id, campaign.tasks[0].task_id, 'not_submitted')
    assert resolved.tasks[0].status == S.FAILED


def test_retry_only_failed_not_posted(system):
    svc, group, engine = system
    g2 = svc.group_manager.add_group('Other', 'https://facebook.com/groups/other')
    campaign = svc.create_campaign('listing', [group.id, g2.id])
    campaign.tasks[0].status = S.POSTED
    campaign.tasks[0].post_url = group.group_url + '/posts/123'
    campaign.tasks[1].status = S.FAILED
    svc._save(campaign)
    def failed(**kw):
        return GroupTaskResult(task_id=kw['task_id'],group_id=g2.id,group_name=g2.name,group_url=g2.group_url,status=S.FAILED)
    engine.post_to_single_group.side_effect = failed
    result = svc.retry_failed_tasks(campaign.id)
    assert engine.post_to_single_group.call_count == 1
    assert result.tasks[0].status == S.POSTED
    assert result.tasks[0].retry_count == 0
    assert result.tasks[1].retry_count == 1


def test_uncertain_group_does_not_stop_remaining_pending_groups(system):
    svc, group, engine = system
    other = svc.group_manager.add_group('Other', 'https://facebook.com/groups/other')
    def submit(**kw):
        kw['before_submit']()
        g = kw['group']
        return GroupTaskResult(task_id=kw['task_id'], group_id=g.id, group_name=g.name, group_url=g.group_url,
            status=S.UNKNOWN if g.id == group.id else S.POSTED, submission_started=True,
            post_url=None if g.id == group.id else g.group_url+'/posts/456', evidence='fixture')
    engine.post_to_single_group.side_effect = submit
    result = svc.execute_campaign(svc.create_campaign('listing', [group.id, other.id]).id)
    assert [t.status for t in result.tasks] == [S.UNKNOWN, S.POSTED]
    assert engine.post_to_single_group.call_count == 2


def test_check_saved_link_is_read_only_preserves_url_and_does_not_block_repost(system):
    svc, group, engine = system
    posted = svc.execute_campaign(svc.create_campaign('listing', [group.id]).id)
    url = posted.tasks[0].post_url
    engine.check_saved_post.return_value = {'status': 'unavailable', 'message': 'Không còn hiển thị'}
    checked = svc.auto_verify_campaign(posted.id)
    task = checked.tasks[0]
    assert task.status == S.POSTED and task.post_url == url
    assert task.post_check_status == 'unavailable' and task.post_checked_at
    assert svc.get_campaign(posted.id).tasks[0].post_check_status == 'unavailable'
    assert svc.create_campaign('listing', [group.id]).tasks[0].status == S.PENDING
    engine.check_saved_post.return_value = {'status': 'available', 'message': 'Còn truy cập'}
    assert svc.auto_verify_campaign(posted.id).tasks[0].post_check_status == 'available'
    assert engine.post_to_single_group.call_count == 1


def test_mock_data_cannot_post(system):
    svc, group, engine = system
    svc.revoland_service.config['revoland_mock_mode'] = True
    campaign = svc.create_campaign('listing', [group.id])
    with pytest.raises(ValueError, match='Dữ liệu mẫu'):
        svc.execute_campaign(campaign.id)
    engine.post_to_single_group.assert_not_called()


def test_restart_preserves_submission_uncertainty(system):
    svc, group, engine = system
    campaign = svc.create_campaign('listing', [group.id])
    campaign.status = 'running'
    campaign.tasks[0].status = S.RUNNING
    campaign.tasks[0].submission_started = True
    svc._save(campaign)
    restored = CampaignService(svc.revoland_service, svc.group_manager, engine, svc.db_path)
    result = restored.get_campaign(campaign.id)
    assert result.status == 'interrupted'
    assert result.tasks[0].status == S.UNKNOWN


def test_simultaneous_execution_rejected(system):
    svc, group, engine = system
    campaign = svc.create_campaign('listing', [group.id])
    with svc._runner:
        with pytest.raises(ResourceBusyError):
            svc.execute_campaign(campaign.id)
    engine.post_to_single_group.assert_not_called()


def test_unproven_posted_result_becomes_unknown(system):
    svc, group, engine = system
    engine.post_to_single_group.side_effect = lambda **kw: GroupTaskResult(task_id=kw['task_id'], group_id=group.id,
        group_name=group.name,group_url=group.group_url,status=S.POSTED,post_url=group.group_url)
    campaign = svc.create_campaign('listing', [group.id])
    assert svc.execute_campaign(campaign.id).tasks[0].status == S.UNKNOWN


def test_background_start_returns_before_posting_completes(system):
    svc, group, engine = system
    started, release = threading.Event(), threading.Event()
    original = engine.post_to_single_group.side_effect
    def slow(**kw):
        started.set()
        assert release.wait(5)
        return original(**kw)
    engine.post_to_single_group.side_effect = slow
    campaign = svc.create_campaign('listing', [group.id])
    queued = svc.start_campaign(campaign.id)
    assert queued.status == 'queued'
    assert started.wait(5)
    assert svc.get_campaign(campaign.id).status == 'running'
    assert svc.busy
    release.set()
    # Wait for the worker via its ownership lock, no timing-dependent sleep.
    assert svc._runner.acquire(timeout=5)
    svc._runner.release()
    assert svc.get_campaign(campaign.id).status == 'completed'


def test_second_service_cannot_overwrite_active_run(system):
    svc, group, engine = system
    other = CampaignService(svc.revoland_service, svc.group_manager, engine, svc.db_path)
    started, release = threading.Event(), threading.Event()
    original = engine.post_to_single_group.side_effect
    def slow(**kw):
        started.set()
        assert release.wait(5)
        return original(**kw)
    engine.post_to_single_group.side_effect = slow
    campaign = svc.create_campaign('listing', [group.id])
    svc.start_campaign(campaign.id)
    try:
        assert started.wait(5)
        with pytest.raises(ResourceBusyError):
            other.start_campaign(campaign.id)
        assert svc.get_campaign(campaign.id).status == 'running'
    finally:
        release.set()
        assert svc._runner.acquire(timeout=5)
        svc._runner.release()
    assert svc.get_campaign(campaign.id).tasks[0].status == S.POSTED


def test_changed_preview_is_rejected_before_downloading(system):
    svc, group, engine = system
    with pytest.raises(ValueError,match='thay đổi'):
        svc.create_campaign('listing',[group.id],preview_token='old-hash')
    svc.revoland_service.download_listing_images.assert_not_called()


def test_legacy_success_is_not_trusted(system, monkeypatch, tmp_path):
    import json
    svc, group, engine = system
    campaign = svc.create_campaign('listing',[group.id])
    campaign.tasks[0].status = S.POSTED
    history_dir = tmp_path/'legacy'; history_dir.mkdir()
    history = history_dir/'campaigns_history.json'
    history.write_text(json.dumps([campaign.model_dump()]),encoding='utf-8')
    monkeypatch.setattr('services.campaign_service.CAMPAIGNS_FILE',history)
    restored = CampaignService(svc.revoland_service,svc.group_manager,engine,history_dir/'campaigns.sqlite3')
    imported = restored.get_campaign(campaign.id)
    assert imported.source_mode == 'legacy'
    assert imported.tasks[0].status == S.UNKNOWN
    assert history.exists()
    with pytest.raises(ValueError): restored.execute_campaign(campaign.id)


def test_start_reads_latest_tasks_after_acquiring_locks(system, monkeypatch):
    """Another request finishes between this request starting and taking its lock."""
    svc, group, engine = system
    other = CampaignService(svc.revoland_service, svc.group_manager, engine, svc.db_path)
    campaign = svc.create_campaign('listing', [group.id])
    actual_lock = threading.Lock()
    runner = Mock(wraps=actual_lock)
    first_acquire = True

    def acquire_after_other_request(*args, **kwargs):
        nonlocal first_acquire
        if first_acquire:
            first_acquire = False
            other.execute_campaign(campaign.id)
        return actual_lock.acquire(*args, **kwargs)

    runner.acquire.side_effect = acquire_after_other_request
    monkeypatch.setattr(svc, '_runner', runner)
    svc.start_campaign(campaign.id)
    assert actual_lock.acquire(timeout=5)
    actual_lock.release()
    assert engine.post_to_single_group.call_count == 1
    assert svc.get_campaign(campaign.id).tasks[0].status == S.POSTED


def test_start_validation_error_releases_both_locks(system):
    svc, group, engine = system
    with pytest.raises(ValueError, match='Không tìm thấy'):
        svc.start_campaign('missing')
    assert not svc.busy
    campaign = svc.create_campaign('listing', [group.id])
    svc.start_campaign(campaign.id)
    assert svc._runner.acquire(timeout=5)
    svc._runner.release()
    assert svc.get_campaign(campaign.id).tasks[0].status == S.POSTED


def test_campaign_enforces_max_100_groups_per_batch(system):
    svc, group, engine = system
    extra = [svc.group_manager.add_group(f'Group {i}', f'https://facebook.com/groups/g{i}') for i in range(2, 102)]
    all_six_ids = [group.id] + [g.id for g in extra]

    full_camp = svc.create_campaign('listing', all_six_ids[:100])
    assert len(full_camp.tasks) == 100

    with pytest.raises(ValueError, match='tối đa 100 nhóm'):
        svc.create_campaign('listing', all_six_ids)

    svc.config['max_groups_per_batch'] = 999
    assert svc.max_groups_per_batch() == 100


def test_queue_uses_saved_user_delay_between_groups_only(system, monkeypatch):
    svc, group, engine = system
    others = [svc.group_manager.add_group(f'Other {i}', f'https://facebook.com/groups/other{i}') for i in range(2)]
    campaign = svc.create_campaign('listing', [group.id] + [g.id for g in others],
                                   min_delay_seconds=42, max_delay_seconds=42)
    svc.config.update(min_delay_seconds=999, max_delay_seconds=999)
    def posted(**kw):
        kw['before_submit']()
        g = kw['group']
        return GroupTaskResult(task_id=kw['task_id'], group_id=g.id, group_name=g.name,
            group_url=g.group_url, status=S.POSTED, post_url=g.group_url + '/posts/123',
            evidence='fixture', submission_started=True)
    engine.post_to_single_group.side_effect = posted
    sleep = Mock()
    monkeypatch.setattr('services.campaign_service.time.sleep', sleep)
    result = svc.execute_campaign(campaign.id)
    assert engine.post_to_single_group.call_count == 3
    assert [call.args for call in sleep.call_args_list] == [(42.0,), (42.0,)]
    assert result.min_delay_seconds == result.max_delay_seconds == 42
    assert all(task.status == S.POSTED for task in result.tasks)


def test_queue_stops_on_action_required_and_keeps_remaining_pending(system, monkeypatch):
    svc, group, engine = system
    other = svc.group_manager.add_group('Other', 'https://facebook.com/groups/other')
    campaign = svc.create_campaign('listing', [group.id, other.id], min_delay_seconds=10, max_delay_seconds=10)
    engine.post_to_single_group.side_effect = lambda **kw: GroupTaskResult(
        task_id=kw['task_id'], group_id=group.id, group_name=group.name,
        group_url=group.group_url, status=S.ACTION_REQUIRED)
    sleep = Mock()
    monkeypatch.setattr('services.campaign_service.time.sleep', sleep)
    result = svc.execute_campaign(campaign.id)
    assert [task.status for task in result.tasks] == [S.ACTION_REQUIRED, S.PENDING]
    assert engine.post_to_single_group.call_count == 1
    sleep.assert_not_called()


@pytest.mark.parametrize('minimum,maximum', [(-1, 10), (20, 10), (0, 3601)])
def test_invalid_queue_delay_is_rejected(system, minimum, maximum):
    svc, group, _ = system
    with pytest.raises(ValueError, match='Khoảng nghỉ'):
        svc.create_campaign('listing', [group.id], min_delay_seconds=minimum, max_delay_seconds=maximum)
