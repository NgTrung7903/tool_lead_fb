"""Kiểm thử tự động cho RegistryFilterEngine trên bộ dữ liệu mẫu thực tế.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import pytest

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Thêm root dir vào sys.path để import dễ dàng
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.filter_engine import RegistryFilterEngine
from core.contact_extractor import extract_contacts, normalize_phone


@pytest.mark.parametrize('text', ['xin hướng nhà', 'cho mình xin hướng', 'nhà hướng nào',
    'hướng ban công', 'hướng cửa chính', 'căn hướng gì', 'xin huong nha', 'xem hướng'])
def test_orientation_questions_are_interested_comments_for_review(text):
    result = RegistryFilterEngine().evaluate(text)
    assert result['classification'] == 'NEEDS_REVIEW', result
    assert result['score'] == 25
    assert 'deep_inquiry' in result['signals']['intents']


@pytest.mark.parametrize('text', ['2 tỷ mua luôn', '2,5 tỷ chốt luôn', 'giá này mua liền',
    '2 ty mua luon', 'chốt ngay', 'lấy luôn', 'cọc luôn', '2 tỷ thì chốt giá này'])
def test_offers_and_explicit_purchase_commitment_are_potential(text):
    result = RegistryFilterEngine().evaluate(text)
    assert result['classification'] == 'LEAD_POTENTIAL', result
    assert result['score'] >= 40


@pytest.mark.parametrize('text', ['không mua luôn đâu', 'k chốt luôn', 'ko lấy luôn đâu',
    'chưa muốn chốt luôn', 'không muốn chốt giá này', 'không chot luon', 'xấu vcl nhìn k muốn mua'])
def test_new_commitment_keywords_still_respect_denials(text):
    result = RegistryFilterEngine().evaluate(text)
    assert result['classification'] == 'IGNORE', result
    assert 'direct_purchase' not in result['signals']['intents']


@pytest.mark.parametrize('text', ['bớt được không', 'fix giá', 'giá cuối cùng', 'trả giá chút', 'có thương lượng'])
def test_negotiation_questions_are_reviewed_instead_of_ignored(text):
    assert RegistryFilterEngine().evaluate(text)['classification'] == 'NEEDS_REVIEW'


@pytest.mark.parametrize('text', [
    'xấu vcl nhìn k muốn mua', 'xấu vcl nhìn ko muốn mua', 'KHÔNG MUỐN MUA',
    'k muốn mua căn này', 'hk muốn mua nhà', 'kg cần mua căn này',
    'khong muon mua 0912345678', 'ko muốn mua 0912345678',
    'không hề muốn mua căn này', 'chẳng muốn mua căn này', 'chưa muốn mua',
])
def test_negated_purchase_is_ignored_and_does_not_score_positive_intent(text):
    result = RegistryFilterEngine().evaluate(text)
    assert result['classification'] == 'IGNORE', result
    assert 'no_purchase' in result['signals']['negations']
    assert 'direct_purchase' not in result['signals']['intents']
    assert not any('(+40đ)' in reason for reason in result['reasons'])


@pytest.mark.parametrize('text', ['muốn mua', 'Mình cần mua căn này', 'Muốn mua, còn không?',
                                'giá 500k, muốn mua', 'Có sổ không? Mình muốn mua'])
def test_positive_purchase_and_questions_remain_potential(text):
    result = RegistryFilterEngine().evaluate(text)
    assert result['classification'] == 'LEAD_POTENTIAL', result
    assert not result['signals']['negations']


def test_contact_extractor():
    text = "Căn này đẹp quá, alo mình 0912.345.678 hoặc qua số 090 311 2233 nhé"
    contacts = extract_contacts(text)
    assert len(contacts["phones"]) == 2
    assert "0912345678" in contacts["phones"]
    assert "0903112233" in contacts["phones"]
    assert contacts["has_contact"] is True
    print("✓ test_contact_extractor PASSED")


def test_filter_dataset_benchmark():
    engine = RegistryFilterEngine()
    dataset_path = ROOT_DIR / "data" / "test_dataset.json"
    with open(dataset_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    correct_count = 0
    total_count = len(items)

    print("\n--- BẮT ĐẦU CHẠY BENCHMARK BỘ DỮ LIỆU BÌNH LUẬN THỰC TẾ ---")
    for item in items:
        res = engine.evaluate(item["text"])
        actual = res["classification"]
        expected = item["expected_classification"]
        is_match = (actual == expected)

        status_icon = "✓" if is_match else "✗"
        print(f"[{status_icon}] ID: {item['id']} | Dự đoán: {actual:<14} | Kỳ vọng: {expected:<14} | Điểm: {res['score']:<4.0f} | Text: '{item['text'][:45]}...'")

        if not is_match:
            print(f"    -> LÝ DO: {res['reasons']}")
        else:
            correct_count += 1

    accuracy = (correct_count / total_count) * 100
    print(f"\nKẾT QUẢ ĐỘ CHÍNH XÁC: {correct_count}/{total_count} ({accuracy:.1f}%)")
    assert accuracy >= 95.0, f"Độ chính xác cần đạt ít nhất 95%, hiện tại đạt {accuracy}%"
    print("✓ test_filter_dataset_benchmark PASSED")


if __name__ == "__main__":
    test_contact_extractor()
    test_filter_dataset_benchmark()
