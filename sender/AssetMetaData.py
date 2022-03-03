import json


class Asset:
    url = None
    users = None
    price = None
    error_message = None

    def __init__(self, url, user_list):
        self.url = url
        self.users = user_list

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=True, indent=4)
