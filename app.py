from flask import Flask, request, render_template_string, jsonify
import time, hmac, hashlib, requests, os
from dotenv import load_dotenv

# === LOAD ENV ===
load_dotenv()

app = Flask(__name__)

PARTNER_ID = int(os.getenv("PARTNER_ID", "0"))
PARTNER_KEY = os.getenv("PARTNER_KEY", "")
SHOP_ID = int(os.getenv("SHOP_ID", "0"))
SMS_API_KEY = os.getenv("SMS_API_KEY", "")
COUNTRY_CODE = int(os.getenv("COUNTRY_CODE", "6"))

# Simpan token Shopee dalam memory (sementara)
ACCESS_TOKEN = None
REFRESH_TOKEN = None

# Mapping produk Shopee ke service SMS-Activate
SERVICE_MAP = {
    "zus": "aik",
    "kfc": "fz",
    "chagee": "bwx",
    "tealive": "avb"
}

# Logo URL
LOGO_MAP = {
    "zus": "https://seeklogo.com/images/Z/zus-coffee-logo.png",
    "tealive": "https://seeklogo.com/images/T/tealive-logo.png",
    "kfc": "https://seeklogo.com/images/K/kfc-logo.png",
    "chagee": "https://seeklogo.com/images/C/chagee-logo.png"
}

# === HTML ===
HTML_FORM = """
<!DOCTYPE html>
<html>
<head>
<title>Redeem Virtual Number</title>
<script>
let activationId = null;
let countdown = 120;

function updateTimer() {
    if (countdown > 0) {
        countdown--;
        document.getElementById("timer").innerText = "Masa tinggal: " + countdown + "s";
    } else {
        document.getElementById("timer").innerText = "Masa habis!";
    }
}

function checkOTP() {
    if (activationId && countdown > 0) {
        fetch("/check_otp?id=" + activationId)
        .then(r => r.json())
        .then(data => {
            if (data.code) {
                document.getElementById("otp").innerText = "Kod OTP: " + data.code;
            } else {
                document.getElementById("otp").innerText = "Sedang tunggu OTP...";
            }
        })
        .catch(err => {
            document.getElementById("otp").innerText = "Ralat semak OTP!";
        });
    }
}

setInterval(updateTimer, 1000);
setInterval(checkOTP, 15000);
</script>
</head>
<body>
<h2>Pilih Produk & Masukkan Order ID Shopee</h2>
<form method="POST">
<select name="product_choice" required>
<option value="">-- Pilih Produk --</option>
<option value="zus">Zus Coffee</option>
<option value="tealive">Tealive</option>
<option value="kfc">KFC</option>
<option value="chagee">Chagee</option>
</select>
<br><br>
<input type="text" name="order_sn" placeholder="Order ID Shopee" required>
<button type="submit">Redeem</button>
</form>

{% if product %}
<h3>Produk: {{ product }}</h3>
{% if logo %}
<img src="{{ logo }}" alt="{{ product }}" style="width:120px;height:auto;">
{% endif %}
{% endif %}

{% if number %}
<h3>Nombor Anda: {{ number }}</h3>
<p id="otp">Sedang tunggu OTP...</p>
<p id="timer">Masa tinggal: 120s</p>
<script>
activationId = "{{ activation_id }}";
checkOTP();
</script>
{% endif %}

{% if error %}
<p style="color:red">{{ error }}</p>
{% endif %}
</body>
</html>
"""

# === SIGNATURE SHOPEE ===
def make_signature(path, timestamp, body=""):
    base_string = f"{PARTNER_ID}{path}{timestamp}{body}"
    return hmac.new(
        PARTNER_KEY.encode(),
        base_string.encode(),
        hashlib.sha256
    ).hexdigest()

# === CHECK ORDER ===
def check_order(order_sn):
    global ACCESS_TOKEN
    path = "/api/v2/order/get_order_detail"
    url = "https://partner.shopeemobile.com" + path
    timestamp = int(time.time())
    sign = make_signature(path, timestamp)

    payload = {
        "partner_id": PARTNER_ID,
        "shop_id": SHOP_ID,
        "timestamp": timestamp,
        "sign": sign,
        "order_sn_list": [order_sn]
    }

    headers = {}
    if ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

# === GET NUMBER ===
def get_virtual_number(service, country=COUNTRY_CODE):
    url = f"https://api.sms-activate.org/stubs/handler_api.php?api_key={SMS_API_KEY}&action=getNumber&service={service}&country={country}"
    try:
        r = requests.get(url, timeout=10).text
        parts = r.split(":")
        if parts[0] == "ACCESS_NUMBER":
            return {"id": parts[1], "number": parts[2]}
        return None
    except Exception:
        return None

# === GET OTP ===
def get_status(activation_id):
    url = f"https://api.sms-activate.org/stubs/handler_api.php?api_key={SMS_API_KEY}&action=getStatus&id={activation_id}"
    try:
        r = requests.get(url, timeout=10).text
        if r.startswith("STATUS_OK"):
            return r.split(":")[1]
        return None
    except Exception:
        return None

@app.route("/", methods=["GET", "POST"])
def redeem():
    number, error, activation_id, product, logo = None, None, None, None, None

    if request.method == "POST":
        order_sn = request.form["order_sn"]
        product_choice = request.form.get("product_choice")

        order_info = check_order(order_sn)

        if not order_info.get("error") and "response" in order_info:
            try:
                product_name = order_info["response"]["order_list"][0]["item_list"][0]["item_name"].lower()
                product = product_choice if product_choice else product_name

                service_code = SERVICE_MAP.get(product_choice)
                if service_code:
                    vnum = get_virtual_number(service=service_code)
                    if vnum:
                        number = vnum["number"]
                        activation_id = vnum["id"]
                        logo = LOGO_MAP.get(product_choice)
                    else:
                        error = "Gagal tempah nombor (tiada nombor tersedia)."
                else:
                    error = f"Produk '{product}' tiada dalam mapping."
            except Exception as e:
                error = f"Ralat proses order: {e}"
        else:
            error = f"Gagal dapatkan maklumat order: {order_info.get('message', 'Tidak diketahui')}"

    return render_template_string(
        HTML_FORM,
        product=product,
        number=number,
        activation_id=activation_id,
        error=error,
        logo=logo
    )

@app.route("/check_otp")
def check_otp():
    activation_id = request.args.get("id")
    otp = get_status(activation_id)
    return jsonify({"code": otp})

# === CALLBACK SHOPEE ===
@app.route("/callback")
def callback():
    global ACCESS_TOKEN, REFRESH_TOKEN

    code = request.args.get("code")
    shop_id = request.args.get("shop_id")

    if not code:
        return "Callback error: tiada code!"

    # Exchange code for access_token
    path = "/api/v2/auth/token/get"
    url = "https://partner.shopeemobile.com" + path
    timestamp = int(time.time())

    body = {
        "code": code,
        "partner_id": PARTNER_ID,
        "shop_id": int(shop_id)
    }

    sign = make_signature(path, timestamp, str(body))

    try:
        r = requests.post(url, json=body, params={
            "partner_id": PARTNER_ID,
            "timestamp": timestamp,
            "sign": sign
        }, timeout=10)

        data = r.json()
        ACCESS_TOKEN = data.get("access_token")
        REFRESH_TOKEN = data.get("refresh_token")

        return f"Callback berjaya!<br>Shop ID={shop_id}<br>Access Token={ACCESS_TOKEN}<br>Refresh Token={REFRESH_TOKEN}"
    except Exception as e:
        return f"Ralat callback: {e}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
