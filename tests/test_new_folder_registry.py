"""Review examples and counterexamples for the five supplied registry files."""
import hashlib
import json
from pathlib import Path

import pytest

from core.filter_engine import RegistryFilterEngine


@pytest.mark.parametrize('text,category,level', [
    ('số mình 0912345678', 'LEAD_POTENTIAL', 'strong'),
    ('số mình', 'IGNORE', 'none'),  # Incomplete text is not a validated contact share.
    ('cần mua đất', 'LEAD_POTENTIAL', 'strong'),
    ('hẹn xem nhà', 'NEEDS_REVIEW', 'strong'),
    ('còn không', 'NEEDS_REVIEW', 'weak'),
    ('có căn nào tầm giá 2 tỷ', 'NEEDS_REVIEW', 'moderate'),
    ('có căn 2pn tầm giá 2 tỷ', 'LEAD_POTENTIAL', 'moderate'),
    ('shr hxh', 'NEEDS_REVIEW', 'moderate'),
    ('gửi map vị trí', 'NEEDS_REVIEW', 'weak'),
    ('chấm', 'IGNORE', 'weak'), ('hóng', 'IGNORE', 'weak'),
    ('em chỉ tìm thuê thôi', 'NEEDS_REVIEW', 'unclear'),
    ('thuê chứ không mua', 'NEEDS_REVIEW', 'unclear'),
    ('mình cần bán căn nhà', 'NEEDS_REVIEW', 'unclear'),
    ('ké chủ tus bên em có căn tương tự 0912345678', 'IGNORE', 'none'),
    ('bên em nhận thi công nội thất 0912345678', 'IGNORE', 'none'),
    ('cho vay tiền giải ngân siêu tốc', 'IGNORE', 'none'),
    ('có hỗ trợ vay vốn không', 'NEEDS_REVIEW', 'moderate'),
    ('bên em có vay tín chấp không?', 'NEEDS_REVIEW', 'unclear'),
    ('không cần thuê, muốn mua nhà', 'LEAD_POTENTIAL', 'strong'),
    ('Cần mua nhà vay ngân hàng', 'LEAD_POTENTIAL', 'strong'),
    ('bên em nhận thiết kế nội thất không?', 'NEEDS_REVIEW', 'moderate'),
    ('Nhà này có dính quy hoạch không?', 'NEEDS_REVIEW', 'moderate'),
    ('Nhà này có ngập nước không bạn', 'NEEDS_REVIEW', 'moderate'),
    ('sổ chung hay sổ riêng vậy?', 'NEEDS_REVIEW', 'moderate'),
    ('khu này ngập nước 0912345678', 'NEEDS_REVIEW', 'unclear'),
    ('hỏi cho biết thôi', 'IGNORE', 'none'), ('đợi trúng vietlott', 'IGNORE', 'none'),
    ('rút cọc không mua nữa', 'IGNORE', 'none'),
    ('sổ chung không mua', 'IGNORE', 'none'),
    ('vi bằng không mua', 'IGNORE', 'none'),
    ('nhà ngập nước không muốn mua nữa', 'IGNORE', 'none'),
])
def test_new_examples_and_context_guards(text, category, level):
    result = RegistryFilterEngine().evaluate(text)
    assert result['classification'] == category, result
    assert result['interest_level'] == level, result


@pytest.mark.parametrize('text,family,score', [
    ('ib thông tin', 'conversation', 15),
    ('xin tt ib thông tin', 'conversation', 20),
    ('fix giá giá cuối bớt được không', 'price', 30),
    ('shr sổ hồng riêng hxh', 'details', 25),
])
def test_synonyms_do_not_stack_scores_for_same_signal(text, family, score):
    result = RegistryFilterEngine().evaluate(text)
    assert result['signals']['score_families'][family] == score
    assert result['score'] == score
    assert result['classification'] == 'NEEDS_REVIEW'


def test_borrower_questions_are_not_financial_advertising():
    engine = RegistryFilterEngine()
    for text in ['có hỗ trợ vay tiền mua nhà không?', 'có vay tín chấp không?', 'vay bank được bao nhiêu?']:
        assert not engine.evaluate(text)['signals']['spam'], text
    assert engine.evaluate('giải ngân 24h không cần thế chấp')['signals']['spam']


def test_legal_title_does_not_hide_a_separate_social_interest_signal():
    engine = RegistryFilterEngine()
    title = engine.evaluate('sổ hồng riêng')
    assert title['score'] == 25
    assert 'social_engagement' not in title['signals']['intents']
    separate = engine.evaluate('sổ hồng riêng, hóng thêm thông tin')
    assert separate['signals']['score_families']['interest'] == 10


def test_new_location_aliases_and_word_boundaries():
    result = RegistryFilterEngine().evaluate('tìm mua tại Q.12 Thới An, Hóc Môn hoặc Bến Lức Long An')
    assert {'Quận 12', 'Hóc Môn', 'Long An'} <= set(result['signals']['locations'])
    result = RegistryFilterEngine().evaluate('cần mua Quận 10')
    assert 'Quận 10' in result['signals']['locations'] and 'Quận 1' not in result['signals']['locations']


def test_import_manifest_tracks_all_original_inputs_without_editing_them():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root/'docs/REGISTRY_IMPORT_SOURCES.json').read_text(encoding='utf-8'))
    assert len(manifest['sources']) == 5
    for source in manifest['sources']:
        data = (root/manifest['source_directory']/source['file']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == source['sha256']
    engine = RegistryFilterEngine()
    assert 'spam_and_negative' not in engine.intents_cfg
    assert engine.intents_cfg['contact_sharing']['requires_contact']
