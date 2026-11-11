# Tóm tắt từng function

> Tài liệu lưu trữ trước đợt sắp xếp 02/11/2026. Nội dung và số dòng mô tả phiên bản cũ; xem [kiến trúc hiện tại](../ARCHITECTURE.md) và [báo cáo rà soát](../PROJECT_REVIEW.md).

**Bổ sung Facebook 4.0:** `WebsiteSourceService` nhập nguồn JSON/JSON-LD và lưu ảnh snapshot; `SnapshotProvider` cấp dữ liệu đã duyệt cho `CampaignService.create_campaign()`; các endpoint `/api/workflow/*` tạo campaign và chuyển bài đã xác nhận sang `LeadFilterService` có thông tin căn/nhóm/chiến dịch. `workflow.js` điều khiển giao diện chung. Đọc [hướng dẫn luồng Facebook](../FACEBOOK_WORKFLOW.md); danh mục thống kê lịch sử bên dưới chưa tính phần bổ sung này.

**Bổ sung 29/10/2026:** Luồng chính mới và các module `facebook_comment_collector.py`, `lead_filter_service.py`, `leads.js` được mô tả trong [LEAD_FILTER.md](../LEAD_FILTER.md). Danh mục dưới đây là bản thống kê luồng đăng bài/xuất báo cáo trước khi chuyển giao diện chính; số hàm cuối tài liệu không bao gồm phần bổ sung này.

Danh mục theo mã nguồn ngày 28/10/2026. Bao gồm hàm public, private, property và hàm lồng có tên trong mã ứng dụng; JavaScript gồm các callback khởi tạo/ủy quyền sự kiện. Các lambda/callback map thuần biến đổi từng phần tử được giải thích trong hàm chứa chúng. Phụ lục liệt kê mọi hàm kiểm thử và helper có tên.

Tên bắt đầu bằng `_` thường dành cho nội bộ. `__init__` khởi tạo đối tượng; `__enter__`/`__exit__` hỗ trợ cú pháp `with`. Hàm tồn tại không đồng nghĩa nó được nối vào dashboard. Đọc [PROJECT_FLOW.md](PROJECT_FLOW_2026-10.md) để biết đường gọi thực tế và [CODE_REVIEW.md](CODE_REVIEW_2026-10-28.md) để biết hạn chế.

## cli.py

| Function | Tóm tắt |
|---|---|
| [main](../../cli.py) | Đọc tham số CLI, tạo service và chọn tác vụ server/login/status/list/post/retry/logout; lệnh post chạy đồng bộ. |

## desktop_launcher.py

| Function | Tóm tắt |
|---|---|
| [configure_runtime](../../desktop_launcher.py) | Chọn dữ liệu khách bền vững và đường dẫn browser trong gói frozen trước khi import các service. |
| [offline_self_test](../../desktop_launcher.py) | Kiểm assets, registry, SQLite, Excel và Chromium offline của bản EXE; ghi JSON kết quả. |
| [main](../../desktop_launcher.py) | Entry point EXE: chọn khách/cổng, khóa dashboard, mở server/trình duyệt hoặc chạy self-test offline. |
| [main.open_dashboard](../../desktop_launcher.py) | Chờ server khởi động rồi mở dashboard trong trình duyệt mặc định. |

## config/settings.py

| Function | Tóm tắt |
|---|---|
| [load_config](../../config/settings.py) | Đọc JSON, ghép giá trị mặc định; nếu chưa có file thì tạo; file hỏng sẽ phát sinh lỗi. |
| [save_config](../../config/settings.py) | Ghi cấu hình JSON nguyên tử bằng atomic_json. |

## models/schema.py

| Function | Tóm tắt |
|---|---|
| [utc_now_iso](../../models/schema.py) | Trả thời gian UTC hiện tại dưới dạng chuỗi ISO để lưu lịch sử. |

## core/contact_extractor.py

| Function | Tóm tắt |
|---|---|
| [normalize_phone](../../core/contact_extractor.py) | Loại dấu phân cách, đổi +84/84 về 0 và kiểm tra số di động theo danh sách prefix. |
| [extract_contacts](../../core/contact_extractor.py) | Trích danh sách điện thoại, số chính, email, Zalo và cờ có thông tin liên hệ. |

## core/dedup.py

| Function | Tóm tắt |
|---|---|
| [generate_comment_hash](../../legacy/dedup.py) | Băm ID tin, ID người dùng và nội dung chuẩn hóa nhẹ để phát hiện bình luận trùng. |
| [generate_lead_dedup_key](../../legacy/dedup.py) | Tạo khóa theo ID căn và điện thoại; nếu thiếu thì dùng Facebook user hoặc unknown. |

## core/filter_engine.py

| Function | Tóm tắt |
|---|---|
| [RegistryFilterEngine.__init__](../../core/filter_engine.py) | Nhận thư mục registry và nạp các bộ quy tắc. |
| [RegistryFilterEngine._load_registries](../../core/filter_engine.py) | Đọc năm registry JSON vào cấu hình ý định, biến thể, phủ định, spam và địa điểm. |
| [RegistryFilterEngine.normalize_text](../../core/filter_engine.py) | Chuẩn hóa khoảng trắng để so sánh; bản trong core còn lowercase và chuẩn Unicode NFC. |
| [RegistryFilterEngine._find_matches](../../core/filter_engine.py) | Tìm từ khóa trong nội dung; áp ranh giới từ cho token ngắn để hạn chế khớp nhầm. |
| [RegistryFilterEngine.evaluate](../../core/filter_engine.py) | Tách liên hệ, tìm spam/phủ định/ý định, tính điểm và trả phân loại cùng lý do, signals, version. |

## services/browser_manager.py

| Function | Tóm tắt |
|---|---|
| [BrowserLeadManager.__init__](../../legacy/browser_manager.py) | Khởi tạo bộ lọc và tạo hai thư mục profile cũ trong project. |
| [BrowserLeadManager.open_facebook_login](../../legacy/browser_manager.py) | Nhánh cũ: mở profile Facebook riêng trong browser_data, đợi 30 giây và trả thông báo lưu; không xác minh login đầy đủ. |
| [BrowserLeadManager.open_revoland_login](../../legacy/browser_manager.py) | Nhánh cũ: mở trang Revoland để khách đăng nhập, chờ rồi đóng context và trả kết quả. |
| [BrowserLeadManager.crawl_and_extract_comments](../../legacy/browser_manager.py) | Nhánh cũ: mở URL, cuộn và lấy text qua selector; trả bản ghi thô, chưa bảo đảm mỗi bản ghi là bình luận. |
| [BrowserLeadManager.process_and_export_leads](../../legacy/browser_manager.py) | Phân loại bản ghi thô, đếm từng loại và xuất Excel; không gọi API tạo lead. |

## services/campaign_service.py

| Function | Tóm tắt |
|---|---|
| [CampaignService.__init__](../../services/campaign_service.py) | Nhận các service phụ thuộc, tạo SQLite/khóa và chạy migrate/phục hồi nếu không có job khác. |
| [CampaignService._db](../../services/campaign_service.py) | Mở kết nối SQLite, commit/rollback transaction rồi đóng kết nối khi ra khỏi with. |
| [CampaignService._save](../../services/campaign_service.py) | Insert hoặc update toàn bộ campaign dạng JSON theo ID trong SQLite. |
| [CampaignService._migrate_legacy](../../services/campaign_service.py) | Nhập lịch sử JSON cũ một lần; chuyển kết quả thành công/running cũ về unknown và giữ file gốc. |
| [CampaignService._recover](../../services/campaign_service.py) | Tìm lần chạy bị gián đoạn; task đã bắt đầu gửi thành unknown, chưa bắt đầu gửi thành failed. |
| [CampaignService.get_campaign](../../services/campaign_service.py) | Đọc một campaign từ SQLite, dựng model Pydantic; không có thì trả None. |
| [CampaignService.list_campaigns](../../services/campaign_service.py) | Đọc toàn bộ campaign theo thứ tự bản ghi mới trước và trả danh sách model. |
| [CampaignService._prior](../../services/campaign_service.py) | Tìm kết quả cùng ID căn và URL nhóm trong các campaign khác; bỏ qua nguồn mock. |
| [CampaignService.create_campaign](../../services/campaign_service.py) | Kiểm tra căn/nhóm/preview/nội dung, chống trùng, tải đủ ảnh, tạo tasks và lưu campaign. |
| [CampaignService.busy](../../services/campaign_service.py) | Property kiểm tra khóa runner trong tiến trình có đang bị giữ hay không. |
| [CampaignService.start_campaign](../../services/campaign_service.py) | Lấy cả khóa runner và khóa file, đọc trạng thái mới nhất rồi đặt queued và chạy worker nền. |
| [CampaignService.start_campaign.worker](../../services/campaign_service.py) | Worker nền: chạy campaign, giữ kết quả gián đoạn và trả khóa khi xong. |
| [CampaignService._validate_run](../../services/campaign_service.py) | Kiểm tra campaign tồn tại, nguồn live và không có task unknown; trả campaign hoặc báo lỗi. |
| [CampaignService.execute_campaign](../../services/campaign_service.py) | Đăng campaign đồng bộ cho CLI; lấy khóa runner, gọi _run và giải phóng khóa. |
| [CampaignService.retry_failed_tasks](../../services/campaign_service.py) | Chạy đồng bộ chỉ những task failed/action_required; bỏ các trạng thái khác. |
| [CampaignService._run](../../services/campaign_service.py) | Điều phối task lần lượt, kiểm tra lại chống trùng, lưu mốc trước gửi, gọi engine, cập nhật và tổng hợp kết quả. |
| [CampaignService._run.before_submit](../../services/campaign_service.py) | Callback lưu submission_started=True trước click để phục hồi an toàn khi app dừng. |
| [CampaignService._summarize](../../services/campaign_service.py) | Tính trạng thái campaign từ trạng thái các task: needs_review/paused/partial_failed/completed. |
| [CampaignService.resolve_task](../../services/campaign_service.py) | Nhận kết quả khách xác minh unknown/chờ duyệt; kiểm permalink khi posted và cập nhật lịch sử. |

## services/comment_pipeline.py

| Function | Tóm tắt |
|---|---|
| [CommentPipeline.__init__](../../legacy/comment_pipeline.py) | Tạo bộ lọc, client Revoland và kho comments/review/leads/hash trong RAM. |
| [CommentPipeline.ingest_comment](../../legacy/comment_pipeline.py) | Chống trùng, phân loại bình luận và tạo lead hoặc mục hàng chờ; lưu dữ liệu trong RAM. |
| [CommentPipeline.approve_review_item](../../legacy/comment_pipeline.py) | Duyệt mục pending, gọi Revoland tạo lead, chỉ chuyển approved khi API báo thành công. |
| [CommentPipeline.reject_review_item](../../legacy/comment_pipeline.py) | Đánh dấu mục hàng chờ bị từ chối và lưu người/lý do/thời gian xử lý. |
| [CommentPipeline.list_review_queue](../../legacy/comment_pipeline.py) | Trả hàng chờ theo status, ghép tên khách/nội dung/điểm từ bình luận gốc. |
| [CommentPipeline.list_leads](../../legacy/comment_pipeline.py) | Trả các lead nội bộ dưới dạng dictionary; dữ liệu mất khi tiến trình tắt. |

## services/excel_exporter.py

| Function | Tóm tắt |
|---|---|
| [_append_literal_row](../../services/excel_exporter.py) | Ghi chuỗi dưới dạng text, bỏ ký tự XML không hợp lệ và chặn ô vượt giới hạn để tránh mất dữ liệu/formula injection. |
| [_save_workbook](../../services/excel_exporter.py) | Lưu workbook vào đường dẫn hoặc stream; tạo thư mục cha cho đường dẫn. |
| [export_records_to_excel](../../services/excel_exporter.py) | Ghi các bản ghi vào XLSX, tạo cột, màu, border và wrap text; trả đường dẫn file. |
| [export_campaigns_to_excel](../../services/excel_exporter.py) | Xuất một dòng mỗi task với trạng thái nguồn/campaign/nhóm, URL, lỗi, retry, thời gian và bằng chứng. |
| [workbook_bytes](../../services/excel_exporter.py) | Chạy exporter vào BytesIO và trả bytes XLSX cho HTTP download. |

## services/facebook_browser.py

| Function | Tóm tắt |
|---|---|
| [profile_operation](../../services/facebook_browser.py) | Tạo khóa file nằm ngoài thư mục profile để login/check/post/logout không mở cùng profile. |
| [authenticated](../../services/facebook_browser.py) | Kiểm domain/URL, cookie c_user, dấu hiệu giao diện và sự vắng mặt ô login để trả bool. |
| [launch_context](../../services/facebook_browser.py) | Tắt lưu mật khẩu trong Preferences rồi mở Chromium persistent theo thư mục profile. |

## services/facebook_service.py

| Function | Tóm tắt |
|---|---|
| [FacebookService.__init__](../../legacy/facebook_service.py) | Nhận token tùy chọn, tạo kho nhóm/task trong RAM và thêm nhóm mẫu. |
| [FacebookService._init_default_groups](../../legacy/facebook_service.py) | Nhánh manual-assisted cũ: khởi tạo nhóm mẫu vào RAM. |
| [FacebookService.list_groups](../../legacy/facebook_service.py) | Trả danh sách nhóm; GroupManager đọc lại JSON và có lọc active, FacebookService cũ chỉ đọc RAM. |
| [FacebookService.add_group](../../legacy/facebook_service.py) | Thêm nhóm; GroupManager lấy khóa/chuẩn hóa/chặn trùng và ghi JSON, nhánh cũ chỉ lưu RAM. |
| [FacebookService.create_distribution_campaign](../../legacy/facebook_service.py) | Nhánh cũ: tạo PostingTask cho nhóm đã chọn, trạng thái manual_ready hoặc pending. |
| [FacebookService.get_assisted_post_payload](../../legacy/facebook_service.py) | Nhánh cũ: trả nội dung định dạng, URL nhóm và ảnh để người dùng copy/đăng tay. |
| [FacebookService.mark_task_posted](../../legacy/facebook_service.py) | Nhánh cũ: đánh dấu task posted và lưu URL/ID/thời gian do người gọi cung cấp; không xác minh bằng trình duyệt. |

## services/group_manager.py

| Function | Tóm tắt |
|---|---|
| [normalize_group_url](../../services/group_manager.py) | Chấp nhận một số hostname Facebook và đường dẫn nhóm, chuẩn hóa HTTPS/www và bỏ query. |
| [GroupManager.__init__](../../services/group_manager.py) | Chọn file groups.json và nạp dữ liệu. |
| [GroupManager._load_groups](../../services/group_manager.py) | Đọc JSON nhóm vào dictionary; file chưa có thì tạo danh sách rỗng; file lỗi thì báo lỗi. |
| [GroupManager._save_to_disk](../../services/group_manager.py) | Lưu danh sách nhóm qua atomic_json. |
| [GroupManager.list_groups](../../services/group_manager.py) | Trả danh sách nhóm; GroupManager đọc lại JSON và có lọc active, FacebookService cũ chỉ đọc RAM. |
| [GroupManager.get_group_by_id](../../services/group_manager.py) | Đọc lại danh sách nhóm từ file rồi tìm theo ID nội bộ. |
| [GroupManager.add_group](../../services/group_manager.py) | Thêm nhóm; GroupManager lấy khóa/chuẩn hóa/chặn trùng và ghi JSON, nhánh cũ chỉ lưu RAM. |
| [GroupManager._add_group](../../services/group_manager.py) | Sau khi đã lấy khóa: kiểm tên/URL/trùng, tạo ID nhóm và ghi danh sách. |
| [GroupManager.update_group](../../services/group_manager.py) | Lấy khóa, đọc bản mới và gọi _update_group; hiện không có endpoint chỉnh nhóm tương ứng. |
| [GroupManager._update_group](../../services/group_manager.py) | Ghép thuộc tính mới, chuẩn hóa URL/chặn trùng, dựng model và lưu lại. |
| [GroupManager.delete_group](../../services/group_manager.py) | Lấy khóa và đọc lại dữ liệu trước khi xóa nhóm. |
| [GroupManager._delete_group](../../services/group_manager.py) | Xóa ID nhóm trong dictionary và lưu JSON; trả bool có tìm thấy hay không. |
| [GroupManager.import_groups_from_text](../../services/group_manager.py) | Trích URL theo dòng, kiểm tra toàn bộ, loại trùng và lưu một lần dưới khóa file. |

## services/poster_engine.py

| Function | Tóm tắt |
|---|---|
| [post_permalink](../../services/poster_engine.py) | Chấp nhận permalink posts/ID hoặc permalink/ID đúng nhóm Facebook rồi trả URL chuẩn; sai trả None. |
| [normalize_text](../../services/poster_engine.py) | Chuẩn hóa khoảng trắng để so sánh; bản trong core còn lowercase và chuẩn Unicode NFC. |
| [confirmed_post](../../services/poster_engine.py) | Tìm article có đủ nội dung, permalink chưa thấy trước đó và timestamp Vừa xong/Just now. |
| [composer_images](../../services/poster_engine.py) | Chụp danh tính ảnh trong composer, nhận diện tile có nút gỡ ảnh và kiểm tra ảnh đã decode/hiển thị. |
| [uploaded_images_ready](../../services/poster_engine.py) | Chỉ chấp nhận đúng số ảnh đính kèm mới so với baseline, tất cả đã tải và không còn UI bận. |
| [FacebookPosterEngine.__init__](../../services/poster_engine.py) | Chọn profile, đọc cấu hình và đặt timeout upload/xác nhận. |
| [FacebookPosterEngine.post_to_single_group](../../services/poster_engine.py) | Mở nhóm bằng phiên khách, nhập nội dung, gắn ảnh, lưu mốc gửi rồi quan sát kết quả; không sinh thành công giả. |
| [FacebookPosterEngine.post_to_single_group.result](../../services/poster_engine.py) | Hàm lồng trong poster: dựng GroupTaskResult nhất quán với trạng thái, thông báo, URL và bằng chứng. |

## services/report_service.py

| Function | Tóm tắt |
|---|---|
| [parse_comment_records](../../services/report_service.py) | Nhận mảng hoặc records/comments, validate giới hạn và phân biệt bình luận với lead thiếu text gốc. |
| [load_comment_json](../../services/report_service.py) | Đọc JSON UTF-8/BOM tối đa 5 MB từ file CLI rồi validate bản ghi. |
| [prepare_comment_report](../../services/report_service.py) | Chấm điểm bình luận bằng registry, giữ liên hệ/trạng thái lead nhập và dựng bản ghi báo cáo; không gọi API. |
| [campaign_report_data](../../services/report_service.py) | Lấy toàn bộ lịch sử hoặc một campaign theo ID, báo lỗi nếu không có campaign đó. |
| [campaign_report_bytes](../../services/report_service.py) | Tạo XLSX kết quả đăng bài từ snapshot campaign của khách. |
| [comment_report_bytes](../../services/report_service.py) | Validate, phân loại bình luận/lead JSON và tạo XLSX trong bộ nhớ. |

## services/revoland_client.py

| Function | Tóm tắt |
|---|---|
| [RevolandClient.__init__](../../legacy/revoland_client.py) | Nhận URL/key/chế độ mock từ tham số hoặc biến môi trường; tạo cache lead trong RAM. |
| [RevolandClient.create_or_update_lead](../../legacy/revoland_client.py) | Nhánh thử nghiệm: dedup trong RAM, tạo lead mock hoặc POST /leads; nhánh cache chưa thực sự update (R6). |

## services/revoland_service.py

| Function | Tóm tắt |
|---|---|
| [RevolandService.__init__](../../services/revoland_service.py) | Đọc cấu hình Revoland dùng cho lấy căn và định dạng bài. |
| [RevolandService.update_config](../../services/revoland_service.py) | Cập nhật những key cấu hình đã biết, lưu file và trả model RevolandConfig; dashboard đang dùng handler riêng. |
| [RevolandService.test_connection](../../services/revoland_service.py) | Mock trả trạng thái mẫu; live gọi GET /ping và trả kết quả kết nối, không lộ response body. |
| [RevolandService.get_listings](../../services/revoland_service.py) | Lấy mẫu hoặc GET /listings theo trang, chuẩn hóa envelope, validate model, loại ID trùng; lỗi live không fallback. |
| [RevolandService.get_listing_by_id](../../services/revoland_service.py) | Gọi lại get_listings rồi tìm ID; hiện chưa gọi endpoint detail riêng. |
| [RevolandService.format_post_content](../../services/revoland_service.py) | Ghép tiêu đề, vị trí, giá, thông số, pháp lý nếu có, mô tả, liên hệ và link thành nội dung bài. |
| [RevolandService.download_listing_images](../../services/revoland_service.py) | Tải mọi ảnh vào snapshot riêng, giới hạn bytes, đọc bằng Pillow, sửa hướng và lưu JPEG; lỗi ảnh chặn chiến dịch. |

## services/session_manager.py

| Function | Tóm tắt |
|---|---|
| [FacebookSessionManager.__init__](../../services/session_manager.py) | Chọn profile, tạo khóa login và nơi giữ kết quả login gần nhất. |
| [FacebookSessionManager._status](../../services/session_manager.py) | Dựng SessionStatus gồm xác thực, mô tả, busy, trạng thái login và kết quả login gần nhất. |
| [FacebookSessionManager.check_session_status](../../services/session_manager.py) | Lấy khóa profile, mở Facebook headless nếu có dữ liệu và gọi authenticated; bận/lỗi trả trạng thái rõ. |
| [FacebookSessionManager.start_login](../../services/session_manager.py) | Lấy khóa login trong tiến trình rồi khởi chạy thread chờ khách đăng nhập. |
| [FacebookSessionManager.start_login.worker](../../services/session_manager.py) | Worker nền: chờ login, lưu kết quả và trả khóa login khi xong. |
| [FacebookSessionManager.open_interactive_login](../../services/session_manager.py) | Phiên bản login đồng bộ dùng cho CLI; giữ khóa cho đến khi hoàn tất/hết thời gian. |
| [FacebookSessionManager._interactive](../../services/session_manager.py) | Giữ khóa profile, mở Facebook có cửa sổ, đợi xác thực và luôn đóng context; trả success/message. |
| [FacebookSessionManager.logout_and_clear_session](../../services/session_manager.py) | Chặn lúc login, lấy khóa profile và xóa thư mục phiên; không báo thành công nếu xóa lỗi. |

## services/storage.py

| Function | Tóm tắt |
|---|---|
| [atomic_json](../../services/storage.py) | Ghi JSON vào file tạm cùng thư mục, flush/fsync rồi os.replace để tránh file ghi dở. |
| [ExclusiveOperation.__init__](../../services/storage.py) | Tạo khóa file không phụ thuộc thread để có thể bàn giao từ request sang worker. |
| [ExclusiveOperation.__enter__](../../services/storage.py) | Thử lấy FileLock ngay; nếu đang bận thì đổi Timeout thành ResourceBusyError. |
| [ExclusiveOperation.__exit__](../../services/storage.py) | Giải phóng khóa file sau thao tác hoặc sau exception. |

## api/server.py

| Function | Tóm tắt |
|---|---|
| [protect_local_api](../../api/server.py) | Kiểm Origin và header thao tác; gắn no-store, nosniff và no-referrer vào response đi qua middleware. |
| [revoland_error](../../api/server.py) | Đổi RevolandAPIError thành response HTTP 502 và detail dễ hiển thị. |
| [busy_error](../../api/server.py) | Đổi ResourceBusyError thành HTTP 409 để giao diện biết tài nguyên đang bận. |
| [validation_error](../../api/server.py) | Đổi ValueError thành HTTP 400 với detail. |
| [public_config](../../api/server.py) | Bỏ API key và đường dẫn profile khỏi cấu hình trả về; thêm cờ đã cấu hình key. |
| [serve_dashboard](../../api/server.py) | Trả file HTML dashboard tại / hoặc trang fallback khi chưa có file. |
| [serve_javascript](../../api/server.py) | Trả JavaScript điều khiển giao diện tại /assets/app.js. |
| [get_system_config](../../api/server.py) | GET /api/config: trả cấu hình đã lọc dữ liệu nhạy cảm. |
| [update_system_config](../../api/server.py) | POST /api/config: kiểm tra bận, validate cấu hình, lưu và cập nhật service trong tiến trình. |
| [test_revoland_connection](../../api/server.py) | POST kiểm tra kết nối: chuyển tiếp lời gọi tới RevolandService.test_connection. |
| [get_revoland_listings](../../api/server.py) | GET danh sách căn: gọi service và chuyển model sang JSON. |
| [get_revoland_listing_detail](../../api/server.py) | GET một căn: tìm theo ID, trả JSON hoặc HTTP 404. |
| [preview_listing_post](../../api/server.py) | GET preview: trả căn, nội dung định dạng, URL ảnh và hash JSON làm preview_token. |
| [get_session_status](../../api/server.py) | GET trạng thái phiên: gọi SessionManager và trả JSON. |
| [open_fb_login](../../api/server.py) | POST login: chặn khi campaign bận, mở worker login rồi trả thông báo đã bắt đầu. |
| [clear_fb_session](../../api/server.py) | POST logout: chặn khi campaign bận và yêu cầu SessionManager xóa phiên. |
| [get_groups](../../api/server.py) | GET danh sách nhóm: trả model nhóm dạng JSON. |
| [add_group](../../api/server.py) | POST thêm nhóm: chuyển tên/URL/phân loại/ghi chú tới GroupManager. |
| [delete_group](../../api/server.py) | DELETE nhóm theo ID: gọi GroupManager và trả success hoặc 404. |
| [import_groups](../../api/server.py) | POST import: chuyển raw_text cho GroupManager, trả số nhóm mới. |
| [create_posting_campaign](../../api/server.py) | POST tạo campaign: nhận DTO gồm preview_token, gọi service và trả campaign hoặc lỗi nhập liệu. |
| [execute_posting_campaign](../../api/server.py) | POST execute: chặn khi login đang mở, đặt lịch campaign nền và trả trạng thái queued. |
| [retry_failed_campaign_tasks](../../api/server.py) | POST retry: tương tự execute nhưng đặt chế độ chỉ retry nhóm lỗi/cần thao tác. |
| [list_campaigns](../../api/server.py) | GET lịch sử: chuyển danh sách model campaign từ service sang JSON. |
| [get_campaign_detail](../../api/server.py) | GET campaign theo ID: trả JSON hoặc 404. |
| [resolve_task](../../api/server.py) | POST xác minh: bắt buộc confirmed rồi chuyển kết quả khách kiểm tra tới CampaignService. |
| [excel_response](../../api/server.py) | Trả XLSX dạng response tải file với tên và media type phù hợp. |
| [export_campaign_results](../../api/server.py) | GET báo cáo một hoặc mọi campaign; trả 404 khi ID không tồn tại. |
| [download_comment_example](../../api/server.py) | GET file JSON bình luận mẫu để người dùng thử nhập/xuất. |
| [export_comment_results](../../api/server.py) | POST nhận JSON bình luận/lead, lọc và trả file Excel; không tạo lead hoặc lưu input lên server. |

## api/static/app.js

| Function/callback | Tóm tắt |
|---|---|
| [byId](../../api/static/app.js) | Lấy phần tử DOM theo ID. |
| [escapeHtml](../../api/static/app.js) | Escape ký tự HTML trước khi ghép dữ liệu vào template giao diện. |
| [safeUrl](../../api/static/app.js) | Chỉ giữ URL HTTP(S) hợp lệ rồi escape để dùng trong thuộc tính HTML. |
| [api](../../api/static/app.js) | Gọi fetch cùng header của tool, parse JSON và ném lỗi có thông điệp khi response không hợp lệ. |
| [updateButtons](../../api/static/app.js) | Bật/tắt nút đăng theo phiên, mock mode, campaign đang chạy và căn được chọn; cập nhật banner. |
| [checkSessionStatus](../../api/static/app.js) | Lấy trạng thái phiên, cập nhật nhãn/nút và tiếp tục poll khi login còn mở. |
| [triggerFbLogin](../../api/static/app.js) | Gọi endpoint mở login, đánh dấu bận và lên lịch kiểm tra trạng thái. |
| [logoutFbSession](../../api/static/app.js) | Xin xác nhận trong giao diện, gọi xóa phiên và kiểm tra lại. |
| [loadMode](../../api/static/app.js) | Đọc cấu hình công khai và cập nhật cờ mock mode. |
| [loadRevolandListings](../../api/static/app.js) | Xóa preview cũ, tải chế độ/danh sách, dựng thẻ căn và tự chọn căn đầu. |
| [selectListing](../../api/static/app.js) | Lấy preview căn, chống response về sai thứ tự bằng generation, cập nhật nội dung/ảnh/token. |
| [loadGroups](../../api/static/app.js) | Tải nhóm và dựng checkbox, tên, URL, phân loại và nút xóa. |
| [toggleAllCheckboxes](../../api/static/app.js) | Chuyển trạng thái checkbox tổng cho selectAllGroups. |
| [selectAllGroups](../../api/static/app.js) | Chọn hoặc bỏ chọn các checkbox nhóm chưa disabled. |
| [deleteGroup](../../api/static/app.js) | Xin xác nhận, gọi DELETE nhóm và tải lại danh sách. |
| [startPostingCampaign](../../api/static/app.js) | Chụp căn/nhóm/nội dung/token đang chọn, tạo campaign rồi gọi thực thi và cuộn tới kết quả. |
| [runCampaign](../../api/static/app.js) | Gọi execute hoặc retry cho campaign đang chọn; nhận queued rồi bắt đầu theo dõi. |
| [retryFailedGroups](../../api/static/app.js) | Gọi runCampaign với cờ retry=true. |
| [scheduleCampaignPoll](../../api/static/app.js) | Hủy timer trước và đặt lần đọc tiến độ kế tiếp sau một giây. |
| [pollCampaign](../../api/static/app.js) | Đọc campaign, cập nhật UI; poll khi đang chạy, đọc lại lịch sử/phiên khi xong; mất mạng thì thử kết nối lại. |
| [renderCampaignResults](../../api/static/app.js) | Dựng bảng trạng thái/URL/lý do và hiển thị nút retry/tiếp tục/xác minh theo từng trạng thái. |
| [resolveTask](../../api/static/app.js) | Hỏi khách kết quả kiểm tra, yêu cầu permalink nếu posted và gửi xác nhận thủ công lên API. |
| [loadHistory](../../api/static/app.js) | Đọc các campaign và dựng dropdown lịch sử. |
| [selectHistory](../../api/static/app.js) | Không đổi khi campaign đang chạy; chọn ID lịch sử và tải kết quả. |
| [openConfigModal](../../api/static/app.js) | Nạp cấu hình công khai vào form; key để trống và có placeholder giữ key cũ. |
| [closeConfigModal](../../api/static/app.js) | Ẩn modal cấu hình và thông báo kiểm tra kết nối. |
| [configPayload](../../api/static/app.js) | Đọc form thành JSON cấu hình, chuyển khoảng nghỉ sang số. |
| [testRevolandPing](../../api/static/app.js) | Lưu dữ liệu form trước, gọi test-connection và tải lại căn. |
| [saveSystemConfig](../../api/static/app.js) | Chặn submit form mặc định, lưu cấu hình, đóng modal và tải lại danh sách. |
| [openAddGroupModal](../../api/static/app.js) | Xóa nội dung form nhóm và mở modal. |
| [closeAddGroupModal](../../api/static/app.js) | Ẩn modal thêm nhóm. |
| [submitNewGroup](../../api/static/app.js) | Import raw_text nếu có, nếu không thì thêm một nhóm; sau đó tải lại danh sách. |
| [document.click](../../api/static/app.js) | Callback ủy quyền sự kiện: tìm data-listing/data-delete-group/data-resolve-task rồi gọi hàm tương ứng. |
| [window.onload](../../api/static/app.js) | Khởi tạo phiên/căn/nhóm song song; sau đó tải lịch sử và phục hồi màn hình chiến dịch. |
| [downloadExcel](../../api/static/app.js) | Fetch báo cáo, kiểm tra response và khởi tạo download blob, sau đó thu hồi URL tạm. |
| [exportPostingResults](../../api/static/app.js) | Xuất campaign đang xem hoặc toàn bộ lịch sử và báo trạng thái tải file. |
| [exportCommentResults](../../api/static/app.js) | Đọc file JSON, kiểm kích thước/cú pháp rồi POST để lọc và tải Excel. |

## File không định nghĩa function riêng

| File/nhóm | Vai trò |
|---|---|
| models/schema.py ngoài utc_now_iso | Pydantic models và enum; các class chủ yếu khai báo trường, không có method tự viết. |
| api/static/index.html | Bố cục dashboard, form, bảng trạng thái và modal; sự kiện gọi app.js. |
| core/registry/*.json | Quy tắc ý định, từ viết tắt, phủ định, spam, địa điểm; là dữ liệu của bộ lọc. |
| install.ps1 | Script tuần tự tạo venv, cài dependency từ lock và tải Chromium. |
| start.ps1 | Script tuần tự chọn khách/cổng, tạo thư mục và ACL, đặt biến môi trường rồi chạy server. |
| requirements*.txt, pytest.ini, .gitignore | Dependency, bản khóa phiên bản, cấu hình kiểm thử và quy tắc bỏ qua dữ liệu. |

## Mô hình dữ liệu cần hiểu

| Model/enum | Vai trò |
|---|---|
| RevolandConfig | Cấu hình URL/key/mock và thông tin liên hệ; chỉ là một phần cấu hình runtime. |
| PropertyListing | Căn từ API; chứa URL ảnh bên ngoài và thông số. |
| FBGroup | Nhóm mục tiêu; còn trường tương thích manual-assisted cũ. |
| GroupTaskResult / GroupPostStatusEnum | Kết quả một nhóm, status, permalink, evidence, retry_count và mốc gửi. |
| PostingCampaign | Một căn + nội dung đã duyệt + task theo nhóm + đường dẫn ảnh local. |
| SessionStatus | Xác thực, profile, busy và tiến độ/kết quả login. |
| Listing / PostingTask / PostingStatusEnum | Model của nhánh manual-assisted cũ. |
| FBComment / ClassificationEnum | Bình luận và kết quả phân loại trong nhánh lead. |
| ReviewItem / ReviewStatusEnum | Mục hàng chờ duyệt thủ công. |
| RevolandLead | Lead nội bộ kèm kết quả đồng bộ Revoland. |
| Các Request DTO trong api/server.py | Validate payload cấu hình, thêm/import nhóm, tạo campaign và xác minh task. |

## Phụ lục: hàm kiểm thử

Các hàm dưới đây dựng dữ liệu/test; không thuộc đường chạy của khách. Số trường hợp pytest bao gồm các hàm có tham số hóa, khác số hàm ứng dụng.

### tests/conftest.py

| Hàm | Mục đích |
|---|---|
| [no_external_requests](../../tests/conftest.py) | Fixture tự áp dụng: chặn requests ra ngoài để tránh dùng dịch vụ thật. |
| [no_external_requests.blocked](../../tests/conftest.py) | Hàm thay thế requests để dừng test nếu phát sinh HTTP ngoài chưa mock. |

### tests/test_api.py

| Hàm | Mục đích |
|---|---|
| [client](../../tests/test_api.py) | Fixture tạo FastAPI TestClient có header thao tác của tool. |
| [test_dashboard_and_javascript](../../tests/test_api.py) | Kiểm tra endpoint HTML và JavaScript hoạt động. |
| [test_config_never_returns_key](../../tests/test_api.py) | Đảm bảo cấu hình công khai không chứa API key và response không cache. |
| [test_mutations_require_header_and_same_origin](../../tests/test_api.py) | Chặn thao tác không có header hoặc đến từ origin khác. |
| [test_config_delay_validation](../../tests/test_api.py) | Từ chối khoảng nghỉ tối thiểu lớn hơn tối đa. |
| [test_api_errors_are_explicit](../../tests/test_api.py) | Revoland lỗi được trả HTTP 502 và giữ detail rõ ràng. |
| [test_manual_resolution_requires_confirmation](../../tests/test_api.py) | Không cho xác minh task khi khách chưa xác nhận. |
| [test_preview_has_fingerprint_and_creation_requires_it](../../tests/test_api.py) | Kiểm hash preview và bắt buộc token khi gọi API tạo campaign. |

### tests/test_browser.py

| Hàm | Mục đích |
|---|---|
| [browser](../../tests/test_browser.py) | Fixture mở/đóng Chromium headless cho các test trình duyệt. |
| [fixture_html](../../tests/test_browser.py) | Tạo trang Facebook giả lập với composer, file input và kết quả theo kịch bản. |
| [test_poster_full_text_images_and_real_confirmation](../../tests/test_browser.py) | Chromium fixture kiểm nội dung dài, ảnh, posted, pending và checkpoint sau gửi. |
| [test_poster_full_text_images_and_real_confirmation.fixture_route](../../tests/test_browser.py) | Intercept mọi request của browser và trả trang fixture, không truy cập Facebook thật. |
| [test_poster_full_text_images_and_real_confirmation.new_page](../../tests/test_browser.py) | Bọc tạo page để test giới hạn timeout và giữ tham chiếu page. |
| [test_poster_full_text_images_and_real_confirmation.new_page.fixture_goto](../../tests/test_browser.py) | Điều hướng fixture với thời gian chờ ngắn để lỗi test không kéo dài. |
| [test_dashboard_renders_untrusted_data_as_text](../../tests/test_browser.py) | Đảm bảo nội dung giống HTML không chạy script và mock mode chặn đăng. |
| [test_dashboard_renders_untrusted_data_as_text.route](../../tests/test_browser.py) | Trả HTML/JavaScript/JSON giả lập theo URL của dashboard. |
| [test_dashboard_to_api_to_sqlite_and_reload](../../tests/test_browser.py) | Đi xuyên dashboard thật, FastAPI thật, SQLite và reload; thay thế hai hệ thống ngoài. |
| [test_dashboard_to_api_to_sqlite_and_reload.submit](../../tests/test_browser.py) | Engine giả lập: gọi mốc trước gửi và trả kết quả posted có bằng chứng fixture. |
| [test_dashboard_to_api_to_sqlite_and_reload.actual_api](../../tests/test_browser.py) | Cầu nối browser request sang FastAPI TestClient thật; ghi nhận response lỗi và trả về browser. |
| [run_photo_fixture](../../tests/test_browser.py) | Chạy engine bằng Chromium fixture với ảnh local và trả kết quả cùng callback gửi. |
| [test_avatar_does_not_count_as_uploaded_photos](../../tests/test_browser.py) | Avatar có sẵn không bù vào số ảnh upload còn thiếu; chỉ đủ ảnh mới mới được gửi. |
| [test_unconfirmed_or_existing_photos_block_submit](../../tests/test_browser.py) | Ảnh lỗi, còn upload, thiếu tile nhận diện hoặc draft có ảnh phải chặn trước gửi. |

### tests/test_campaign.py

| Hàm | Mục đích |
|---|---|
| [system](../../tests/test_campaign.py) | Fixture tạo nhóm, căn, engine giả lập và SQLite riêng cho test campaign. |
| [system.posted](../../tests/test_campaign.py) | Engine giả lập trả posted/permalink sau khi gọi callback trước gửi. |
| [test_precreated_campaigns_do_not_duplicate](../../tests/test_campaign.py) | Hai campaign khác nhau tạo trước không gửi lại cùng căn/nhóm. |
| [test_delete_readd_group_keeps_dedup](../../tests/test_campaign.py) | Xóa và thêm lại cùng URL nhóm vẫn giữ chống trùng. |
| [test_unknown_is_not_retried_and_blocks_new_campaign](../../tests/test_campaign.py) | Unknown không tự retry, chặn campaign mới và cần xác minh. |
| [test_unknown_is_not_retried_and_blocks_new_campaign.uncertain](../../tests/test_campaign.py) | Giả lập lỗi sau mốc bắt đầu gửi để kiểm tra không retry mù. |
| [test_retry_only_failed_not_posted](../../tests/test_campaign.py) | Retry không tác động nhóm posted và chỉ tăng số lần thử cho nhóm lỗi. |
| [test_retry_only_failed_not_posted.failed](../../tests/test_campaign.py) | Engine giả lập trả failed để kiểm tra chọn đúng nhóm retry. |
| [test_mock_data_cannot_post](../../tests/test_campaign.py) | Campaign mock không được gọi engine đăng bài. |
| [test_restart_preserves_submission_uncertainty](../../tests/test_campaign.py) | Khôi phục task đang gửi sau restart thành unknown. |
| [test_simultaneous_execution_rejected](../../tests/test_campaign.py) | Khóa runner đang giữ sẽ chặn lệnh chạy đồng bộ khác. |
| [test_unproven_posted_result_becomes_unknown](../../tests/test_campaign.py) | Kết quả posted thiếu bằng chứng/permalink chuyển unknown. |
| [test_background_start_returns_before_posting_completes](../../tests/test_campaign.py) | Start trả queued trước khi worker xong và dữ liệu chạy được lưu. |
| [test_background_start_returns_before_posting_completes.slow](../../tests/test_campaign.py) | Giữ worker bằng threading.Event để kiểm tra khóa và cơ chế chạy nền. |
| [test_second_service_cannot_overwrite_active_run](../../tests/test_campaign.py) | Service thứ hai bị chặn trong lúc service đầu đã giữ khóa thực thi. |
| [test_second_service_cannot_overwrite_active_run.slow](../../tests/test_campaign.py) | Giữ worker bằng threading.Event để kiểm tra khóa và cơ chế chạy nền. |
| [test_changed_preview_is_rejected_before_downloading](../../tests/test_campaign.py) | Hash căn thay đổi chặn tạo campaign trước bước tải ảnh. |
| [test_legacy_success_is_not_trusted](../../tests/test_campaign.py) | Lịch sử cũ thành legacy/unknown, không tự chạy và giữ file JSON gốc. |
| [test_start_reads_latest_tasks_after_acquiring_locks](../../tests/test_campaign.py) | Yêu cầu khác hoàn tất trước khi lấy khóa; campaign không bị ghi lại pending và engine chỉ được gọi một lần. |
| [test_start_reads_latest_tasks_after_acquiring_locks.acquire_after_other_request](../../tests/test_campaign.py) | Điều khiển thứ tự lấy khóa để mô phỏng một yêu cầu khác hoàn tất campaign trước. |
| [test_start_validation_error_releases_both_locks](../../tests/test_campaign.py) | Validation lỗi sau khi giữ khóa phải giải phóng cả khóa runner và khóa file. |

### tests/test_desktop_launcher.py

| Hàm | Mục đích |
|---|---|
| [test_launcher_uses_persistent_customer_storage](../../tests/test_desktop_launcher.py) | Dữ liệu mặc định của launcher theo tên khách nằm trong LocalAppData. |
| [test_launcher_rejects_invalid_customer](../../tests/test_desktop_launcher.py) | Chặn tên khách rỗng, quá dài, chứa dấu cách hoặc đường dẫn thoát thư mục. |
| [test_frozen_browser_resources_do_not_own_customer_data](../../tests/test_desktop_launcher.py) | Tài nguyên frozen nằm trong gói; dữ liệu khách vẫn ở thư mục bền vững bên ngoài. |

### tests/test_exports.py

| Hàm | Mục đích |
|---|---|
| [sheet](../../tests/test_exports.py) | Đọc bytes XLSX bằng openpyxl để kiểm nội dung sheet. |
| [campaign](../../tests/test_exports.py) | Tạo campaign fixture có nhóm posted và nhóm unknown cho test xuất file. |
| [test_campaign_excel_keeps_uncertainty_and_group_results](../../tests/test_exports.py) | Đọc lại XLSX và đối chiếu từng trạng thái nhóm, permalink, lỗi và retry. |
| [test_comments_excel_preserves_phone_and_does_not_claim_lead_created](../../tests/test_exports.py) | Giữ số 0 đầu điện thoại và không báo đã tạo lead khi chỉ phân loại. |
| [test_imported_sync_status_is_explicit_and_keeps_lead_id](../../tests/test_exports.py) | Ghi rõ trạng thái do input cung cấp và bảo toàn mã lead. |
| [test_lead_without_comment_preserves_contacts_and_sync_state](../../tests/test_exports.py) | Lead không có bình luận gốc vẫn xuất liên hệ, loại bản ghi và trạng thái đồng bộ đúng. |
| [test_exported_user_text_cannot_become_formula](../../tests/test_exports.py) | Tên/nội dung bắt đầu bằng dấu = giữ là text và ký tự XML lỗi được xử lý. |
| [test_comment_import_supported_shapes](../../tests/test_exports.py) | Chấp nhận ba dạng JSON mảng trực tiếp, records và comments. |
| [test_invalid_comment_import_is_rejected](../../tests/test_exports.py) | Từ chối JSON sai cấu trúc, trống nội dung, thiếu dữ liệu hoặc quá dài. |
| [test_too_many_records_rejected](../../tests/test_exports.py) | Không nhận quá 5.000 bản ghi một lần. |
| [test_empty_reports_have_headers](../../tests/test_exports.py) | Nguồn rỗng vẫn xuất workbook có header hợp lệ. |
| [test_legacy_export_function_can_write_path](../../tests/test_exports.py) | API exporter cũ vẫn ghi file vào đường dẫn và tự tạo thư mục. |
| [test_export_api_downloads_and_campaign_filter](../../tests/test_exports.py) | Kiểm response tải XLSX, lọc campaign, 404 và file JSON mẫu. |
| [test_comment_export_api_validation_and_size_limit](../../tests/test_exports.py) | Kiểm validation, giới hạn 5 MB và header bảo vệ POST. |
| [test_cli_exports_comments_and_posting_history](../../tests/test_exports.py) | Chạy CLI bằng subprocess, đọc lại hai file và chặn ghi đè file cũ. |
| [test_cli_export_does_not_recover_or_rewrite_running_campaign](../../tests/test_exports.py) | Xuất báo cáo CLI không đổi campaign running hoặc phục hồi task đang dở. |

### tests/test_filter_engine.py

| Hàm | Mục đích |
|---|---|
| [test_contact_extractor](../../tests/test_filter_engine.py) | Kiểm tra trích số điện thoại có dấu cách/dấu chấm. |
| [test_filter_dataset_benchmark](../../tests/test_filter_engine.py) | Chạy bộ lọc trên 20 mẫu có nhãn và yêu cầu độ đúng tối thiểu 95%. |

### tests/test_groups.py

| Hàm | Mục đích |
|---|---|
| [test_normalization_and_duplicates](../../tests/test_groups.py) | Chuẩn hóa URL nhóm và chặn thêm cùng nhóm với URL biến thể. |
| [test_group_url_validation](../../tests/test_groups.py) | Từ chối domain hoặc đường dẫn không phải nhóm Facebook. |
| [test_bulk_import_normalizes_duplicates](../../tests/test_groups.py) | Import nhiều dòng, bỏ URL trùng và xác nhận dữ liệu lưu lại. |

### tests/test_pipeline.py

| Hàm | Mục đích |
|---|---|
| [test_full_pipeline_flow](../../tests/legacy/test_pipeline.py) | Luồng thử nghiệm dùng bình luận mẫu: lọc, tạo lead mock, hàng chờ, duyệt và chống trùng. |

### tests/test_revoland.py

| Hàm | Mục đích |
|---|---|
| [response](../../tests/test_revoland.py) | Dựng HTTP response Mock với mã trạng thái và JSON chỉ định. |
| [live](../../tests/test_revoland.py) | Fixture tạo RevolandService với mock mode tắt nhưng HTTP được mock trong test. |
| [test_http_error_never_falls_back](../../tests/test_revoland.py) | 401/403/500 không được thay bằng dữ liệu căn mẫu. |
| [test_supported_envelopes](../../tests/test_revoland.py) | Đọc được mảng trực tiếp, data và listings. |
| [test_empty_is_empty](../../tests/test_revoland.py) | Mảng data rỗng phải trả danh sách rỗng. |
| [test_pagination](../../tests/test_revoland.py) | Đọc đủ các trang theo last_page. |
| [test_bad_schema_is_error](../../tests/test_revoland.py) | Bản ghi thiếu trường bắt buộc phải báo lỗi. |
| [test_no_invented_legal_claim](../../tests/test_revoland.py) | Không tự chèn pháp lý khi API không có, và có hiển thị khi API cung cấp. |
| [test_all_images_or_error](../../tests/test_revoland.py) | Ảnh lỗi phải chặn tải thay vì trả tập ảnh thiếu. |
| [test_download_validates_images_and_keeps_all](../../tests/test_revoland.py) | Đọc ảnh bằng Pillow, giữ đủ hơn bốn ảnh và không thoát thư mục cache theo ID căn. |

### tests/test_session.py

| Hàm | Mục đích |
|---|---|
| [test_no_session_never_simulates_success](../../tests/test_session.py) | Không có profile thì yêu cầu login, không có URL/thành công giả. |
| [test_cookie_and_ui_both_required](../../tests/test_session.py) | Không coi URL trang chủ, cookie riêng hoặc trang checkpoint là phiên hợp lệ. |
| [test_profile_lock_protects_logout_and_check](../../tests/test_session.py) | Profile đang giữ khóa sẽ chặn logout và status trả busy. |
| [test_logout_reports_deletion_failure](../../tests/test_session.py) | Lỗi xóa profile phải được báo thay vì success. |
| [test_post_url_must_be_permalink_for_same_group](../../tests/test_session.py) | Chặn URL domain khác/nhóm khác và URL nhóm không phải bài. |
| [test_password_saving_disabled_preserves_preferences](../../tests/test_session.py) | Tắt lưu mật khẩu mà không xóa thiết lập profile khác. |

Tổng danh mục: **140 hàm/method Python ứng dụng**, **37 hàm/callback JavaScript**, **86 hàm/helper kiểm thử có tên**. Không tính hàm do thư viện/Pydantic sinh tự động.
