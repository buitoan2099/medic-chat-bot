"""
Client HTTP duy nhất mà giao diện dùng (technical plan R1: UI không import rag/llm).
"""

import json

import httpx

from config import BACKEND_URL


class BackendError(RuntimeError):
    pass


def _check(response):
    if response.status_code >= 400:
        try:
            detail = response.json().get('detail')
        except ValueError:
            detail = response.text[:300]
        raise BackendError(f'{response.status_code}: {detail}')
    return response.json()


def _client(admin_token=None, timeout=30.0):
    headers = {'X-Admin-Token': admin_token} if admin_token else {}
    return httpx.Client(base_url=BACKEND_URL, headers=headers, timeout=timeout)


def health():
    try:
        with _client(timeout=5.0) as c:
            return _check(c.get('/api/health'))
    except httpx.HTTPError as error:
        raise BackendError(f'Không kết nối được backend tại {BACKEND_URL}: {error}') from error


# ---------- khung 1 ----------

def start_conversation(consent, profile=None):
    with _client() as c:
        return _check(c.post('/api/chat/conversations', json={'consent': consent, 'profile': profile}))


def get_conversation(conversation_id):
    with _client() as c:
        return _check(c.get(f'/api/chat/conversations/{conversation_id}'))


def handoff(conversation_id):
    with _client() as c:
        return _check(c.post(f'/api/chat/conversations/{conversation_id}/handoff'))


def send_message(conversation_id, text):
    """Generator các sự kiện SSE (dict) từ backend."""

    with _client(timeout=httpx.Timeout(10.0, read=600.0)) as c:
        with c.stream('POST', f'/api/chat/conversations/{conversation_id}/messages',
                      json={'text': text}) as response:
            if response.status_code >= 400:
                response.read()
                _check(response)
            for line in response.iter_lines():
                if line.startswith('data: '):
                    event = json.loads(line[6:])
                    if event.get('type') == 'end':
                        return
                    yield event


# ---------- quản trị ----------

class Admin:
    def __init__(self, token):
        self.token = token

    def _get(self, path, **params):
        with _client(self.token) as c:
            return _check(c.get(path, params=params))

    def _send(self, method, path, body=None, timeout=30.0):
        with _client(self.token, timeout=timeout) as c:
            return _check(c.request(method, path, json=body))

    def agents(self):
        return self._get('/api/admin/agents')

    def update_agent(self, agent_id, changes):
        return self._send('PUT', f'/api/admin/agents/{agent_id}', {'changes': changes})

    def test_agent(self, agent_id, sample=False):
        return self._send('POST', f'/api/admin/agents/{agent_id}/test', {'sample': sample},
                          timeout=300.0)

    def prompts(self, agent_id):
        return self._get(f'/api/admin/agents/{agent_id}/prompts')

    def prompt_text(self, agent_id, version):
        return self._get(f'/api/admin/agents/{agent_id}/prompts/{version}')['text']

    def add_prompt(self, agent_id, text, note, activate):
        return self._send('POST', f'/api/admin/agents/{agent_id}/prompts',
                          {'text': text, 'note': note, 'activate': activate})

    def activate_prompt(self, agent_id, version):
        return self._send('POST', f'/api/admin/agents/{agent_id}/prompts/{version}/activate')

    def settings(self):
        return self._get('/api/admin/settings')

    def update_settings(self, changes):
        return self._send('PUT', '/api/admin/settings', {'changes': changes})

    def index(self):
        return self._get('/api/admin/index')

    def rebuild(self):
        return self._send('POST', '/api/admin/index/rebuild')

    def cancel_rebuild(self):
        return self._send('POST', '/api/admin/index/cancel')

    def rollback(self):
        return self._send('POST', '/api/admin/index/rollback')


# ---------- khung 2: người trực ----------

def operator_login(username, password):
    with _client() as c:
        return _check(c.post('/api/operator/login', json={'username': username, 'password': password}))


class Operator:
    def __init__(self, token):
        self.headers = {'Authorization': f'Bearer {token}'}

    def _req(self, method, path, body=None, timeout=60.0):
        with httpx.Client(base_url=BACKEND_URL, headers=self.headers, timeout=timeout) as c:
            return _check(c.request(method, path, json=body))

    def me(self):
        return self._req('GET', '/api/operator/me')

    def presence(self, status, force=False):
        return self._req('PUT', '/api/operator/presence', {'status': status, 'force': force})

    def online_staff(self):
        return self._req('GET', '/api/operator/staff/online')

    def queue(self):
        return self._req('GET', '/api/operator/queue')

    def mine(self):
        return self._req('GET', '/api/operator/mine')

    def view(self, conversation_id):
        return self._req('GET', f'/api/operator/conversations/{conversation_id}')

    def claim(self, conversation_id):
        return self._req('POST', f'/api/operator/conversations/{conversation_id}/claim')

    def check(self, conversation_id, text):
        return self._req('POST', f'/api/operator/conversations/{conversation_id}/check',
                         {'text': text}, timeout=120.0)

    def send(self, conversation_id, text, suggestion_id=None, guard_check_id=None,
             confirm_reason=None):
        return self._req('POST', f'/api/operator/conversations/{conversation_id}/send',
                         {'text': text, 'suggestion_id': suggestion_id,
                          'guard_check_id': guard_check_id, 'confirm_reason': confirm_reason},
                         timeout=120.0)

    def regenerate(self, conversation_id, instruction=None):
        return self._req('POST', f'/api/operator/conversations/{conversation_id}/suggestions',
                         {'instruction': instruction})

    def discard(self, suggestion_id):
        return self._req('POST', f'/api/operator/suggestions/{suggestion_id}/discard')

    def transfer(self, conversation_id, to_staff_id, note):
        return self._req('POST', f'/api/operator/conversations/{conversation_id}/transfer',
                         {'to_staff_id': to_staff_id, 'note': note})

    def respond_transfer(self, conversation_id, accept):
        return self._req('POST', f'/api/operator/conversations/{conversation_id}/transfer/respond',
                         {'accept': accept})

    def escalate(self, conversation_id, level, reason):
        return self._req('POST', f'/api/operator/conversations/{conversation_id}/escalate',
                         {'level': level, 'reason': reason})

    def close(self, conversation_id):
        return self._req('POST', f'/api/operator/conversations/{conversation_id}/close')

    def update_profile(self, conversation_id, fields):
        return self._req('PUT', f'/api/operator/conversations/{conversation_id}/profile',
                         {'fields': fields})
