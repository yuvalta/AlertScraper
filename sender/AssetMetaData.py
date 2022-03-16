import json


class Asset:
    url = None
    users = []
    price = None
    error_message = None
    need_to_notify = False

    def __init__(self, url):
        self.url = url

    def __init__(self, url, user_list):
        self.url = url
        self.users = user_list

    def __init__(self, url, user_list, price, error_message, need_to_notify):
        self.url = url
        self.users = user_list
        self.price = price
        self.error_message = error_message
        self.need_to_notify = need_to_notify

    def add_user(self, user):
        self.users.append(user)

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=True, indent=4)
