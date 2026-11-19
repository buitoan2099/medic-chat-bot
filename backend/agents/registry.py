"""
Định nghĩa agent (đặc tả 03 mục 1.1). Cấu hình vận hành (model, nhiệt độ...) và
prompt có phiên bản nằm trong storage, sửa được lúc chạy; ở đây chỉ là giá trị
khởi tạo. Agent của P2/P3 (copilot, kiểm tra trước khi gửi, quản lý) bổ sung sau.
"""

from config import BASE_DIR, GENERATION_MODEL

SEED_PROMPT_DIR = BASE_DIR / 'prompts' / 'agents'

AG0_TRIAGE = 'ag0_triage'
AG1_USER_AI = 'ag1_user_ai'
AG2_COPILOT_C1 = 'ag2_copilot_c1'
AG3_COPILOT_C2 = 'ag3_copilot_c2'
AG4_COPILOT_C3 = 'ag4_copilot_c3'
AG5_CASE_MEMORY = 'ag5_case_memory'
AG6_GUARD = 'ag6_guard'
AG7_MANAGER = 'ag7_manager'

# Copilot ứng với cấp chuyên môn của người trực (đặc tả 03 mục 4)
COPILOT_BY_LEVEL = {'C1': AG2_COPILOT_C1, 'C2': AG3_COPILOT_C2, 'C3': AG4_COPILOT_C3}

# Thời gian chờ theo số đo thật trên Mac mini (18/11/2026): qwen3:14b đọc prompt ~115 tok/s,
# sinh ~10,5 tok/s, Ollama xử lý tuần tự 1 yêu cầu. AG-0 ~20 s, AG-1/copilot 60–120 s.
AGENT_DEFAULTS = {
    AG0_TRIAGE: dict(title='AG-0 · Phân loại câu hỏi', provider='ollama', model=GENERATION_MODEL,
                     temperature=0.0, max_tokens=300, num_ctx=16384, timeout_s=45.0),
    AG1_USER_AI: dict(title='AG-1 · AI người dùng (chế độ AI)', provider='ollama',
                      model=GENERATION_MODEL, temperature=0.1, max_tokens=1024, num_ctx=16384,
                      timeout_s=300.0),
    AG2_COPILOT_C1: dict(title='AG-2 · Copilot C1 – Tư vấn thông tin thuốc', provider='ollama',
                         model=GENERATION_MODEL, temperature=0.2, max_tokens=1500, num_ctx=16384,
                         timeout_s=300.0),
    AG3_COPILOT_C2: dict(title='AG-3 · Copilot C2 – Bệnh nhẹ, thuốc không kê đơn', provider='ollama',
                         model=GENERATION_MODEL, temperature=0.2, max_tokens=1500, num_ctx=16384,
                         timeout_s=300.0),
    AG4_COPILOT_C3: dict(title='AG-4 · Copilot C3 – Bác sĩ tư vấn ca nặng', provider='ollama',
                         model=GENERATION_MODEL, temperature=0.2, max_tokens=1800, num_ctx=16384,
                         timeout_s=300.0),
    AG5_CASE_MEMORY: dict(title='AG-5 · Tóm tắt & hồ sơ ca', provider='ollama',
                          model=GENERATION_MODEL, temperature=0.0, max_tokens=600, num_ctx=16384,
                          timeout_s=180.0),
    AG6_GUARD: dict(title='AG-6 · Kiểm tra trước khi gửi', provider='ollama',
                    model=GENERATION_MODEL, temperature=0.0, max_tokens=400, num_ctx=16384,
                    timeout_s=90.0),
    AG7_MANAGER: dict(title='AG-7 · Agent quản lý', provider='ollama', model=GENERATION_MODEL,
                      temperature=0.1, max_tokens=1500, num_ctx=16384, timeout_s=300.0),
}


def seed_prompt(agent_id):
    return (SEED_PROMPT_DIR / agent_id / 'v1.txt').read_text(encoding='utf-8').strip()
