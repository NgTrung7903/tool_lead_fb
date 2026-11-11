# Danh sách 5 bảng registry

Phiên bản **1.3.0**. Nguồn là các JSON trong `core/registry/`; dashboard hiển thị qua `/api/leads/registries`. Xem [đối chiếu 5 file bổ sung](REGISTRY_IMPORT_REVIEW.md).

Điểm là trọng số quy tắc, không phải xác suất. Các tín hiệu cùng `family` chỉ lấy điểm cao nhất, kể cả nằm ở nhiều bảng. Mức quan tâm và phân loại lead là hai thông tin riêng.

| Bảng | Nhóm | Từ khóa / bí danh |
| --- | --- | --- |
| [intent_registry.json](../core/registry/intent_registry.json) — Ý định | 10 | 240 |
| [variants_registry.json](../core/registry/variants_registry.json) — Từ viết tắt / biến thể | 9 | 133 |
| [negation_registry.json](../core/registry/negation_registry.json) — Phủ định / nhu cầu khác | 6 | 171 |
| [spam_registry.json](../core/registry/spam_registry.json) — Spam / quảng cáo | 6 | 110 |
| [location_registry.json](../core/registry/location_registry.json) — Địa điểm | 23 | 167 |

## Ý định — `intent_registry.json`

| Nhóm | Mô tả | Điểm / mức | Family / điều kiện | Từ khóa / bí danh |
| --- | --- | --- | --- | --- |
| direct_purchase | Nhu cầu mua, đặt cọc, chốt giao dịch trực tiếp | +40 / strong | purchase | cần mua, muốn mua, tìm mua, mua căn này, mua nhà, đặt cọc, chốt cọc, giữ chỗ, lấy căn này, chốt căn này, mua ở, mua đầu tư, want to buy, interested in buying, ready to buy, i will buy, i'll buy, cần mua gấp, mua ngay, mua luôn, mua liền, chốt luôn, chốt ngay, chốt giá, chốt căn, lấy luôn, lấy căn, cọc luôn, cọc liền, mua luon, mua lien, chot luon, chot ngay, coc luon, mua đất, dat coc |
| viewing_request | Yêu cầu hẹn xem nhà thực tế | +35 / strong | viewing | xem nhà, xem đất, đi xem, qua xem, dắt đi xem, dẫn đi xem, khi nào xem được, cuối tuần xem, hôm nay xem, mai xem, xem thực tế, coi nhà, coi đất, mở cửa xem, xem căn này, ghé xem, hẹn xem, đặt lịch xem, xem nha, xem dat, di xem, coi nha, coi dat, hen xem |
| deep_inquiry | Hỏi thông tin kỹ thuật, pháp lý, vị trí, tài chính | +25 / moderate | details | sổ hồng, sổ đỏ, pháp lý, quy hoạch, tranh chấp, hướng gì, hướng nào, diện tích, tầng mấy, bao nhiêu m2, chiết khấu, chính sách, ngân hàng hỗ trợ, vay được bao nhiêu, tiến độ, bàn giao, nội thất, xin hướng, hướng nhà, nhà hướng, hướng căn, căn hướng, hướng cửa, cửa hướng, hướng ban công, ban công hướng, xin huong, huong nha, huong can, huong cua, huong ban cong, xem hướng, shr, sổ riêng, hoàn công, thổ cư, hẻm mấy mét, hẻm xe hơi, ô tô vào được không, vị trí ở đâu, địa chỉ ở đâu, đoạn nào, gần chợ không, ngập không, vay bank, so hong, phap ly, vi tri o dau, ngập nước, hẻm cụt, đường đâm, thóp hậu, vay ngân hàng, hỗ trợ vay, vay vốn, vay tiền, sổ chung, vi bằng, hẻm sâu, xa trung tâm, phong thủy, nghĩa trang, hướng tây, quy hoach, hem cut, so chung, vi bang, phong thuy |
| consultation_request | Yêu cầu inbox, tư vấn, gửi thông tin | +20 / moderate | conversation | tư vấn giúp, tư vấn em, tư vấn mình, tư vấn nhé, hỗ trợ tư vấn, gửi thông tin, gửi vị trí, gửi hình ảnh, gửi sổ, gửi bảng giá, liên hệ lại, gọi lại cho mình, nhắn tin cho mình, tư vấn, xin thông tin, xin tt, gửi tt, xin định vị, tu van, tu van giup, gui thong tin, check inbox, goi lai |
| pricing_inquiry | Hỏi giá cơ bản trên bình luận | +15 / weak | price | giá bao nhiêu, báo giá, xin giá, giá cả thế nào, giá sao, tổng giá, giá bn, bn tiền, ib giá, inb giá, mấy tỷ, mấy đồng, rổ giá, gia bao nhieu, gia bn, bao gia, xin gia, ib gia, gia sao |
| contact_sharing | Khách chủ động để lại SĐT hoặc Zalo trên bình luận | +45 / strong | contact, requires_contact | số mình, sđt mình, gọi số này, alo mình số, liên hệ số, zalo mình, kb zalo số, add zalo, nhắn qua số, gửi qua zalo số, so minh, sdt minh, zalo minh, goi so nay |
| price_negotiation | Trả giá, thương lượng mức giá chốt | +30 / strong | price | có bớt không, bớt được không, có giảm không, bớt chút, bớt lộc, thương lượng không, có thương lượng, còn thương lượng, trả giá, giá chốt, giá cuối, giá cuối cùng, giá net, fix giá, bao sang tên, làm việc chính chủ, tra gia, bot duoc khong, fix gia, gia chot, thuong luong |
| custom_criteria | Khách hỏi tìm bất động sản theo nhu cầu/tài chính riêng dưới bình luận | +25 / moderate | criteria | có căn nào, còn căn nào, có lô nào, tầm giá, tài chính tầm, cần tìm căn, có căn 1pn, có căn 2pn, có căn 3pn, còn lô góc, có nhà trệt, co can nao, con can nao, tai chinh tam, can tim can |
| availability_check | Hỏi tình trạng còn hay đã bán | +15 / weak | availability | còn không, còn bán không, bán chưa, nhà còn không, đất còn không, căn này còn không, con khong, con ban khong, ban chua, nha con khong |
| social_engagement | Bình luận chấm, hóng, quan tâm trên Facebook | +10 / weak | interest | quan tâm, qt, q.tâm, qtam, chấm, hóng, note, quan tam, cham, hong |

## Từ viết tắt / biến thể — `variants_registry.json`

| Nhóm | Mô tả | Điểm / mức | Family / điều kiện | Từ khóa / bí danh |
| --- | --- | --- | --- | --- |
| inbox_variants | inbox | +15 / weak | conversation | ib, inb, inbox, in box, inbox mình, ib mình, ib nhé, check ib, rep ib, inbox shop, ib e, ib a, inb mình, check inb, rep inb, ib em, ib anh, ib chị, nhắn mình, tv qua ib |
| interested_variants | quan_tam | +15 / weak | interest | qtam, quan tam, q tâm, q.tam, q.tâm, qtam nhe, quan tâm căn này, quan tâm nhé, quan tam can nay, rất quan tâm, quan tâm, interested |
| price_variants | bao_nhieu | +15 / weak | price | bn, bnhieu, bao nhieu, gia bn, giá bn, bn tiền, bnh, mấy đồng, bao tien, mấy tỷ, may ty, rổ giá, ro gia, giá sao |
| contact_variants | lien_he | +20 / moderate | conversation | sdt, sđt, so dt, số đt, zalo, zl, add zalo, check zalo, lh, call, alo, phone, số điện thoại, kb zalo, kết bạn zalo, gửi qua zalo, liên hệ, gọi mình |
| info_variants | thong_tin | +10 / weak | conversation | tt, ttin, thông tin, xin tt, gửi tt, chi tiet, ctiet, chi tiết, thong tin, full tt, thông số |
| re_variants | can_ho_dat | +10 / weak | property_reference | căn này, can nay, nhà này, nha nay, lô này, lo nay, miếng này, mảnh này, nền này, nen nay, bất động sản này |
| legal_variants | phap_ly | +20 / moderate | details | shr, sổ hồng riêng, so hong rieng, sổ riêng, so rieng, sổ sẵn, so san, full thổ, full tho, thổ cư 100%, tho cu, hoàn công, hoan cong, ccst, công chứng ngay, pháp lý chuẩn |
| feature_access_variants | dac_diem_bds | +15 / moderate | details | hxh, hẻm xe hơi, hem xe hoi, hẻm ô tô, hem o to, ô tô đỗ cửa, mt, mặt tiền, mat tien, lô góc, lo goc, căn góc, can goc, 1pn, 2pn, 3pn, trệt lầu, tret lau, full nt, full nội thất |
| location_request_variants | vi_tri | +15 / weak | details | vị trí, vi tri, định vị, dinh vi, share vị trí, gửi map, google map, chấm vị trí, khúc nào, đoạn nào, gần chỗ nào |

## Phủ định / nhu cầu khác — `negation_registry.json`

| Nhóm | Mô tả | Điểm / mức | Family / điều kiện | Từ khóa / bí danh |
| --- | --- | --- | --- | --- |
| no_purchase | Từ chối mua hoặc huỷ giao dịch | -50 / — |  | không mua, ko mua, k mua, chẳng mua, thôi không mua, thôi ko mua, hết nhu cầu, không còn nhu cầu, ko còn nhu cầu, hết tiền, không đủ tiền, hủy, huy, bỏ qua, không cần nữa, ko cần nữa, k cần nữa, đã mua chỗ khác, tìm được rồi, mua rồi, thôi em, thôi b, thôi shop, không muốn mua, không cần mua, không có nhu cầu, không còn muốn mua, không định mua, không thích mua, không hề muốn mua, không phải muốn mua, chẳng muốn mua, chả muốn mua, chưa muốn mua, chưa có nhu cầu, không muon mua, không can mua, không co nhu cau, không dinh mua, không chốt, chả mua, không lấy, chẳng lấy, không cọc, không muốn chốt, không cần chốt, chưa muốn chốt, không muốn lấy, không định lấy, không muốn cọc, không chot, không lay, không coc, don't want to buy, do not want to buy, not interested in buying, not interested, not buying, won't buy, will not buy, don't buy, do not buy, ko đủ tài chính, vượt tài chính, mua được nhà rồi, thôi bạn, rút cọc, ko chot, ko lay |
| bad_feedback_overprice | Chê đắt, tiêu cực, phản đối mức giá | -40 / — |  | đắt quá, dat qua, ngáo giá, ngao gia, giá trên trời, ảo giá, chát quá, giá này ai mua, cắt cổ, lừa đảo, treo đầu dê, đăng ảo, tin rác, chém gió, bán cho ma, chó nó mua, giá cao thế, mắc quá, mac qua, giá cao quá, ao gia, giá này để mà ở, lua dao, ôm bom, mua vào mắt |
| no_viewing | Từ chối hoặc hủy lịch xem nhà | -30 / — |  | không xem nữa, ko xem nữa, không đi được, bận không đi, hủy hẹn, bận rồi, không muốn xem, không cần xem, không muốn đi xem, chưa muốn xem, không muon xem, không can xem, ko đi được, hủy lịch xem, hoãn lịch, huy hen, ko di xem |
| wrong_demand_type | Nhu cầu thuê hoặc bán khác với nhu cầu mua; cần nhân viên xem lại, không phải spam | Chuyển xem lại; không trừ / — | review_only | chỉ tìm thuê, tìm thuê thôi, thuê chứ không mua, thuê chứ ko mua, cần thuê chứ không mua, có cho thuê không, thuê nguyên căn, mình cần bán, em cần bán, đang cần bán, bán chứ không mua, chi tim thue, thue chu ko mua, minh can ban, cần cho thuê, cần thuê, tìm thuê, cho thuê không, can thue, cho thue |
| property_defect_rejection | Từ chối vì lỗi vị trí, hẻm nhỏ, ngập nước hoặc pháp lý/phong thủy xấu | -35 / — | question_safe, review_when_interested | xa quá, xa trung tâm quá, hẻm nhỏ quá, hẻm cụt, hẻm sâu quá, khu này ngập, ngập tới gối, ngập nước, kẹt xe lắm, dính quy hoạch, đất quy hoạch, sổ chung không mua, vi bằng không mua, lỗi phong thủy, đường đâm, thóp hậu, gần nghĩa trang, mả mồ, hướng tây nắng lắm, không hợp hướng, ko hợp mệnh, hem nho qua, hem cut, dinh quy hoach, loi phong thuy, khong hop huong |
| troll_or_window_shopping | Bình luận dạo, hỏi cho biết hoặc trêu đùa trên mạng xã hội | -35 / — |  | hỏi cho biết, xem cho vui, vào ngắm thôi, ngắm cho đỡ thèm, đợi trúng số, đợi trúng vietlott, trúng vietlott mình mua, kiếp sau mua, bán thận mới mua được, tiền đâu mà mua, lấy gì mua, hoi cho biet, doi trung vietlott, tien dau ma mua |

## Spam / quảng cáo — `spam_registry.json`

| Nhóm | Mô tả | Điểm / mức | Family / điều kiện | Từ khóa / bí danh |
| --- | --- | --- | --- | --- |
| financial_loan | Quảng cáo cho vay tiền, tín dụng đen (đã tách khỏi câu hỏi vay ngân hàng của khách) | -100 / — | question_safe, safe_with_purchase | giải ngân 24h, giải ngân trong ngày, lãi suất thấp không thế chấp, hỗ trợ vay nợ xấu, hỗ trợ vay nhanh, nợ xấu vẫn vay, vay tiêu dùng, bốc bát họ, vay cmnd, vay cccd, cho vay tiền, cho vay vốn, bên em hỗ trợ vay vốn, nhận hỗ trợ vay, giải ngân siêu tốc, bao nợ xấu, vay tín chấp, vay góp ngày, rút tiền thẻ tín dụng |
| recruitment_scam | Tuyển dụng việc nhẹ lương cao, ctv, tuyển sale BĐS | -100 / — |  | tuyển dụng, việc làm tại nhà, kiếm tiền online, hoa hồng cao, ctv bán hàng, thu nhập 500k, thu nhập 1tr, tuyển mẫu, việc nhẹ, lương ngày, tuyển sale bđs, tuyển nhân viên kinh doanh, tuyển cộng tác viên, nhận việc về nhà làm |
| gambling_crypto | Cờ bạc, crypto, kéo tài xỉu, chứng khoán lừa đảo | -100 / — |  | crypto, tiền ảo, tài xỉu, lô đề, nhà cái, baccarat, kéo 1-1, kèo thơm, đầu tư sinh lời 30%, lợi nhuận cam kết, nhóm kéo, sàn forex |
| service_spam | Quảng cáo dịch vụ khác (sim, like, mỹ phẩm, thuốc) | -100 / — |  | bán sim, sim số đẹp, tăng tương tác, tăng like, mua view, thanh lý gấp, hàng tồn kho, mỹ phẩm, giảm cân, chữa trĩ, trị nám, chạy quảng cáo, xương khớp |
| competitor_hijacking | Môi giới khác hoặc chủ nhà vào bình luận ké bài, cướp khách | -100 / — | question_safe | ké chủ tus, ké chủ top, xin phép chủ tus, ké căn, ké lô, bên em có căn, bên mình có căn, em có căn tương tự, mình có căn gần đây, chính chủ cần bán, chính chủ gửi bán, cần bán gấp căn, cắt lỗ gấp căn, nhận ký gửi, ký gửi mua bán, tìm anh em môi giới, hợp tác môi giới, hoa hồng cho anh em, hh 1%, hh 2%, giỏ hàng giá f0, ke chu tus, ben em co can, chinh chu can ban, nhan ky gui, hop tac moi gioi, ben em co, ky gui |
| re_ancillary_services | Quảng cáo dịch vụ ăn theo BĐS (nội thất, chuyển nhà, lắp mạng, làm sổ) | -100 / — | question_safe | thiết kế nội thất, thi công nội thất, xưởng nội thất, báo giá nội thất, chuyển nhà trọn gói, chuyển văn phòng, xe tải chuyển nhà, xe ba gác, dọn vệ sinh công nghiệp, vệ sinh nhà mới, lắp đặt rèm cửa, giấy dán tường, lắp mạng viettel, lắp mạng fpt, lắp đặt wifi, lắp đặt camera, dịch vụ làm sổ, nhận làm sổ đỏ, nhận xóa thế chấp, đáo hạn ngân hàng, thiet ke noi that, thi cong noi that, chuyen nha tron goi, dich vu lam so |

## Địa điểm — `location_registry.json`

| Nhóm | Mô tả | Điểm / mức | Family / điều kiện | Từ khóa / bí danh |
| --- | --- | --- | --- | --- |
| Hồ Chí Minh | Hồ Chí Minh | Không cộng / — |  | hcm, tp hcm, sài gòn, saigon, sg, tphcm, tp.hcm, hồ chí minh, ho chi minh, sài thành |
| Hà Nội | Hà Nội | Không cộng / — |  | hà nội, ha noi, hn, thủ đô, tp hà nội |
| Thủ Đức | Thủ Đức | Không cộng / — |  | thủ đức, tp thủ đức, q thủ đức, quận 9, q9, quận 2, q2, thu duc, tp thu duc, quan 9, q.9, quan 2, q.2, thảo điền, thao dien, an phú, vạn phúc, cát lái |
| Bình Thạnh | Bình Thạnh | Không cộng / — |  | bình thạnh, q bình thạnh, bt, binh thanh, quận bình thạnh, q.bình thạnh |
| Gò Vấp | Gò Vấp | Không cộng / — |  | gò vấp, q gò vấp, gv, go vap, quận gò vấp, q.gò vấp |
| Tân Bình | Tân Bình | Không cộng / — |  | tân bình, q tân bình, tb, tan binh, quận tân bình, q.tân bình |
| Quận 1 | Quận 1 | Không cộng / — |  | quận 1, q1, q.1, quan 1, bến nghé, bến thành, đa kao |
| Quận 7 | Quận 7 | Không cộng / — |  | quận 7, q7, q.7, phú mỹ hưng, pmh, quan 7, phu my hung, tân phong, tân quy |
| Bình Dương | Bình Dương | Không cộng / — |  | bình dương, binh duong, dĩ an, thuận an, thủ dầu một, di an, thuan an, thu dau mot, tdm, bến cát, tân uyên |
| Đồng Nai | Đồng Nai | Không cộng / — |  | đồng nai, dong nai, biên hòa, nhơn trạch, long thành, bien hoa, nhon trach, long thanh, long bình, long binh, trảng bom |
| Tân Phú | Tân Phú | Không cộng / — |  | tân phú, tan phu, q tân phú, quận tân phú, q.tân phú, tp |
| Bình Tân | Bình Tân | Không cộng / — |  | bình tân, binh tan, q bình tân, quận bình tân, q.bình tân, bình trị đông, tên lửa |
| Quận 12 | Quận 12 | Không cộng / — |  | quận 12, quan 12, q12, q.12, thới an, thạnh xuân, thạnh lộc, hiệp thành |
| Hóc Môn | Hóc Môn | Không cộng / — |  | hóc môn, hoc mon, huyện hóc môn, bà điểm, xuân thới thượng |
| Quận 3 | Quận 3 | Không cộng / — |  | quận 3, quan 3, q3, q.3 |
| Phú Nhuận | Phú Nhuận | Không cộng / — |  | phú nhuận, phu nhuan, q phú nhuận, quận phú nhuận, pn |
| Quận 8 | Quận 8 | Không cộng / — |  | quận 8, quan 8, q8, q.8, tạ quang bửu, phạm thế hiển |
| Quận 10 | Quận 10 | Không cộng / — |  | quận 10, quan 10, q10, q.10 |
| Bình Chánh | Bình Chánh | Không cộng / — |  | bình chánh, binh chanh, huyện bình chánh, bc, trung sơn, vĩnh lộc |
| Nhà Bè | Nhà Bè | Không cộng / — |  | nhà bè, nha be, huyện nhà bè, phước kiển, nhơn đức |
| Củ Chi | Củ Chi | Không cộng / — |  | củ chi, cu chi, huyện củ chi |
| Bà Rịa - Vũng Tàu | Bà Rịa - Vũng Tàu | Không cộng / — |  | vũng tàu, vung tau, bà rịa, ba ria, brvt, côn đảo, con dao, phú mỹ, hồ tràm, ho tram, long hải |
| Long An | Long An | Không cộng / — |  | long an, đức hòa, duc hoa, bến lức, ben luc, cần giuộc, can giuoc, tân an |

Các biểu thức xử lý DM, từ chối liên hệ và từ bổ sung mức độ nằm trong `variants_registry.json`. Địa điểm chỉ dùng nhận diện khu vực, không cộng điểm. Sửa JSON khi chạy source; build lại để cập nhật EXE. Xem [hướng dẫn sử dụng](LEAD_FILTER.md).
