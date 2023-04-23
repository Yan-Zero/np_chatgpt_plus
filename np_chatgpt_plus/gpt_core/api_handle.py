from revChatGPT.recipient import Recipient


class UserAPIManager:
    def __init__(self):
        self.user_apis: dict[str, dict[str, Recipient]] = {}

    def activate_api(self, user_id, api_name, api_instance):
        """激活一个 API"""
        if user_id not in self.user_apis:
            self.user_apis[user_id] = {}
        self.user_apis[user_id][api_name] = api_instance

    def deactivate_api(self, user_id: str, api_name: str):
        if user_id in self.user_apis and api_name in self.user_apis[user_id]:
            del self.user_apis[user_id][api_name]

    def get_active_apis(self, user_id: str) -> dict[str, Recipient]:
        if user_id not in self.user_apis:
            return {}
        return self.user_apis[user_id]

    def get_active_api(self, user_id, api_name):
        if user_id not in self.user_apis or api_name not in self.user_apis[user_id]:
            return None
        return self.user_apis[user_id][api_name]

    def clear_user_apis(self, user_id):
        if user_id in self.user_apis:
            del self.user_apis[user_id]


user_api_manager = UserAPIManager()
