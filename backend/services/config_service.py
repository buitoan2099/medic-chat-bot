"""
Cấu hình vận hành đọc/ghi lúc chạy (technical plan X-5). `config.py` chỉ còn cấu
hình khởi động; mọi thứ đổi được trên trang cấu hình nằm ở đây.
"""

import threading

from backend.agents.registry import AGENT_DEFAULTS, seed_prompt
from backend.domain import AgentConfig, AuditLog
from config import CANDIDATE_K, COLLECTION_NAME, MIN_SCORE, TOP_K

DEFAULT_SETTINGS = {
    'active_collection': COLLECTION_NAME,
    'previous_collection': None,
    # Khớp OLLAMA_NUM_PARALLEL (đo 18/11/2026: Mac mini xử lý tuần tự). Lớn hơn số Ollama
    # chạy song song thì yêu cầu dồn ở Ollama (FIFO) và hàng đợi ưu tiên mất tác dụng.
    'llm_max_parallel': 1,
    # Số chỗ giữ riêng cho việc gấp (phân loại, trả lời khách, kiểm tra trước khi gửi): gợi ý /
    # quản lý / hồ sơ ca không được chiếm. Chỉ có tác dụng khi llm_max_parallel >= 2.
    'llm_reserved_slots': 1,
    # Dịch vụ đám mây (Gemini, OpenAI…) có hàng đợi riêng, không xếp sau Ollama
    'remote_llm_max_parallel': 8,
    'top_k': TOP_K,
    'candidate_k': CANDIDATE_K,
    'min_score': MIN_SCORE,
    # Trọng số BM25 khi gộp với vector: câu có dấu / không dấu (đo ở evaluation/, 18/11/2026)
    'bm25_weight_accented': 0.0,
    'bm25_weight_unaccented': 1.0,
    # Bộ quy tắc phân tầng (phan-tang.md) chỉ bật khi Hội đồng đã duyệt
    'tiering_rules_enabled': False,
    # Người trực (P2)
    'sla_normal_s': 300,                 # BR-05: chờ quá 5 phút -> cảnh báo
    'sla_emergency_s': 60,
    'reopen_window_h': 24,               # BR-06
    'guard_block_mode': 'confirm',       # confirm | hard (Q-10: thí điểm = confirm)
    # Lỗi CHẶN CỨNG thêm (vd ['exceeds_level']) dù guard_block_mode=confirm. Mặc định rỗng:
    # người trực trả lời thoải mái; chỉ gợi ý AI vượt quyền là không gửi được.
    # prescription_drug luôn chặn cứng (không kê đơn trực tuyến), không bỏ được bằng cài đặt.
    'guard_hard_issues': [],
    # Bật/tắt bước AI kiểm tra trước khi gửi (AG-6). Tắt (mặc định): bấm Gửi là đi ngay, chỉ còn
    # kiểm tra theo quy tắc (danh mục thuốc kê đơn, trích dẫn) + chặn gợi ý AI vượt quyền.
    'guard_llm_enabled': False,
    # Khi AG-6 bật: tin người trực tự soạn có qua AG-6 không (chỉ chặn thuốc kê đơn, còn lại cảnh báo).
    # False = chỉ quy tắc, gửi ngay không chờ LLM – CHỈ tắt khi danh mục thuốc kê đơn (Q-2) đã đủ.
    'guard_llm_for_typed': True,
    'guard_confirm_when_unavailable': True,
    # Quản lý (P3): mẫu quyền áp nhanh (đặc tả 02 mục 5)
    'permission_templates': {
        'Dược sĩ mới': {'level': 'C1', 'ai.send_unedited': False, 'chat.max_concurrent': 3},
        'Người trực chuẩn': {'ai.send_unedited': True, 'chat.max_concurrent': 5},
    },
    'credential_expiry_warning_days': 30,
}

# Ngân sách system prompt (technical plan 5.2): ~2.500 token ≈ 6.250 ký tự (2,5 ký tự/token)
PROMPT_BUDGET_TOKENS = 2500
CHARS_PER_TOKEN = 2.8   # đo thật: ~3,2 ký tự/token trên tài liệu (qwen3); chừa biên

EDITABLE_FIELDS = {'provider', 'model', 'temperature', 'max_tokens', 'num_ctx', 'timeout_s',
                   'enabled', 'fallback_provider', 'fallback_model'}
ALLOWED_PROVIDERS = {'ollama', 'gemini', 'openrouter', 'openai', 'fake'}


class ConfigError(ValueError):
    pass


def estimate_tokens(text):
    return int(len(text) / CHARS_PER_TOKEN) + 1


class ConfigService:
    def __init__(self, storage):
        self.storage = storage
        self._lock = threading.RLock()

    # ---------- khởi tạo ----------

    def ensure_seeded(self, actor='system'):
        """Tạo cấu hình + prompt v1 cho agent chưa có (không ghi đè cấu hình đã sửa)."""

        with self._lock:
            agents = self.storage.config.get_agents()
            for agent_id, defaults in AGENT_DEFAULTS.items():
                if agent_id not in agents:
                    self.storage.config.save_agent(AgentConfig(agent_id=agent_id, **defaults))
                if not self.storage.config.list_prompt_versions(agent_id):
                    self.storage.config.add_prompt_version(agent_id, seed_prompt(agent_id),
                                                           note='Khởi tạo từ đặc tả 03',
                                                           created_by=actor)
            settings = {**DEFAULT_SETTINGS, **self.storage.config.get_settings()}
            self.storage.config.save_settings(settings)

    # ---------- agent ----------

    def agents(self):
        return self.storage.config.get_agents()

    def agent(self, agent_id):
        agents = self.agents()
        if agent_id not in agents:
            raise ConfigError(f'Không có agent {agent_id}')
        return agents[agent_id]

    def update_agent(self, agent_id, changes, actor):
        unknown = set(changes) - EDITABLE_FIELDS
        if unknown:
            raise ConfigError(f'Không sửa được trường: {", ".join(sorted(unknown))}')
        if 'provider' in changes and changes['provider'] not in ALLOWED_PROVIDERS:
            raise ConfigError(f'Provider không hợp lệ: {changes["provider"]}')
        with self._lock:
            current = self.agent(agent_id)
            updated = AgentConfig.model_validate({**current.model_dump(), **changes})
            self.storage.config.save_agent(updated)
            self._audit(actor, 'agent.update', agent_id,
                        {'before': {k: getattr(current, k) for k in changes},
                         'after': changes})
            return updated

    # ---------- prompt ----------

    def prompt(self, agent_id):
        """(nội dung, phiên bản) của prompt đang dùng."""

        version = self.agent(agent_id).active_prompt_version
        return self.storage.config.get_prompt(agent_id, version), version

    def prompt_versions(self, agent_id):
        return self.storage.config.list_prompt_versions(agent_id)

    def add_prompt_version(self, agent_id, text, note, actor, activate=False):
        text = text.strip()
        if not text:
            raise ConfigError('Prompt rỗng')
        tokens = estimate_tokens(text)
        if tokens > PROMPT_BUDGET_TOKENS:
            raise ConfigError(f'Prompt ~{tokens} token vượt ngân sách {PROMPT_BUDGET_TOKENS} token')
        with self._lock:
            self.agent(agent_id)
            entry = self.storage.config.add_prompt_version(agent_id, text, note, actor)
            self._audit(actor, 'prompt.add', agent_id, {'version': entry.version, 'note': note})
            if activate:
                self.activate_prompt(agent_id, entry.version, actor)
            return entry

    def activate_prompt(self, agent_id, version, actor):
        with self._lock:
            if version not in {v.version for v in self.prompt_versions(agent_id)}:
                raise ConfigError(f'{agent_id} không có phiên bản {version}')
            current = self.agent(agent_id)
            updated = current.model_copy(update={'active_prompt_version': version})
            self.storage.config.save_agent(updated)
            self._audit(actor, 'prompt.activate', agent_id,
                        {'from': current.active_prompt_version, 'to': version})
            return updated

    # ---------- settings ----------

    def settings(self):
        return {**DEFAULT_SETTINGS, **self.storage.config.get_settings()}

    def bm25_weights(self):
        settings = self.settings()
        return (float(settings['bm25_weight_accented']), float(settings['bm25_weight_unaccented']))

    def update_settings(self, changes, actor):
        unknown = set(changes) - set(DEFAULT_SETTINGS)
        if unknown:
            raise ConfigError(f'Không có cài đặt: {", ".join(sorted(unknown))}')
        with self._lock:
            current = self.settings()
            updated = {**current, **changes}
            self.storage.config.save_settings(updated)
            self._audit(actor, 'settings.update', None,
                        {'before': {k: current.get(k) for k in changes}, 'after': changes})
            return updated

    def _audit(self, actor, action, target, data):
        self.storage.audit.add(AuditLog(actor=actor, action=action, target=target, data=data))
