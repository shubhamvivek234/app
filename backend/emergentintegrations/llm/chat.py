
class UserMessage:
    def __init__(self, text):
        self.text = text

class LlmChat:
    def __init__(self, api_key, session_id, system_message):
        self.api_key = api_key
        self.session_id = session_id
        self.system_message = system_message

    def with_model(self, provider, model):
        return self

    async def send_message(self, user_message):
        return "This is a mocked AI response based on: " + user_message.text
