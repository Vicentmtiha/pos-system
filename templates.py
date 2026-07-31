import requests

# 1. API ya SMS (Mfano: Beem Africa / NextSMS / Africa's Talking)
BEEM_API_KEY = "YOUR_BEEM_API_KEY"
BEEM_SECRET_KEY = "YOUR_BEEM_SECRET_KEY"
SMS_SENDER_ID = "INFO" # Jina la biashara yako lililosajiliwa

def send_normal_sms(phone_number: str, message: str):
    """Kutuma SMS ya Kawaida"""
    url = "https://api.beem.africa/v1/send"
    payload = {
        "source_addr": SMS_SENDER_ID,
        "schedule_time": "",
        "message": message,
        "recipients": [
            {"recipient_id": 1, "dest_addr": phone_number}
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {BEEM_API_KEY}:{BEEM_SECRET_KEY}"
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"SMS Error: {e}")
        return False


# 2. API ya WhatsApp (Mfano: UltraMsg / Green API)
ULTRAMSG_INSTANCE_ID = "instanceXXXXX"
ULTRAMSG_TOKEN = "YOUR_ULTRAMSG_TOKEN"

def send_whatsapp_msg(phone_number: str, message: str):
    """Kutuma Ujumbe wa WhatsApp"""
    url = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE_ID}/messages/chat"
    payload = {
        "token": ULTRAMSG_TOKEN,
        "to": phone_number,
        "body": message
    }
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    try:
        response = requests.post(url, data=payload, headers=headers, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"WhatsApp Error: {e}")
        return False


# 3. Kazi Kuu Inayounganisha Zote Mbili (Unified Service)
def send_multi_channel_notification(phone_number: str, message: str, send_sms: bool = True, send_whatsapp: bool = True):
    """Kutuma WhatsApp na SMS kwa Pamoja au Moja Wapo"""
    # Rekebisha namba ya simu ikae kwenye muundo wa kimataifa (k.m. 255712345678)
    clean_phone = phone_number.strip().replace("+", "")
    if clean_phone.startswith("0"):
        clean_phone = "255" + clean_phone[1:]

    # Tuma WhatsApp
    if send_whatsapp:
        send_whatsapp_msg(clean_phone, message)

    # Tuma SMS ya Kawaida
    if send_sms:
        send_normal_sms(clean_phone, message)
