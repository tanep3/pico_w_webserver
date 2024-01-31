import network
import asyncio
from time import sleep
import machine
import ubinascii

# Wi-Fi ルーターのSSIDとパスワードです
# お使いの設定に書き換えてください
SSID = 'xxxxxx'
PASSWORD = 'xxxxxx'
PORT = 80
#ルーティングテーブル
ROOTING_TABLE = {
    '/': 'index.html',
    '/top': 'right.html',
    '/left': 'left.html',
    '/right': 'right.html',
    '/ledon': 'ledon.html',
    '/ledoff': 'ledoff.html',
    '/getTemperature': 'getTemperature.html',
    '/inputName': 'inputName.html',
}
#コンテントタイプ
CONTENT_TYPE = {
    'html': 'text/html',
    'jpg': 'image/jpg',
    'png': 'image/png',
    'ico': 'image/x-icon'
}
#アクションテーブル
#Raspberry Pi PICO Wで何か制御したいときは、ここに処理を記述してください
LED = machine.Pin("LED", machine.Pin.OUT)
TEMPERATURE_SENSOR = machine.ADC(4)
def get_temperature():
    conversion_factor = 3.3 / (65535)
    reading = TEMPERATURE_SENSOR.read_u16() * conversion_factor
    temperature = 27 - (reading - 0.706) / 0.001721
    return '{:.1f}'.format(temperature)

#(ルーティング名:関数名)
ACTION_TABLE = {
    '/ledon': lambda: LED.on(),
    '/ledoff': lambda: LED.off(),
    '/getTemperature': lambda: get_temperature(),
}

#POSTアクションテーブル
#POSTのときの処理をここに登録
POST_ACTION_TABLE = {
    '/inputName': lambda page_data, posted_data: post_name(page_data, posted_data)
}

#postページを加工する関数をここに登録
def post_name(page_data, posted_data):
    edited_page = str(page_data).format(posted_data['name'])
    return edited_page

# Webページを取得する関数
def get_page(file_name):
    open_mode = 'r'
    if get_file_type(file_name) != 'html':
        open_mode = 'rb'
    data = ''
    try:
        with open(file_name, open_mode) as f:
            data = f.read()
    except Exception as e:
        print(f'Error opening file: {e}')
        with open('NotFound.html', 'r') as f:
            data = f.read()
    return data

# WEBページをルーティングする関数
def rooting_from_url(rooting):
    #ファイル名指定だったら、ファイル名を返す
    if len(rooting.split('.')) >= 2:
        return rooting.split('/')[-1]
    #ルーティング表を参照して、ファイル名を返す
    if rooting in ROOTING_TABLE.keys():
        return ROOTING_TABLE[rooting]
    #各表になかったら、NotFound.htmlを返す
    return 'NotFound.html'

# WEBページからアクションを実行する関数
def action_from_page(rooting):
    if rooting in ACTION_TABLE.keys():
        return ACTION_TABLE[rooting]()
    return None

# urlからファイルタイプを取得する関数
def get_file_type(url):
    url_split = url.split('.')
    if len(url_split) == 1:
        mime_type = 'html'
    else:  
        mime_type = url_split[-1]
    return mime_type

# ファイルタイプからContent-Typeを取得する関数
def get_content_type(url):
    mime_type = get_file_type(url)
    content_type = ''
    if mime_type in CONTENT_TYPE.keys():
        content_type = f'HTTP/1.0 200 OK\r\nContent-type: {CONTENT_TYPE[mime_type]}\r\n\r\n'
    return content_type

# Wi-Fiに接続する関数
def connect_and_return_ip():
    #Connect to WLAN
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    while wlan.isconnected() == False:
        print('Waiting for connection...')
        sleep(1)
    ip = wlan.ifconfig()[0]
    print(f'Connected on {ip}')
    return ip

# GETメソッドの時の処理
def get_method(url):
    filename = rooting_from_url(url)
    #Raspberry Pi PICO Wに対するアクション実行
    value = action_from_page(url)
    page = get_page(filename)
    if value != None:
        page = str(page).format(value)
    return (get_content_type(url), page)

# POSTメソッドの時の処理
def post_method(url, posted_data):
    filename = rooting_from_url(url)
    page = get_page(filename)
    if url in POST_ACTION_TABLE.keys():
        page = POST_ACTION_TABLE[url](str(page), posted_data)
    return (get_content_type(url), page)

# URLデコードを行う関数
# micropythonにはurllib.parseモジュールはないため自前で実装
# '+' を ' ' に変換し、%xx 形式の文字列を対応するASCII文字に変換する
def url_decode(s):
    if '%' not in s:
        return s
    s_replaced = s.replace('+', ' ')
    s_decoded = ubinascii.unhexlify(s_replaced.replace('%', '').encode()).decode()
    return s_decoded

def get_posted_data(request):
    request_lines = request.decode('utf8').split('\r\n')
    posted_data = {key:url_decode(value) for key, value in [line.split('=') for line in request_lines[-1].split('&')]}
    return posted_data

# リクエストに対して、コンテントタイプとWebページを返す関数
def get_content_and_page(request):
    request_line = request.split(b'\r\n')[0].decode('utf-8')
    method = request_line.split()[0]
    url = request_line.split()[1]
    if method == 'GET':
        return get_method(url)
    elif method == 'POST':
        return post_method(url, get_posted_data(request)) 
    raise ValueError('method is not GET or POST')

# クライアント(ブラウザ)からの接続に対応する関数
async def async_server(reader, writer):
    request = await reader.read(1024)
    if len(request) == 0:
        return
    content_type , page = get_content_and_page(request)
    writer.write(content_type)
    writer.write(page)
    await writer.drain()
    await writer.wait_closed()

# メイン処理部分
# Wi-Fiに接続し、IPアドレスを取得します
ip = connect_and_return_ip()
# 非同期でWEBサーバを起動させます
loop = asyncio.new_event_loop()
coroutine = asyncio.start_server(async_server, ip, PORT)
server = loop.run_until_complete(coroutine)
try:
    loop.run_forever()
except KeyboardInterrupt:
    pass
finally:
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()
