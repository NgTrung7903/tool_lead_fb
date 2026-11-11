# Đối chiếu nguồn registry bổ sung — registry 1.3.0

Đã đọc đủ 5 file JSON và hợp nhất với registry hiện có. Giữ nguyên file gốc, các luật DM/phủ định trước đây và cách xử lý comment ẩn danh. [Danh sách nguồn và SHA256](REGISTRY_IMPORT_SOURCES.json) dùng để đối chiếu đầu vào.

| Nội dung bổ sung | Cách áp dụng |
| --- | --- |
| Chủ động để lại liên hệ | Nhóm contact_sharing mạnh, +45; cần cụm liên hệ và thông tin liên hệ hợp lệ từ bộ trích xuất. “Số mình” đứng riêng không đủ. SĐT vẫn có điểm liên hệ +50 riêng. |
| Mua/chốt/cọc, hẹn xem | Mức mạnh; +40 mua, +35 xem. Có phủ định vẫn xét trước khi cộng ý định. |
| Trả giá, thương lượng | Mức mạnh, tối đa +30 cho họ giá; không cộng thêm điểm hỏi giá/giá bn cho cùng tín hiệu. Đứng riêng vẫn cần xem lại. |
| Hỏi chi tiết, tiêu chí căn nhà, tư vấn | Mức vừa; chi tiết/tiêu chí +25, trao đổi +20. Hai họ vừa độc lập có thể đủ điều kiện lead; nhiều từ đồng nghĩa không tính thành nhiều nhu cầu. |
| “Còn không?”, hỏi giá đơn giản | Mức yếu, +15; tách khỏi ý định mua trực tiếp. |
| “Chấm”, “hóng”, tương tác xã hội | Mức yếu, +10; đứng riêng chưa đủ nhu cầu giao dịch. |
| SHR, HXH, MT, PN, pháp lý, vị trí | Bổ sung 3 nhóm biến thể. Pháp lý/đặc điểm mức vừa; vị trí mức yếu. Cùng họ chi tiết lấy điểm cao nhất. |
| Chỉ tìm thuê, cần bán | Chuyển Cần xem lại, ghi nhu cầu khác loại tin; không tự coi là spam hay xác nhận người mua. Từ chối thuê để mua không bị gán nhu cầu thuê. |
| Quy hoạch, ngập, hẻm cụt, phong thủy | Tách câu hỏi/đặc điểm được phủ định khỏi lời chê thực sự. Có quan tâm nhưng nêu nhược điểm chuyển xem lại. |
| “Hỏi cho biết”, đợi trúng số, trêu đùa | Bổ sung nhóm bình luận dạo, trừ 35; câu đứng riêng bị bỏ qua. |
| Môi giới chen tin, quảng cáo dịch vụ liên quan BĐS | Hai nhóm spam riêng; dùng cụm chào bán cụ thể, tránh loại chỉ vì từ “ké”, “hoa hồng”. |
| Vay ngân hàng và quảng cáo vay | Câu hỏi vay mua nhà không tự thành spam; quảng cáo giải ngân/chào vay vẫn bị loại. Câu hỏi dịch vụ chưa rõ nhu cầu BĐS chuyển xem lại. |
| Địa điểm | Hợp nhất bí danh mới và cũ thành 23 nhóm; không cộng điểm; khớp theo ranh giới từ để tránh Quận 1 khớp Quận 10. |

Không nhập nguyên nhóm `spam_and_negative` thành ý định dương: nhóm nguồn này trộn nhu cầu thuê, quảng cáo và từ chối. Các nội dung được chuyển về nhóm phù hợp. Regex số điện thoại trong đầu vào được thay bằng bộ trích xuất/kiểm tra liên hệ hiện có, tránh cộng điểm cho chuỗi số không hợp lệ.

Các cụm nguồn không giữ làm luật loại độc lập: `ké`, `em có căn`, `bên em có`, `mình có căn`, `hoa hồng`, `nhận thiết kế`, `hỗ trợ vay vốn`, `không thế chấp`. Thay bằng cụm quảng cáo rõ hơn hoặc quy tắc câu hỏi/ngữ cảnh. Ngoài các điều chỉnh này, toàn bộ từ khóa/bí danh đầu vào đã có trong registry hợp nhất.

Tổng cộng: **10 nhóm ý định, 9 nhóm biến thể, 6 nhóm phủ định/nhu cầu khác, 6 nhóm spam và 23 nhóm địa điểm**. [Danh sách đầy đủ từ và trọng số](REGISTRIES.md).

Engine giới hạn điểm theo họ tín hiệu (`family`). Không có SĐT thì điểm từ 40 còn cần ý định hành động hoặc ít nhất hai họ mức vừa/mạnh độc lập; cộng nhiều từ yếu không tự thành lead. Kết quả cũ được chấm lại khi hiển thị/xuất theo phiên bản mới; không ghi đè snapshot gốc.

Các kiểm thử trong `tests/test_new_folder_registry.py` bao gồm ví dụ mới, phản ví dụ, điểm không cộng trùng, bí danh địa điểm và tính nguyên vẹn 5 file nguồn. Kiểm thử offline không xác nhận khả năng lấy dữ liệu từ Facebook thật.
