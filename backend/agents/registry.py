"""
Định nghĩa agent (đặc tả 03 mục 1.1). Cấu hình vận hành (model, nhiệt độ...) và
prompt có phiên bản nằm trong storage, sửa được lúc chạy; ở đây chỉ là giá trị
khởi tạo. Agent của P2/P3 (copilot, kiểm tra trước khi gửi, quản lý) bổ sung sau.
"""

from config import BASE_DIR, GENERATION_MODEL

SEED_PROMPT_DIR = BASE_DIR / 'prompts' / 'agents'

AG0_TRIAGE = 'ag0_triage'
AG1_USER_AI = 'ag1_user_ai'

AGENT_DEFAULTS = {
    AG0_TRIAGE: dict(title='AG-0 · Phân loại câu hỏi', provider='ollama', model=GENERATION_MODEL,
                     temperature=0.0, max_tokens=300, num_ctx=16384, timeout_s=15.0),
    AG1_USER_AI: dict(title='AG-1 · AI người dùng (chế độ AI)', provider='ollama',
                      model=GENERATION_MODEL, temperature=0.1, max_tokens=1024, num_ctx=16384,
                      timeout_s=180.0),
}


def seed_prompt(agent_id):
    return (SEED_PROMPT_DIR / agent_id / 'v1.txt').read_text(encoding='utf-8').strip()
