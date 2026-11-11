"""Failure handling for concurrent posting; no browser or network required."""
from contextlib import nullcontext
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from models.schema import FBGroup, GroupPostStatusEnum as S
from services.poster_engine import FacebookPosterEngine


@pytest.fixture
def batch(tmp_path, monkeypatch):
    engine = FacebookPosterEngine(tmp_path / 'profile')
    context = Mock()
    context.storage_state.return_value = {'cookies': [{'name': 'c_user', 'value': 'fixture'}], 'origins': []}
    monkeypatch.setattr(engine, 'posting_session', lambda **kw: nullcontext(
        SimpleNamespace(ensure_context=lambda: context)))
    isolated = Mock(side_effect=lambda *args: nullcontext(Mock()))
    monkeypatch.setattr('services.facebook_browser.isolated_posting_context', isolated)
    groups = [FBGroup(id=f'g{i}', name=f'Group {i}', group_url=f'https://www.facebook.com/groups/test{i}')
              for i in range(2)]
    return engine, context, isolated, [(g.id, g) for g in groups]


@pytest.mark.parametrize('submitted,expected', [(False, S.FAILED), (True, S.UNKNOWN)])
def test_worker_failure_preserves_submission_uncertainty(batch, monkeypatch, submitted, expected):
    engine, _, _, items = batch
    before = []
    done = []

    def fail(page, context, group, content, images, before_submit, result, mark_submitted):
        if submitted:
            before_submit()
            mark_submitted()
        raise RuntimeError('offline failure')

    monkeypatch.setattr(engine, '_submit_on_page', fail)
    results = engine.post_batch_parallel(items[:1], 'Approved', [],
        on_before_submit=before.append, on_task_done=lambda tid, res: done.append(tid))
    res = results['g0']
    assert res.status == expected and res.submission_started == submitted
    assert before == (['g0'] if submitted else []) and done == ['g0']


def test_challenge_pauses_other_group_before_submit(batch, monkeypatch):
    engine, _, _, items = batch
    challenge_saved = threading.Event()
    before = []

    def submit(page, context, group, content, images, before_submit, result, mark_submitted):
        if group.id == 'g0':
            return result(S.ACTION_REQUIRED, 'Checkpoint')
        assert challenge_saved.wait(5)
        before_submit()
        pytest.fail('The second group must not submit after a checkpoint')

    def done(tid, res):
        if tid == 'g0':
            challenge_saved.set()

    monkeypatch.setattr(engine, '_submit_on_page', submit)
    results = engine.post_batch_parallel(items, 'Approved', [],
        on_before_submit=before.append, on_task_done=done)
    assert {r.status for r in results.values()} == {S.ACTION_REQUIRED}
    assert not before and not any(r.submission_started for r in results.values())


def test_unknown_result_does_not_pause_other_group(batch, monkeypatch):
    engine, _, _, items = batch
    first_saved = threading.Event()
    def submit(page, context, group, content, images, before_submit, result, mark_submitted):
        if group.id != 'g0':
            assert first_saved.wait(5)
        before_submit()
        mark_submitted()
        return result(S.UNKNOWN if group.id == 'g0' else S.POSTED,
                      url=None if group.id == 'g0' else group.group_url+'/posts/456', evidence='fixture')
    def done(tid, res):
        if tid == 'g0':
            first_saved.set()
    monkeypatch.setattr(engine, '_submit_on_page', submit)
    results = engine.post_batch_parallel(items, 'Approved', [], on_task_done=done)
    assert results['g0'].status == S.UNKNOWN and results['g1'].status == S.POSTED


def test_missing_login_starts_no_workers(batch):
    engine, context, isolated, items = batch
    context.storage_state.return_value = {'cookies': [], 'origins': []}
    done = []
    results = engine.post_batch_parallel(items, 'Approved', [], on_task_done=lambda tid, res: done.append(tid))
    assert {r.status for r in results.values()} == {S.ACTION_REQUIRED}
    assert len(done) == 2
    isolated.assert_not_called()


def test_worker_limit_is_enforced_before_opening_profile(batch):
    engine, context, isolated, items = batch
    with pytest.raises(ValueError, match='5 nhóm'):
        engine.post_batch_parallel(items * 3, 'Approved', [])
    context.storage_state.assert_not_called()
    isolated.assert_not_called()
