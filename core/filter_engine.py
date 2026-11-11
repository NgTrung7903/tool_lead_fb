"""Bộ lọc bình luận Facebook bằng Registry (Rule-based, không sử dụng LLM).
Tuân thủ tiêu chí:
- Tốc độ xử lý mili-giây, độc lập, không phụ thuộc kết nối bên ngoài.
- Giải thích rõ ràng nguyên nhân ra quyết định (Explainability / Auditability).
- Ưu tiên độ chính xác (Precision) cho Lead tự tạo; nghi ngờ đẩy vào Hàng chờ duyệt (Needs Review).
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import unicodedata
from typing import Any, Dict, List, Optional

from core.contact_extractor import extract_contacts


CURRENT_DIR = Path(__file__).resolve().parent
REGISTRY_DIR = CURRENT_DIR / "registry"


def fold_accents(text: str) -> str:
    """Fold Vietnamese accents while retaining regex syntax and token positions."""
    return ''.join(c for c in unicodedata.normalize('NFD', text)
                   if not unicodedata.combining(c)).replace('đ', 'd').replace('Đ', 'D')


class RegistryFilterEngine:
    def __init__(self, registry_dir: Optional[Path] = None):
        self.registry_dir = registry_dir or REGISTRY_DIR
        self.version = "1.0.0"
        self._load_registries()

    def _load_registries(self) -> None:
        """Đọc toàn bộ file cấu hình JSON của các registry."""
        with open(self.registry_dir / "intent_registry.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            self.intents_cfg = data.get("intents", {})
            self.version = data.get("version", self.version)

        with open(self.registry_dir / "variants_registry.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            self.variants_cfg = data.get("variants", {})
            self.context_cfg = data.get('context_rules', {})
            self.strength_cfg = data.get('strength_rules', {})

        with open(self.registry_dir / "negation_registry.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            self.negations_cfg = data.get("negations", {})

        with open(self.registry_dir / "spam_registry.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            self.spam_cfg = data.get("spam_categories", {})

        with open(self.registry_dir / "location_registry.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            self.locations_cfg = data.get("locations", [])

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize case, whitespace and Vietnamese accents for every rule."""
        if not text:
            return ""
        text = unicodedata.normalize("NFC", text).lower().strip()
        # Chuẩn hóa khoảng trắng thừa
        text = re.sub(r'\s+', ' ', text)
        # Expand a denial abbreviation only before an action/desire. A price
        # such as 500k or an unrelated letter k must not become a negation.
        text = re.sub(
            r'(?<!\w)(?:k|ko|k0|kg|hk|hok|khong|hông|hong|hem)(?=\s+(?:muốn|muon|cần|can|định|dinh|thích|thich|mua|chốt|chot|lấy|lay|cọc|coc|xem|đi|di|có|co|còn|con|quan tâm|quan tam)\b)',
            'không', text)
        return fold_accents(text)

    def _pattern_spans(self, text, pattern):
        normalized = self.normalize_text(pattern)
        if not normalized:
            return []
        return [match.span() for match in re.finditer(r'(?<!\w)' + re.escape(normalized) + r'(?!\w)', text)]

    def _find_matches(self, text: str, patterns: List[str], excluded_spans=()) -> List[str]:
        """Tìm các pattern khớp trong câu, hỗ trợ cả token ngắn và cụm từ."""
        matched = []
        for pat in patterns:
            spans = self._pattern_spans(text, pat)
            if any(not any(left <= start < right for left, right in excluded_spans)
                   for start, end in spans):
                matched.append(pat)
        return matched

    @staticmethod
    def _question_or_negated_detail(text, start, end):
        # Inspect the containing sentence, not an unrelated question elsewhere.
        boundaries = list(re.finditer(r'[.!?;\n]', text[:start]))
        left = boundaries[-1].end() if boundaries else 0
        following = re.search(r'[.!?;\n]', text[end:])
        right = end + following.end() if following else len(text)
        clause = text[left:right]
        prefix = text[max(left, start - 30):start]
        return bool('?' in clause or re.search(r'(?<!\w)(?:khong|ko|k|chua)(?:\s+(?:ban|em|anh|chi|ad|vay|nhi|nha|nhe|a))*\s*$', clause[end-left:])
                    or re.search(r'(?:khong|ko|k)\s+(?:bi\s+|co\s+)?$', prefix)
                    or re.search(r'(?<!\w)(?:cho hoi|xin hoi|lieu|the nao|ra sao)(?!\w)', clause))

    def evaluate(self, comment_text: str) -> Dict[str, Any]:
        """Đánh giá toàn diện 1 bình luận và trả về phân loại, điểm số kèm lý do."""
        norm_text = self.normalize_text(comment_text)
        contacts = extract_contacts(comment_text)

        reasons: List[str] = []
        matched_signals = {
            "intents": {},
            "variants": {},
            "negations": {},
            "spam": {},
            "locations": [],
            "contacts": contacts
        }
        strengths = {'strong': [], 'moderate': [], 'weak': []}
        contact_refusals = [m.span() for p in self.context_cfg.get('contact_refusals', [])
                            for m in re.finditer(fold_accents(p), norm_text)]
        message_requests = [m for p in self.context_cfg.get('message_requests', [])
                            for m in re.finditer(fold_accents(p), norm_text)
                            if not any(left <= m.start() < right for left, right in contact_refusals)]
        has_dm = bool(re.search(r'(?<!\w)dm(?!\w)', norm_text))
        ambiguous_dm = has_dm and not message_requests and not contact_refusals
        matched_signals['context'] = {'ambiguous_dm': ambiguous_dm,
            'message_requests': [m.group() for m in message_requests],
            'contact_refusals': [norm_text[a:b] for a, b in contact_refusals]}

        # 1. Kiểm tra Spam
        total_spam_penalty = 0
        guarded_terms = []
        offer_pattern = r'(?<!\w)(?:(?:bên em|bên mình|chúng tôi)\s+(?:nhận|chuyên|hỗ trợ|cung cấp)|nhận\s+(?:thiết kế|thi công|ký gửi|làm sổ|xóa thế chấp)|xưởng\s+nội thất|cho vay\s+(?:tiền|vốn)|ké chủ|xin phép chủ)(?!\w)'
        explicit_offer = any(not self._question_or_negated_detail(norm_text,m.start(),m.end())
                             for m in re.finditer(fold_accents(offer_pattern), norm_text))
        for cat_key, cat_data in self.spam_cfg.items():
            matches = self._find_matches(norm_text, cat_data.get("patterns", []))
            if cat_data.get('question_safe') and not explicit_offer:
                safe_purchase = cat_data.get('safe_with_purchase') and bool(self._find_matches(
                    norm_text, self.intents_cfg.get('direct_purchase', {}).get('keywords', [])))
                protected = [p for p in matches if safe_purchase or all(
                    self._question_or_negated_detail(norm_text, a, b) for a,b in self._pattern_spans(norm_text,p))]
                guarded_terms.extend(protected)
                matches = [p for p in matches if p not in protected]
            if matches:
                matched_signals["spam"][cat_key] = matches
                total_spam_penalty += cat_data.get("penalty", 100)
                reasons.append(f"Phát hiện nội dung spam/ngoài ngành: {cat_data.get('description')} ({', '.join(matches)})")

        if total_spam_penalty >= 100:
            return {
                "classification": "IGNORE",
                "score": 0.0,
                "reasons": reasons,
                "contacts": contacts,
                "signals": matched_signals,
                "registry_version": self.version,
                "interest_level": "none", "interest_evidence": []
            }

        # 2. Kiểm tra Phủ định / Từ chối
        total_negation_penalty = 50 if contact_refusals else 0
        other_demand = False
        review_concerns = False
        negated_spans = list(contact_refusals)
        if contact_refusals:
            matched_signals['negations']['contact_refusal'] = [norm_text[a:b] for a,b in contact_refusals]
            reasons.append('Có lời từ chối nhận tin nhắn; không cộng điểm yêu cầu liên hệ.')
        for neg_key, neg_data in self.negations_cfg.items():
            matches = self._find_matches(norm_text, neg_data.get("patterns", []))
            if neg_data.get('review_only'):
                # A refusal to rent must not override an explicit buying request.
                matches = [p for p in matches if any(not re.search(
                    r'(?<!\w)(?:khong|ko|k|chang|cha)\s+$', norm_text[max(0,a-20):a])
                    for a,b in self._pattern_spans(norm_text,p))]
            if neg_data.get('question_safe'):
                matches = [p for p in matches if any(not self._question_or_negated_detail(norm_text,a,b)
                            for a,b in self._pattern_spans(norm_text,p))]
            if matches:
                if neg_data.get('review_only'):
                    other_demand = True
                    matched_signals['negations'][neg_key] = matches
                    reasons.append('Nhu cầu thuê/bán khác loại nhu cầu mua; cần xem lại, không gắn nhãn spam.')
                    continue
                review_concerns = review_concerns or neg_data.get('review_when_interested', False)
                for pattern in matches:
                    negated_spans.extend(self._pattern_spans(norm_text, pattern))
                matched_signals["negations"][neg_key] = matches
                penalty = neg_data.get("penalty", 40)
                total_negation_penalty += penalty
                reasons.append(f"Có tín hiệu phủ định/từ chối: {neg_data.get('description')} ({', '.join(matches)})")

        # 3. Kiểm tra Ý định (Intents)
        intent_score = 0
        family_scores = {}
        intent_families = set()

        def score_family(family, weight):
            previous = family_scores.get(family, 0)
            family_scores[family] = max(previous, weight)
            return max(0, weight - previous)

        # Accent folding makes "hồng" and "hóng" identical. A legal-title
        # phrase must not also count as a separate social-interest signal.
        social_exclusions = negated_spans + self._pattern_spans(norm_text, 'sổ hồng')
        for intent_key, intent_data in self.intents_cfg.items():
            if intent_data.get('requires_contact') and not contacts.get('has_contact'):
                continue
            excluded_spans = social_exclusions if intent_key == 'social_engagement' else negated_spans
            matches = self._find_matches(norm_text, intent_data.get("keywords", []), excluded_spans)
            if matches:
                matched_signals["intents"][intent_key] = matches
                strengths[intent_data.get('strength', 'weak')].extend(matches)
                weight = intent_data.get("weight", 10)
                family = intent_data.get('family', intent_key)
                delta = score_family(family, weight)
                if intent_data.get('strength') in ('strong', 'moderate'):
                    intent_families.add(family)
                intent_score += delta
                reasons.append(f"Khớp ý định {intent_data.get('description')}: {', '.join(matches)} (+{delta}đ; nhóm {family})")

        # 4. Kiểm tra Biến thể / Teencode (Variants)
        variant_score = 0
        for var_key, var_data in self.variants_cfg.items():
            matches = self._find_matches(norm_text, var_data.get("tokens", []), negated_spans)
            if matches:
                matched_signals["variants"][var_key] = matches
                strengths[var_data.get('strength', 'weak')].extend(matches)
                weight = var_data.get("weight", 10)
                family = var_data.get('family', var_key)
                if var_data.get('strength') in ('strong', 'moderate'):
                    intent_families.add(family)
                delta = score_family(family, weight)
                variant_score += delta
                reasons.append(f"Khớp từ viết tắt/teencode ({var_data.get('canonical')}): {', '.join(matches)} (+{delta}đ; không cộng trùng nhóm)")

        if message_requests:
            weight = self.context_cfg.get('message_weight', 20)
            intent_score += score_family('conversation', weight)
            intent_families.add('conversation')
            matched_signals['intents'].setdefault('consultation_request', []).extend(m.group() for m in message_requests)
            strengths['moderate'].extend(m.group() for m in message_requests)
            reasons.append('Ngữ cảnh yêu cầu nhắn tin/DM, không suy đoán quốc tịch của người viết.')
        for level, patterns in self.strength_cfg.items():
            strengths[level].extend(self._find_matches(norm_text, patterns, negated_spans))

        # 5. Kiểm tra Địa điểm
        for loc in self.locations_cfg:
            matches = self._find_matches(norm_text, loc.get("aliases", []))
            if matches:
                matched_signals["locations"].append(loc.get("name"))
                reasons.append(f"Khớp địa điểm khu vực: {loc.get('name')} ({', '.join(matches)})")

        # 6. Tính điểm tổng hợp (Scoring Calculation)
        contact_bonus = 0
        if contacts.get("primary_phone"):
            contact_bonus = 50
            reasons.append(f"Cung cấp số điện thoại hợp lệ: {contacts['primary_phone']} (+50đ)")
        elif contacts.get("zalo"):
            contact_bonus = 25
            reasons.append(f"Có thông tin Zalo: {contacts['zalo']} (+25đ)")
        elif contacts.get("emails"):
            contact_bonus = 30
            reasons.append(f"Có thông tin Email: {contacts['emails'][0]} (+30đ)")

        raw_score = contact_bonus + intent_score + variant_score - total_negation_penalty
        final_score = max(0.0, float(raw_score))

        # 7. Ma trận ra quyết định (Decision Matrix)
        classification = "IGNORE"

        # Case A: Có số điện thoại hợp lệ + không bị phủ định áp đảo
        if contacts.get("primary_phone") and total_negation_penalty == 0:
            classification = "LEAD_POTENTIAL"
            reasons.insert(0, "Lead tiềm năng: Có số điện thoại liên hệ trực tiếp và không có từ chối.")

        # Case B: Có ý định mua/xem rất mạnh (score >= 40) và không có phủ định
        elif final_score >= 40 and total_negation_penalty == 0 and (
                any(k in matched_signals['intents'] for k in ('direct_purchase', 'viewing_request', 'contact_sharing'))
                or len(intent_families) >= 2):
            classification = "LEAD_POTENTIAL"
            reasons.insert(0, f"Lead tiềm năng: Nhu cầu xem/mua rõ nét (Điểm tổng hợp {final_score:.0f} >= 40).")

        # Case C: Tín hiệu tiềm năng trung bình hoặc câu hỏi sơ lược (ib, giá bn, hỏi thăm) -> Cần nhân viên duyệt
        elif final_score >= 15 and total_negation_penalty < 40:
            classification = "NEEDS_REVIEW"
            reasons.insert(0, f"Chuyển hàng chờ duyệt: Có quan tâm sơ lược (Điểm {final_score:.0f}), cần sale phản hồi tư vấn.")

        # Case D: Phủ định hoặc điểm quá thấp
        else:
            classification = "IGNORE"
            if total_negation_penalty > 0:
                reasons.insert(0, f"Bỏ qua: Bình luận thể hiện sự từ chối hoặc tiêu cực (Phạt trừ -{total_negation_penalty}đ).")
            else:
                reasons.insert(0, f"Bỏ qua: Không đủ tín hiệu nhu cầu giao dịch bất động sản (Điểm {final_score:.0f} < 15).")

        if other_demand:
            classification = 'NEEDS_REVIEW'
            reasons.insert(0, 'Nhu cầu khác loại tin: cần kiểm tra thuê/bán, không xác nhận là người mua.')
        elif review_concerns and matched_signals['intents'] and total_negation_penalty < 40:
            classification = 'NEEDS_REVIEW'
            reasons.insert(0, 'Có quan tâm nhưng nêu vấn đề của căn nhà; cần trao đổi thêm.')
        elif guarded_terms and classification == 'IGNORE' and not total_negation_penalty:
            classification = 'NEEDS_REVIEW'
            reasons.insert(0, 'Đây có thể là câu hỏi về dịch vụ/tài chính, chưa đủ cơ sở coi là quảng cáo.')
        elif contact_refusals and matched_signals['intents']:
            classification = 'NEEDS_REVIEW'
            reasons.insert(0, 'Có tín hiệu quan tâm nhưng từ chối nhận DM; cần xem ngữ cảnh.')
        elif ambiguous_dm and not total_negation_penalty and not matched_signals['intents']:
            classification = 'NEEDS_REVIEW'
            reasons.insert(0, 'DM chưa rõ là nhắn tin hay cách nói khác; không tự đoán nghĩa.')
        level = next((key for key in ('strong', 'moderate', 'weak') if strengths[key]), 'none')
        if total_negation_penalty:
            level = 'unclear' if classification == 'NEEDS_REVIEW' else 'none'
        elif ambiguous_dm and not matched_signals['intents']:
            level = 'unclear'
        elif level == 'none' and contacts.get('has_contact'):
            level = 'unclear'
        if other_demand or (guarded_terms and level == 'none'):
            level = 'unclear'
        matched_signals['context']['guarded_terms'] = guarded_terms
        matched_signals['score_families'] = family_scores
        matched_signals['strength'] = strengths
        return {
            "classification": classification,
            "score": final_score,
            "reasons": reasons,
            "contacts": contacts,
            "signals": matched_signals,
            "registry_version": self.version,
            "interest_level": level,
            "interest_evidence": list(dict.fromkeys(word for words in strengths.values() for word in words))
        }
