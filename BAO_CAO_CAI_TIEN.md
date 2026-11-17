# Báo cáo cải tiến chatbot tra cứu tài liệu

Ngày: 17/11/2026 · Tài liệu đang dùng: Dược thư Quốc gia Việt Nam 2018

## Tóm tắt

- **Dùng chung cho mọi tài liệu PDF:** code không còn chỗ nào viết riêng cho Dược thư. Header/footer, tiêu đề, mục và trang mục lục được tự suy ra từ chính tài liệu (dựa vào cỡ chữ, chữ đậm, các dòng lặp lại). Tiêu đề app và prompt riêng theo lĩnh vực nằm trong `.env`.
- **Dữ liệu sạch hơn:**
  - bỏ ~33% nội dung bị embed trùng lặp do cấu trúc PDF;
  - bỏ header lẫn trong nội dung và trang mục lục;
  - chunk theo mục, mở đầu bằng đường dẫn tiêu đề (vd `Paracetamol › Chống chỉ định`).
- **Truy xuất:** tìm kiếm kết hợp vector + BM25 (gộp bằng RRF), có ngưỡng điểm, xử lý câu hỏi nối tiếp, mở rộng ngữ cảnh theo mục, và tự chuyển sang tìm theo từ khoá khi Ollama mất kết nối.
- **Trải nghiệm và hiệu năng:**
  - trả lời dạng streaming;
  - giữ một client Qdrant dùng chung thay vì mở lại mỗi câu hỏi;
  - trạng thái chỉ mục đọc nhanh.

> ⚠️ **Chưa embed collection mới và chưa đo được phần vector.** Trong lúc làm, Tailscale trên máy này đang tắt nên không gọi được Ollama trên Mac mini. Xem mục 5.

---

## 1. Phát hiện về dữ liệu

| Vấn đề | Ảnh hưởng | Cách xử lý (tổng quát) |
|---|---|---|
| Luồng nội dung của trang PDF chứa cả chữ của **trang đối diện**, đặt ngoài khổ giấy. | ~33% văn bản bị embed hai lần; top-3 thường là 2 bản sao của cùng một đoạn. | Chỉ lấy chữ có toạ độ x nằm trong khổ trang. |
| Header `482 DTQGVN 2Dactinomycin` lẫn vào nội dung. | Gây nhiễu embedding. | Dòng ở mép trang có cùng "chữ ký" lặp lại ở ≥25% số trang thì coi là header/footer. |
| Tên chạy đầu trang đôi khi bị PDF đặt ở *cuối* luồng chữ. | Bị nhận nhầm là tiêu đề mới, các mục sau đó bị gán sai chủ đề. | Tiêu đề ở mép trang trùng tiêu đề vừa gặp trong vòng 10 trang thì bỏ qua. |
| Chunk cắt máy móc 1.400 ký tự theo trang. | Đoạn "Liều dùng: 500 mg…" không biết thuộc thuốc nào. | Chunk theo mục; mỗi chunk mở đầu bằng đường dẫn tiêu đề. |
| Mục lục và chỉ mục cuối sách (137 trang) bị embed như nội dung. | Nhiễu. | Trang có ≥50% số dòng dạng "tên…, số trang" thì không embed. |

---

## 2. Bộ phân tích tài liệu tổng quát ([rag/pdf_parser.py](rag/pdf_parser.py))

Không có mẫu header, khoảng trang hay tên mục nào được viết sẵn trong code.

| Bước | Cách làm |
|---|---|
| Trích chữ | Lấy cả cỡ chữ và tỉ lệ in đậm của từng dòng. Có cache theo kích thước + thời điểm sửa của file. |
| Header/footer | Theo chữ ký lặp lại ở mép trang, hoặc dòng chỉ là số trang. |
| Tiêu đề | Dòng ngắn in đậm hoặc cỡ chữ lớn hơn nội dung. Dòng kết thúc bằng ":" là nhãn trong đoạn, không phải tiêu đề. Dòng chỉ gồm "(…)" được ghép vào tiêu đề ngay trước. |
| Cấp tiêu đề | Theo cỡ chữ và kiểu in hoa. |
| Loại mục | Tiêu đề xuất hiện dưới ≥5 tiêu đề cha khác nhau, vd "Chỉ định", "Thận trọng". |
| Chủ đề | Tiêu đề hay làm cha của các loại mục, vd tên thuốc. Các cỡ chữ khác nhau của cùng loại tiêu đề được coi là ngang hàng. |
| Ghép dòng | Nối dòng bị ngắt cứng thành đoạn, giữ được số trang của từng đoạn. |

**Kết quả với Dược thư 2018** (không cấu hình gì thêm):
- 742 chủ đề, gồm 683/684 chuyên luận thuốc và các chuyên đề;
- 22 loại mục, 137 trang mục lục/chỉ mục bị loại;
- 15.780 chunk, khoảng 9,5 triệu ký tự (bản cũ: 14.529 chunk, khoảng 14,4 triệu ký tự, trong đó 1/3 trùng);
- chạy lại cho kết quả giống hệt (kiểm tra bằng md5).

**Ingest** ([rag/ingest.py](rag/ingest.py)):
- xử lý **mọi PDF** khớp `PDF_GLOB`, `chunk_id` gắn với tên file để không trùng;
- thêm tuỳ chọn `--dry-run`: chỉ phân tích, không embed;
- bỏ phụ thuộc `langchain-community` (đã ngừng phát triển).

---

## 3. Truy xuất và trả lời

### [rag/rag.py](rag/rag.py), [rag/lexical.py](rag/lexical.py)
1. **Tìm kiếm kết hợp:** lấy 30 ứng viên từ vector (Qdrant) và 30 từ BM25, gộp bằng Reciprocal Rank Fusion.
   - BM25 tự viết bằng numpy, không thêm thư viện; dùng từ không dấu kèm bigram.
   - Dựng chỉ mục khoảng 5 giây (một lần); mỗi lần tìm dưới 1 ms.
2. **Ngưỡng điểm:** cosine cao nhất < `MIN_SCORE` (0,45) thì trả "chưa đủ thông tin" mà không gọi LLM.
3. **Câu hỏi nối tiếp:** câu ngắn (≤ 6 từ) hoặc bắt đầu bằng "còn/vậy…" được ghép thêm câu hỏi trước để tìm kiếm.
4. **Mở rộng ngữ cảnh:** chunk khớp thuộc mục ngắn (≤ 2.500 ký tự) thì đưa nguyên mục cho LLM. Tổng ngữ cảnh ≤ 9.000 ký tự để vừa `NUM_CTX=8192`.
5. **Dự phòng:** không tạo được embedding thì tìm theo BM25 và hiện cảnh báo. Thời gian chờ kết nối Ollama là 5 giây.
6. `TOP_K` tăng từ 3 lên 5.

**Đã bỏ theo yêu cầu:** module nhận diện tên thuốc/biệt dược và từ khoá ý định (`rag/drugs.py`), vì chỉ dùng được cho tài liệu dược.

### Sinh câu trả lời ([provider/llm.py](provider/llm.py), [provider/prompts.py](provider/prompts.py))
- **Streaming** cho Ollama, Gemini và OpenAI; lọc khối `<think>` ngay trong lúc stream.
- Prompt mặc định là **prompt chung**. Prompt Dược thư được chuyển ra [prompts/duoc_thu.txt](prompts/duoc_thu.txt) và bật bằng `SYSTEM_PROMPT_FILE` trong `.env`.

### Giao diện ([app.py](app.py))
- Tiêu đề, mô tả và lưu ý lấy từ `.env` (`APP_TITLE`, `APP_SUBTITLE`, `APP_NOTICE`).
- Câu trả lời hiện chữ dần; nguồn hiển thị đường dẫn tiêu đề và khoảng trang.
- Sidebar có số PDF, số chủ đề, loại mục, trang bị loại; thêm nút xoá hội thoại.
- Nút rebuild chạy đúng lệnh `python -m rag.ingest` (trước đây trỏ sai đường dẫn).

### Sửa lỗi
- Resume ingest không bỏ qua được chunk nào, do so sánh UUID với chuỗi.
- Thông báo lỗi chỉ sai lệnh.
- Import thừa.
- Script `test_check` còn câu hỏi luật đất đai.

---

## 4. Kết quả đánh giá (đã đo)

Chạy bằng [evaluation/run_eval.py](evaluation/run_eval.py) trên 167 câu hỏi:
- 147 câu sinh theo mẫu, gồm tên chung, không dấu, biệt dược và chuyên đề;
- 20 câu viết tay kiểu người dùng thật.

Hai chỉ số chính:
- **page@k:** trong top k có kết quả thuộc đúng chủ đề.
- **section@k:** kết quả đúng cả mục.

Hiện chỉ đo được **BM25 dùng riêng**, vì phần vector cần Ollama:

| Nhóm | page@1 | page@5 | section@1 | section@5 |
|---|---|---|---|---|
| Tất cả | 0,527 | 0,665 | 0,216 | 0,419 |
| Tên chung | 0,708 | 0,854 | 0,250 | 0,500 |
| Không dấu | 0,644 | 0,756 | 0,267 | 0,556 |
| Biệt dược | 0,262 | 0,262 | 0,048 | 0,095 |
| Chuyên đề | 0,500 | 0,833 | 0,500 | 0,833 |
| Viết tay | 0,400 | 0,750 | 0,200 | 0,350 |

**Cách đọc:**
- BM25 dùng một mình chỉ là một nửa của hệ thống. Kết quả thực tế là `hybrid` (vector + BM25), chưa đo được.
- **Đánh đổi khi bỏ nhận diện thuốc** (đã đo trước khi bỏ, cũng chưa có vector):
  - page@1 từ 0,98 xuống 0,53;
  - câu hỏi bằng tên biệt dược từ 1,00 xuống 0,26.
  - Lý do: tên biệt dược chỉ có trong mục lục và mục "Tên thương mại", không có trong nội dung chính.
- Câu hỏi sinh theo mẫu dễ hơn câu hỏi thật. Nhóm viết tay là thước đo đáng tin hơn.

---

## 5. Việc cần làm tiếp

1. **Bật Tailscale**, kiểm tra bằng `python -m test_check.check_ollama`.
2. **Tắt app Streamlit**, vì Qdrant local chỉ cho một tiến trình truy cập.
3. Embed collection mới:
   ```bash
   python -m rag.ingest --reset
   ```
   - Lệnh này chỉ tạo `duoc_2018_v2`; collection cũ `duoc_2018_pdf` được giữ để so sánh.
   - Bị gián đoạn thì chạy `--resume`.
4. Đo đủ các phương án `baseline` / `dense` / `bm25` / `hybrid`:
   ```bash
   python -m evaluation.run_eval
   ```
5. Điều chỉnh `MIN_SCORE` theo điểm cosine thực tế. Giá trị 0,45 hiện tại là ước lượng.
6. Khi hài lòng với kết quả, xoá collection cũ để giảm RAM.

**Đổi sang tài liệu khác:** chép PDF vào `data/documents/`, rồi sửa trong `.env`:
- `PDF_GLOB` (vd `data/documents/*.pdf`);
- `COLLECTION_NAME`;
- `APP_TITLE` / `APP_SUBTITLE` / `APP_NOTICE`;
- `SYSTEM_PROMPT_FILE` (bỏ trống để dùng prompt chung).

Sau đó chạy `python -m rag.ingest --reset`. Muốn đánh giá thì sinh câu hỏi bằng `python -m evaluation.build_eval` và bổ sung câu viết tay vào `natural_questions.jsonl`.

**Đã thay đổi trong `.env`:** `COLLECTION_NAME=duoc_2018_v2`, `BASELINE_COLLECTION`, `TOP_K=5`, cùng các biến giao diện/prompt ở cuối file.

## 6. Giới hạn còn lại

- **Bộ phân tích dựa vào định dạng chữ:**
  - PDF scan (ảnh, không có lớp chữ) cần OCR trước.
  - PDF không phân biệt tiêu đề bằng chữ đậm/cỡ chữ sẽ chỉ có chunk theo kích thước, không có đường dẫn tiêu đề.
  - Mới kiểm chứng trên Dược thư 2018; nên chạy `--dry-run` và xem `chunks.jsonl` khi thêm tài liệu mới.
- **Không còn nhận diện tên riêng/biệt dược:** câu hỏi bằng tên gọi khác không có trong nội dung chính sẽ khó tìm. Có thể bổ sung lại theo cách tổng quát, tức lấy chủ đề và tên gọi khác từ tiêu đề và trang chỉ mục, nếu cần.
- Chưa có reranker cross-encoder, vì Ollama không có API rerank.
- Một vài trang có thứ tự chữ bị trộn do PDF (hai chuyên luận chung một cột).
- Qdrant server (Docker) sẽ bỏ được giới hạn một tiến trình.
