import logging
import re
from csv import DictWriter
from dataclasses import dataclass, field
from time import sleep
from typing import List, Dict, Tuple
from sys import argv

from furl import furl
from selenium.webdriver import Chrome, ChromeOptions, DesiredCapabilities

from credentials import USERNAME, PASSWORD

CARGOX_URL = furl('https://cargox.ru')
CARGOX_ALL_ORDERS_URL = furl("https://cargox.ru/request/all/?detail=1")
CARGOX_LOGIN_URL = furl('https://cargox.ru/accounts/login/')


logging.basicConfig(level=logging.ERROR,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='./logs/log')
logger = logging.getLogger('cargox_parser')
logger.setLevel(logging.INFO)


@dataclass
class OrderInfo:
    name: str = ''
    email: str = ''
    phone: str = ''
    link: str = ''
    extra_info: Dict[str, str] = field(default_factory=dict)


def get_driver(headless: bool =False) -> Chrome:
    options = ChromeOptions()

    capabilities = DesiredCapabilities.CHROME
    options.add_argument("--window-position=1920,50")
    options.add_argument("--window-size=1920,1000")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    if headless:
        options.add_argument("--headless")

    return Chrome("./webdriver/chromedriver", options=options,
                  desired_capabilities=capabilities)


def login(driver: Chrome) -> None:
    driver.get(CARGOX_LOGIN_URL.url)

    driver.find_element_by_id('id_username').send_keys(USERNAME)
    driver.find_element_by_id('id_password').send_keys(PASSWORD)
    driver.find_element_by_xpath(f'//input[@value="Войти"]').click()

    if driver.current_url == 'https://cargox.ru/request/all/':
        logger.info('Success login')
    else:
        logger.warning('Something went wrong during login')
        exit()


def get_last_page_number(driver: Chrome) -> int:
    navi_panel = driver.find_element_by_class_name('ul_navi')
    last_page_link = navi_panel.find_elements_by_tag_name('a')[-2]

    return int(last_page_link.text)


def get_order_paths(driver: Chrome) -> List[str]:
    last_page_number = get_last_page_number(driver)

    order_paths = []
    page_number = 1
    # last_page_number = 1  # временно
    while page_number <= last_page_number:
        order_block = driver.find_element_by_id("other_statement")
        for order_row in order_block.find_elements_by_xpath("//tbody/tr"):
            first_cell = order_row.find_element_by_tag_name("td")
            location_href = first_cell.get_attribute('onclick')
            order_path = re.search(r'(?<=\")[^\"]+', location_href).group(0)
            order_paths.append(order_path)
        sleep(1)

        page_number += 1
        CARGOX_ALL_ORDERS_URL.args['page'] = page_number
        driver.get(CARGOX_ALL_ORDERS_URL.url)

    return order_paths


def parse_extra_info(driver: Chrome) -> Tuple[Dict[str, str], List[str]]:
    info = {}
    fields = []
    tbl = driver.find_element_by_class_name("tbl")
    for tbl_row in tbl.find_elements_by_class_name("tbl_row"):
        divs = tbl_row.find_elements_by_tag_name('div')

        field_title = divs[0].text.strip(':').replace('\n', ' ')
        fields.append(field_title)
        info[field_title] = divs[1].text

    return info, fields


def parse_orders(driver: Chrome, order_paths: List[str]) -> Tuple[List[OrderInfo], List[str]]:
    orders_info = []
    fields = []
    for path in order_paths:
        order_info = OrderInfo()

        CARGOX_URL.path = path
        driver.get(CARGOX_URL.url)

        order_info.name = driver.find_element_by_class_name('site_a').text
        order_info.email = driver.find_element_by_class_name('mail_a').text
        order_info.phone = driver.find_element_by_class_name('tel_a').text
        order_info.link = driver.current_url

        # с полями странная ситуация, вероятно их количество может меняться,
        # поэтому выберем просто наиболее полный перечень полей
        extra_info, new_fields = parse_extra_info(driver)
        if set(new_fields) != set(fields):
            for item in new_fields:
                if item not in fields:
                    fields.append(item)
        order_info.extra_info = extra_info
        print(order_info, end='\n\n')

        orders_info.append(order_info)
        sleep(1)

    return orders_info, fields


def save_orders_info(orders_info: List[OrderInfo], fields: List[str]) -> None:
    with open('cargox_orders.csv', 'w') as file:
        field_names = ['Имя', 'Телефон', 'Email', 'Ссылка', *fields]

        writer = DictWriter(file, fieldnames=field_names, delimiter=';')
        writer.writeheader()
        for order_info in orders_info:
            try:
                writer.writerow({'Имя': order_info.name,
                                 'Телефон': order_info.phone,
                                 'Email': order_info.email,
                                 'Ссылка': order_info.link,
                                 **order_info.extra_info})
            except Exception as e:
                print(e)
                print(order_info.link)


def main(args: List[str]):
    driver = get_driver(headless=('headless' in args))

    login(driver)
    driver.get(CARGOX_ALL_ORDERS_URL.url)  # используем удобный вид для

    order_paths = get_order_paths(driver)

    orders_info, fields = parse_orders(driver, order_paths)
    save_orders_info(orders_info, fields)

    driver.close()


if __name__ == "__main__":
    arguments = [word.strip('--') for word in argv]
    main(arguments)
