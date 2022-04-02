import json


class Asset:
    contract_id = None
    users = []
    price = None
    error_message = None
    need_to_notify = False
    action = None

    def __init__(self, contract_id):
        self.contract_id = contract_id

    def __init__(self, contract_id, user_list):
        self.contract_id = contract_id
        self.users = user_list

    def __init__(self, contract_id, user_list, price, error_message, need_to_notify, action):
        self.contract_id = contract_id
        self.users = user_list
        self.price = price
        self.error_message = error_message
        self.need_to_notify = need_to_notify
        self.action = action

    def add_user(self, user):
        self.users.append(user)

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=True, indent=4)
