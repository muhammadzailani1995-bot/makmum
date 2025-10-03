from flask import Flask, request, render_template_string, jsonify
import time, hmac, hashlib, requests, os, json
from dotenv import load_dotenv

# =========================
# LOAD ENV
# =========================
load_dotenv()

app = Flask(__name__)

# =========================
# CONFIG / ENV
# =========================
PARTNER_ID   = int(os.getenv("PARTNER_ID", "0"))
PARTNER_KEY  = os.getenv("PARTNER_KEY", "")
SHOP_ID      = int(os.getenv("SHOP_ID", "0"))  # optional (mode global tak wajib)
SMS_API_KEY  = os.getenv("SMS_API_KEY", "")
COUNTRY_CODE = int(os.getenv("COUNTRY_CODE", "7"))  # Malaysia = 7

# Gambar: pilih salah satu – URL ATAU BASE64 (data:image/...)
# Contoh URL: "https://example.com/redeem.png"
REDEEM_IMAGE_URL = os.getenv("REDEEM_IMAGE_URL", "")
# Contoh BASE64: "data:image/png;base64,iVBORw0KGgoAAA..."
REDEEM_IMAGE_BASE64 = os.getenv("REDEEM_IMAGE_BASE64", "")

ACCESS_TOKEN  = os.getenv("ACCESS_TOKEN") or None
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN") or None

# =========================
# MAPPING PRODUK -> SMS-ACTIVATE service code + Logo
# =========================
SERVICE_MAP = {
    "zus": "aik",
    "kfc": "fz",
    "chagee": "bwx",
    "tealive": "avb"
}
LOGO_MAP = {
    "zus": "https://seeklogo.com/images/Z/zus-coffee-logo.png",
    "tealive": "https://seeklogo.com/images/T/tealive-logo.png",
    "kfc": "https://seeklogo.com/images/K/kfc-logo.png",
    "chagee": "https://seeklogo.com/images/C/chagee-logo.png"
}

# =========================
# HTML TEMPLATE
# =========================
HTML_PAGE = """
<!DOCTYPE html>
<html lang="ms">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Redeem Virtual Number</title>
<style>
  :root{
    --blue:#e6f4ff;
    --ink:#0b2a54;
    --card:#ffffff;
    --muted:#5c6b7a;
    --accent:#1a73e8;
  }
  *{box-sizing:border-box}
  body{
    margin:0; padding:0;
    background:var(--blue);
    font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Arial,sans-serif;
    color:var(--ink);
  }
  .wrap{
    min-height:100dvh;
    display:flex; align-items:center; justify-content:center;
    position:relative; overflow:hidden; padding:24px;
  }
  /* Watermark MR.ROBOT */
  .wm{
    position:absolute; inset:0; display:grid; place-items:center;
    pointer-events:none; user-select:none; opacity:0.08;
    font-weight:900; letter-spacing:.2em; font-size:15vw; color:#0b2a54;
    transform:rotate(-15deg);
  }
  .card{
    width:100%; max-width:720px; background:var(--card);
    border-radius:18px; padding:22px 18px; box-shadow:0 10px 30px rgba(0,0,0,.08);
    position:relative; z-index:2;
  }
  h1{margin:0 0 6px; text-align:center; font-size:clamp(24px,5.5vw,34px)}
  h2{margin:8px 0; text-align:center; font-size:clamp(20px,4.6vw,28px); color:var(--muted)}
  form{display:flex; flex-direction:column; gap:12px; align-items:center; margin-top:8px}
  select,input{
    width:100%; max-width:560px; font-size:20px; padding:12px 14px;
    border:1px solid #cfe1ff; border-radius:12px; outline:none;
  }
  button{
    font-size:20px; padding:12px 20px; border-radius:12px; border:none;
    background:var(--accent); color:white; cursor:pointer;
  }
  button:active{transform:translateY(1px)}
  .logos{display:flex; gap:18px; justify-content:center; flex-wrap:wrap; margin:4px 0 10px}
  .logos img{height:44px; width:auto; object-fit:contain; filter:drop-shadow(0 2px 4px rgba(0,0,0,.12))}
  .result{margin-top:14px; text-align:center}
  .row{display:flex; gap:8px; justify-content:center; align-items:center; flex-wrap:wrap; margin:8px 0}
  .pill{
    background:#f2f7ff; border:1px dashed #b7d3ff; padding:10px 14px; border-radius:12px;
    font-size:20px; font-weight:700; color:#1d4ed8; min-width:220px;
  }
  .copy{background:#eef5ff; color:#0b50c8; border:1px solid #cfe1ff}
  #otp,#timer{font-size:22px; font-weight:800; color:#0b50c8}
  .err{color:#c62828; font-size:20px; font-weight:700; margin-top:6px}
  .ok{color:#2e7d32; font-size:20px; font-weight:700; margin-top:6px}
  .toggle{
    display:block; text-align:center; margin:20px auto 8px;
    font-weight:900; font-size:clamp(18px,4.4vw,26px); color:#0b50c8; text-decoration:underline; cursor:pointer;
  }
  .redeem-img{display:none; width:min(92%,680px); height:auto; margin:8px auto 0; border-radius:12px; box-shadow:0 10px 28px rgba(0,0,0,.12)}
  .hint{font-size:14px; color:#6b7280; text-align:center; margin-top:6px}
</style>
<script>
  let activationId = null;
  let countdown = 120;
  function updateTimer(){
    const t = document.getElementById("timer");
    if(!t) return;
    if(countdown>0){ countdown--; t.innerText = "Masa tinggal: " + countdown + "s"; }
    else{ t.innerText = "Masa habis!"; }
  }
  function checkOTP(){
    if(activationId && countdown>0){
      fetch("/check_otp?id=" + activationId)
      .then(r => r.json())
      .then(data => {
        const el = document.getElementById("otp");
        if(!el) return;
        if (data.code){ el.innerText = "Kod OTP: " + data.code; }
        else { el.innerText = "Sedang tunggu OTP..."; }
      }).catch(()=>{ const el=document.getElementById("otp"); if(el) el.innerText="Ralat semak OTP!"; });
    }
  }
  function copyText(selId){
    const n = document.getElementById(selId);
    if(!n) return;
    const text = n.innerText.replace(/^.*?:\s*/, ""); // buang label "Nombor: "
    navigator.clipboard.writeText(text).then(()=>{
      const btn = document.getElementById("btn-"+selId);
      if(btn){ const old=btn.innerText; btn.innerText="Disalin!"; setTimeout(()=>btn.innerText=old,1200); }
    });
  }
  function toggleRedeemImage(){
    const img = document.getElementById("redeemImage");
    if(!img) return;
    img.style.display = (img.style.display === "none" || img.style.display === "") ? "block" : "none";
  }
  setInterval(updateTimer, 1000);
  setInterval(checkOTP, 15000);
</script>
</head>
<body>
  <div class="wrap">
    <div class="wm">MR.ROBOT</div>
    <div class="card">

      {% if not is_callback %}
      <h1>Redeem Virtual Number</h1>
      <h2>Masukkan Order ID Shopee & Pilih Produk</h2>

      <div class="logos">
        {% for key,logo in logos.items() %}
          <img src="{{ logo }}" alt="{{ key }}">
        {% endfor %}
      </div>

      <form method="POST" action="/">
        <select name="product_choice" required>
          <option value="">— Pilih Produk —</option>
          <option value="zus" {% if last_choice=='zus' %}selected{% endif %}>Zus Coffee</option>
          <option value="tealive" {% if last_choice=='tealive' %}selected{% endif %}>Tealive</option>
          <option value="kfc" {% if last_choice=='kfc' %}selected{% endif %}>KFC</option>
          <option value="chagee" {% if last_choice=='chagee' %}selected{% endif %}>Chagee</option>
        </select>
        <input type="text" name="order_sn" placeholder="Order ID Shopee" value="{{ last_order or '' }}" required>
        <button type="submit">Redeem</button>
      </form>

      <!-- Toggle gambar -->
      {% if show_toggle %}
        <a class="toggle" onclick="toggleRedeemImage()">DAPATKAN NOMBOR ORDER DI SINI</a>
        {% if redeem_image %}
          <img id="redeemImage" class="redeem-img" src="{{ redeem_image }}" alt="Redeem Info">
        {% endif %}
        <p class="hint">Tekan teks di atas untuk papar/sembunyi gambar.</p>
      {% endif %}
      {% endif %}

      {% if product %}
        <div class="result">
          <h2>Produk: {{ product|title }}</h2>
          {% if logo %}<img src="{{ logo }}" alt="{{ product }}" style="height:56px;object-fit:contain;margin:6px auto 12px;display:block;">{% endif %}
        </div>
      {% endif %}

      {% if number %}
        <div class="row">
          <div id="num" class="pill">Nombor: {{ number }}</div>
          <button id="btn-num" class="copy" onclick="copyText('num')">Copy</button>
        </div>
        <p id="otp">Sedang tunggu OTP...</p>
        <p id="timer">Masa tinggal: 120s</p>
        <script>activationId = "{{ activation_id }}"; checkOTP();</script>
      {% endif %}

      {% if error %}<p class="err">{{ error }}</p>{% endif %}
      {% if ok %}<p class="ok">{{ ok }}</p>{% endif %}

      {% if is_callback and access_token %}
        <div class="result">
          <h2>✅ Callback Berjaya</h2>
          <div class="row"><div class="pill">Shop ID: {{ cb_shop_id }}</div></div>
          <div class="row"><div id="acc" class="pill">Access Token: {{ access_token }}</div><button id="btn-acc" class="copy" onclick="copyText('acc')">Copy</button></div>
          <div class="row"><div id="ref" class="pill">Refresh Token: {{ refresh_token }}</div><button id="btn-ref" class="copy" onclick="copyText('ref')">Copy</button></div>
          <p class="hint">Sila simpan token di .env (ACCESS_TOKEN, REFRESH_TOKEN) jika perlu.</p>
        </div>
      {% elif is_callback and not access_token %}
        <p class="err">❌ Callback error: tiada code atau token gagal dijana.</p>
      {% endif %}

    </div>
  </div>
</body>
</html>
"""

# =========================
# UTIL
# =========================
def make_signature(path, timestamp, body=""):
    base_string = f"{PARTNER_ID}{path}{timestamp}{body}"
    return hmac.new(PARTNER_KEY.encode(), base_string.encode(), hashlib.sha256).hexdigest()

def save_token(access_token, refresh_token):
    # Simpan juga ke .env untuk persist (jika dibenarkan)
    lines = []
    if os.path.exists(".env"):
        with open(".env","r") as f:
            lines = f.readlines()
    lines = [l for l in lines if not l.startswith("ACCESS_TOKEN") and not l.startswith("REFRESH_TOKEN")]
    lines.append(f"ACCESS_TOKEN={access_token or ''}\n")
    lines.append(f"REFRESH_TOKEN={refresh_token or ''}\n")
    with open(".env","w") as f:
        f.writelines(lines)

def check_order(order_sn):
    """
    Cuba dapatkan maklumat order daripada Shopee (LIVE).
    Jika ACCESS_TOKEN belum ada, Shopee mungkin reject — kita tetap cuba untuk debug.
    """
    global ACCESS_TOKEN
    path = "/api/v2/order/get_order_detail"
    url  = "https://partner.shopeemobile.com" + path
    ts   = int(time.time())
    sign = make_signature(path, ts)

    payload = {
        "partner_id": PARTNER_ID,
        "timestamp": ts,
        "sign": sign,
        "order_sn_list": [order_sn],
    }
    headers = {}
    if ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=12)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

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

def get_status(activation_id):
    url = f"https://api.sms-activate.org/stubs/handler_api.php?api_key={SMS_API_KEY}&action=getStatus&id={activation_id}"
    try:
        r = requests.get(url, timeout=10).text
        if r.startswith("STATUS_OK"):
            return r.split(":")[1]
        return None
    except Exception:
        return None

def resolve_redeem_image():
    """
    Kembalikan SRC gambar ikut keutamaan:
    1) REDEEM_IMAGE_BASE64 (data URI)
    2) REDEEM_IMAGE_URL
    3) Kuih kosong (None) -> seksyen gambar tak dipapar
    """
    if REDEEM_IMAGE_BASE64.strip():
        return REDEEM_IMAGE_BASE64.strip()
    if REDEEM_IMAGE_URL.strip():
        return REDEEM_IMAGE_URL.strip()
    return None

# =========================
# ROUTES
# =========================

@app.route("/", methods=["GET","POST"])
def index_or_callback():
    """
    ROOT "/"
    - Jika ada ?code=... daripada Shopee: proses callback & tebus token
    - Jika tiada: paparkan borang Redeem seperti biasa
    """
    global ACCESS_TOKEN, REFRESH_TOKEN

    # CASE A: Callback dari Shopee (ada code)
    code = request.args.get("code")
    shop_id = request.args.get("shop_id")
    if code:
        path = "/api/v2/auth/token/get"
        url  = "https://partner.shopeemobile.com" + path
        ts   = int(time.time())

        # Jika shop_id tak wujud, cuba fallback 0 / SHOP_ID env
        try:
            shop_id_int = int(shop_id) if shop_id else (SHOP_ID if SHOP_ID>0 else 0)
        except:
            shop_id_int = SHOP_ID if SHOP_ID>0 else 0

        body = {"code": code, "partner_id": PARTNER_ID, "shop_id": shop_id_int}
        body_str = json.dumps(body, separators=(',',':'))
        sign = make_signature(path, ts, body_str)

        try:
            r = requests.post(
                url,
                json=body,
                params={"partner_id": PARTNER_ID, "timestamp": ts, "sign": sign},
                timeout=12
            )
            data = r.json()
            ACCESS_TOKEN  = data.get("access_token")
            REFRESH_TOKEN = data.get("refresh_token")
            if ACCESS_TOKEN:
                save_token(ACCESS_TOKEN, REFRESH_TOKEN)
            return render_template_string(
                HTML_PAGE,
                is_callback=True,
                access_token=ACCESS_TOKEN,
                refresh_token=REFRESH_TOKEN,
                cb_shop_id=shop_id_int,
                product=None, number=None, activation_id=None,
                error=None, ok=None,
                logos=LOGO_MAP,
                last_order=None, last_choice=None,
                show_toggle=bool(resolve_redeem_image()),
                redeem_image=resolve_redeem_image()
            )
        except Exception as e:
            return render_template_string(
                HTML_PAGE,
                is_callback=True,
                access_token=None, refresh_token=None, cb_shop_id=shop_id,
                product=None, number=None, activation_id=None,
                error=f"❌ Ralat callback: {e}", ok=None,
                logos=LOGO_MAP,
                last_order=None, last_choice=None,
                show_toggle=bool(resolve_redeem_image()),
                redeem_image=resolve_redeem_image()
            )

    # CASE B: Papar borang / proses redeem
    number = error = activation_id = product = logo = ok = None
    last_order = None
    last_choice = None

    if request.method == "POST":
        last_order = request.form.get("order_sn") or ""
        last_choice = request.form.get("product_choice") or ""
        order_info = check_order(last_order)

        if not order_info.get("error") and "response" in order_info:
            try:
                # Ambil product daripada pilihan user; jika tak, fallback item_name order
                product = last_choice or order_info["response"]["order_list"][0]["item_list"][0]["item_name"].lower()
                service_code = SERVICE_MAP.get(last_choice)
                if service_code:
                    vnum = get_virtual_number(service=service_code)
                    if vnum:
                        number = vnum["number"]
                        activation_id = vnum["id"]
                        logo = LOGO_MAP.get(last_choice)
                        ok = "✅ Nombor berjaya ditempah. Tunggu OTP dihantar..."
                    else:
                        error = "❌ Gagal tempah nombor (tiada nombor tersedia)."
                else:
                    error = f"❌ Produk '{product}' tiada dalam mapping."
            except Exception as e:
                error = f"❌ Ralat proses order: {e}"
        else:
            error = "❌ Gagal dapatkan maklumat order Shopee. Pastikan app & shop telah authorize (LIVE)."

    return render_template_string(
        HTML_PAGE,
        is_callback=False,
        product=product, number=number, activation_id=activation_id,
        error=error, ok=ok, logo=logo,
        logos=LOGO_MAP,
        last_order=last_order, last_choice=last_choice,
        show_toggle=bool(resolve_redeem_image()),
        redeem_image=resolve_redeem_image()
    )

@app.route("/check_otp")
def check_otp():
    activation_id = request.args.get("id")
    otp = get_status(activation_id)
    return jsonify({"code": otp})

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    # Render akan set PORT env; local default 5000
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
