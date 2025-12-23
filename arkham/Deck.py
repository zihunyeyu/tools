from pprint import pprint

from Toolkits.web_funcs import get_json

api_url = r'https://zh.arkhamdb.com/api/public/deck/{deck_id}'



def main():
    deck_data = get_json(api_url.format(deck_id='5154174'))
    pprint(deck_data)


if __name__ == '__main__':
    main()