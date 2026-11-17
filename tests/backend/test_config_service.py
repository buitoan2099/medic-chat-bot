import pytest

from backend.agents.registry import AG0_TRIAGE, AG1_USER_AI
from backend.core import local_date, utc_now
from backend.services.config_service import ConfigError, ConfigService
from backend.storage.local import LocalStorage


@pytest.fixture
def service(tmp_path):
    svc = ConfigService(LocalStorage(tmp_path / 'storage'))
    svc.ensure_seeded()
    return svc


def test_seed_creates_agents_prompts_and_settings(service):
    assert set(service.agents()) == {AG0_TRIAGE, AG1_USER_AI}
    text, version = service.prompt(AG1_USER_AI)
    assert version == 1 and '[AN-TOÀN – BẮT BUỘC' in text
    assert service.settings()['tiering_rules_enabled'] is False


def test_seed_does_not_overwrite_edited_config(service):
    service.update_agent(AG1_USER_AI, {'model': 'qwen3:4b'}, actor='admin')
    service.ensure_seeded()
    assert service.agent(AG1_USER_AI).model == 'qwen3:4b'


def test_update_agent_validates_and_audits(service):
    with pytest.raises(ConfigError):
        service.update_agent(AG1_USER_AI, {'active_prompt_version': 9}, actor='admin')
    with pytest.raises(ConfigError):
        service.update_agent(AG1_USER_AI, {'provider': 'abc'}, actor='admin')

    service.update_agent(AG1_USER_AI, {'temperature': 0.3}, actor='admin')
    audit = service.storage.audit.by_day(local_date(utc_now()))
    assert audit[-1].action == 'agent.update' and audit[-1].data['after'] == {'temperature': 0.3}


def test_prompt_versions_activate_and_rollback(service):
    v2 = service.add_prompt_version(AG1_USER_AI, 'Prompt mới', 'thử', actor='admin', activate=True)
    assert service.prompt(AG1_USER_AI) == ('Prompt mới', v2.version)          # AC-4.2
    service.activate_prompt(AG1_USER_AI, 1, actor='admin')                    # quay lại
    assert service.prompt(AG1_USER_AI)[1] == 1
    with pytest.raises(ConfigError):
        service.activate_prompt(AG1_USER_AI, 99, actor='admin')


def test_prompt_budget_enforced(service):
    with pytest.raises(ConfigError):
        service.add_prompt_version(AG1_USER_AI, 'x' * 10000, 'quá dài', actor='admin')


def test_settings_update(service):
    service.update_settings({'llm_max_parallel': 3}, actor='admin')
    assert service.settings()['llm_max_parallel'] == 3
    with pytest.raises(ConfigError):
        service.update_settings({'khong_co': 1}, actor='admin')
