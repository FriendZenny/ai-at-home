import json
import os
import requests

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(_CONFIG_PATH) as _f:
    _config = json.load(_f)

API_URL = _config["api_url"]
CONTEXT_LENGTH = _config["context_length"]
# ~4 chars per token is a conservative estimate; reserves headroom for the response
_PROMPT_BUDGET = (CONTEXT_LENGTH - _config["max_response_tokens"]) * 4

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "avatar-assets")
_BEHAVIOR_PATH = os.path.join(os.path.dirname(__file__), "behavior_prompt.txt")

with open(_BEHAVIOR_PATH) as _f:
    _DEFAULT_BEHAVIOR = _f.read().strip()


def update_user_config(name: str, description: str):
    """Persist user name and description to config.json."""
    _config["user_name"] = name
    _config["user_description"] = description
    with open(_CONFIG_PATH, "w") as f:
        json.dump(_config, f, indent=4)


def list_profiles():
    """Return sorted list of profile IDs (avatar-assets subdirs that have a profile.json)."""
    if not os.path.isdir(_ASSETS_DIR):
        return []
    return sorted(
        name for name in os.listdir(_ASSETS_DIR)
        if os.path.isfile(os.path.join(_ASSETS_DIR, name, "profile.json"))
    )


def load_profile(profile_id):
    """Return the parsed profile.json for the given profile ID."""
    path = os.path.join(_ASSETS_DIR, profile_id, "profile.json")
    with open(path) as f:
        return json.load(f)


def import_tavern_card(png_path: str) -> str:
    """Parse a SillyTavern character card PNG and create a profile directory.

    Returns the new profile_id on success, raises on failure.
    """
    import base64
    import shutil
    from PIL import Image

    img = Image.open(png_path)
    chara_b64 = img.info.get("chara")
    if not chara_b64:
        raise ValueError("No 'chara' metadata found — not a valid Tavern card.")

    card = json.loads(base64.b64decode(chara_b64))
    # Support both V1 (flat) and V2 (nested under "data")
    data = card.get("data", card)

    name = data.get("name", "Unknown").strip()
    parts = [data.get("description", ""), data.get("personality", ""), data.get("scenario", "")]
    description = "\n\n".join(p.strip() for p in parts if p.strip())
    behavior = data.get("system_prompt", "").strip() or None

    profile_id = name.lower().replace(" ", "_")
    target_dir = os.path.join(_ASSETS_DIR, profile_id)
    os.makedirs(target_dir, exist_ok=True)

    profile_data = {"name": name, "description": description}
    if behavior:
        profile_data["behavior"] = behavior

    with open(os.path.join(target_dir, "profile.json"), "w") as f:
        json.dump(profile_data, f, indent=2)

    shutil.copy(png_path, os.path.join(target_dir, "default.png"))
    return profile_id

# Template tags for Tekken format
START_TAG = "[INST]"
END_TAG = "[/INST]"
AGENT_END_TAG = "</s>"

_MEMORIES_DIR = os.path.join(os.path.dirname(__file__), "memories")

class ChatSession:
    def __init__(self, profile_id="rina"):
        profile = load_profile(profile_id)
        self.agent_name = profile["name"]
        self.profile_id = profile_id
        self.user_name = _config.get("user_name", "User")
        self.user_description = _config.get("user_description", "")
        subs = {"{user_name}": self.user_name, "{agent_name}": self.agent_name}

        description = profile.get("description", profile.get("prompt", ""))
        behavior = profile.get("behavior") or _DEFAULT_BEHAVIOR
        for k, v in subs.items():
            description = description.replace(k, v)
            behavior = behavior.replace(k, v)

        user_context = f"The user's name is {self.user_name}."
        if self.user_description:
            user_context += f" {self.user_description}"

        self._memory_path = os.path.join(_MEMORIES_DIR, f"{profile_id}.json")
        self._system_header = (
            f"<s>[SYSTEM_PROMPT]\n{behavior}\n\n{description}\n\n{user_context}\n[/SYSTEM_PROMPT]\n"
            f"{self.agent_name}:\nUnderstood.\n{AGENT_END_TAG}\n"
        )
        self._turns = []  # list of ("user"|"assistant", text)
        self._load()

    def _load(self):
        if os.path.exists(self._memory_path):
            with open(self._memory_path) as f:
                self._turns = [tuple(t) for t in json.load(f)]
            print(f"[Resumed conversation with {len(self._turns) // 2} previous exchange(s).]")
            last_reply = next((t for r, t in reversed(self._turns) if r == "assistant"), None)
            if last_reply:
                print(f"\n{self.agent_name}: {last_reply}\n")

    def _save(self):
        os.makedirs(_MEMORIES_DIR, exist_ok=True)
        with open(self._memory_path, "w") as f:
            json.dump(self._turns, f)

    def reset(self):
        self._turns = []
        if os.path.exists(self._memory_path):
            os.remove(self._memory_path)

    def pop_last_exchange(self):
        """Remove the last assistant reply and the preceding user message.

        Returns the user message text so the caller can re-send it, or None
        if there is no complete exchange to pop.
        """
        if (len(self._turns) >= 2
                and self._turns[-1][0] == "assistant"
                and self._turns[-2][0] == "user"):
            self._turns.pop()             # drop assistant reply
            _, user_text = self._turns.pop()  # drop user turn, keep text
            self._save()
            return user_text
        return None

    def append_user(self, message):
        self._turns.append(("user", message.strip()))

    def append_assistant_reply(self, reply):
        self._turns.append(("assistant", reply.strip()))
        self._save()

    @property
    def token_estimate(self):
        """Rough estimate of current context token usage (~4 chars/token)."""
        chars = len(self._system_header)
        for _, text in self._turns:
            chars += len(text) + 20  # +20 per turn for formatting tags
        return chars // 4

    def get_prompt(self):
        formatted = []
        for role, text in self._turns:
            if role == "user":
                formatted.append(f"{START_TAG}{self.user_name}:\n{text}\n{END_TAG}\n")
            else:
                formatted.append(f"{self.agent_name}:\n{text}\n{AGENT_END_TAG}\n")

        # Trim oldest exchange pairs until the prompt fits within budget
        while len(formatted) >= 2 and len(self._system_header) + sum(len(t) for t in formatted) > _PROMPT_BUDGET:
            formatted.pop(0)
            formatted.pop(0)

        return self._system_header + "".join(formatted) + f"{self.agent_name}:\n"

def stream_bot_reply(chat_session: ChatSession, user_input: str):
    """Yields tokens as they arrive. Saves the full reply to session when exhausted."""
    chat_session.append_user(user_input)

    payload = {
        "prompt": chat_session.get_prompt(),
        "temperature": _config["temperature"],
        "top_p": _config["top_p"],
        "max_length": _config["max_response_tokens"],
        "dry_sequence_breakers": "[\"\\n\",\":\",\"\\\"\",\"*\"]",
        "sampler_order": [6, 0, 1, 3, 4, 2, 5],
        "stop_sequence": [AGENT_END_TAG, START_TAG],
    }

    reply_text = ""
    with requests.post(API_URL, json=payload, stream=True, timeout=(10, 180)) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8")
            if not text.startswith("data: "):
                continue
            payload_str = text[6:]
            if payload_str == "[DONE]":
                break
            try:
                data = json.loads(payload_str)
            except json.JSONDecodeError:
                continue
            token = data.get("token", "")
            reply_text += token
            yield token

    chat_session.append_assistant_reply(reply_text)


def detect_emotion(reply_text: str, emotions: list) -> str:
    """Ask the model to classify reply_text into one of the available emotion labels.

    Returns one of the strings in `emotions`, falling back to 'default' on any failure.
    """
    emotion_list = ", ".join(emotions)
    prompt = (
        f"{START_TAG}Classify the emotional tone of the following text. "
        f"Reply with exactly one word from this list: {emotion_list}. "
        f"Do not explain. Just the one word.\n\n"
        f"Text:\n\"{reply_text[:600]}\"\n{END_TAG}\n"
        f"Emotion:"
    )
    payload = {
        "prompt": prompt,
        "max_length": 8,
        "temperature": 0.1,
        "top_p": 1.0,
        "sampler_order": [6, 0, 1, 3, 4, 2, 5],
        "stop_sequence": ["\n", START_TAG, AGENT_END_TAG],
    }
    result = ""
    try:
        with requests.post(API_URL, json=payload, stream=True, timeout=(10, 30)) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                text = line.decode("utf-8")
                if not text.startswith("data: "):
                    continue
                payload_str = text[6:]
                if payload_str == "[DONE]":
                    break
                try:
                    data = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue
                result += data.get("token", "")
    except Exception:
        return "default"

    word = result.strip().lower().split()[0] if result.strip() else "default"
    return word if word in emotions else "default"
