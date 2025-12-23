from pprint import pprint

import requests

proxies = {
    'http': None,
    'https': None
}

def get_json(url):
    try:
        response = requests.get(url, proxies=proxies)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(str(e))
        return {}

def __get_json_test():
    test_url = r'https://zh.arkhamdb.com/api/public/card/01501'
    return get_json(test_url)

if __name__ == '__main__':
    # print('Hello web funcs')
    pprint(__get_json_test())