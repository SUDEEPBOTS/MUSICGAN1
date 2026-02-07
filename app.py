from flask import Flask, render_template, request, jsonify
from pyrogram import Client
import asyncio
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- CONFIGURATION ---
API_ID = 33917975
API_HASH = "9ded8160307386acef2451d464e7a9b9"

# Helper to run async methods
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# Helper: Session file path (Safe /tmp folder)
def get_session_path(phone):
    # Phone number clean karo
    clean_phone = phone.replace('+', '').replace(' ', '')
    return f"sess_{clean_phone}"

# Helper: Delete session ONLY on success
def remove_session(phone):
    try:
        # Pyrogram workdir /tmp me files banayega
        clean_phone = phone.replace('+', '').replace(' ', '')
        file_path = f"/tmp/sess_{clean_phone}.session"
        if os.path.exists(file_path):
            os.remove(file_path)
    except:
        pass

@app.route('/health', methods=['GET', 'HEAD'])
def health_check():
    return 'Alive', 200

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/send_otp', methods=['POST'])
def send_otp():
    phone = request.json.get('phone')
    if not phone:
        return jsonify({"status": "error", "message": "Phone number required"})

    # Naya OTP mangwa rahe ho, toh purani file hata do
    remove_session(phone)

    async def process():
        session_name = get_session_path(phone)
        # WORKDIR ko /tmp set kiya hai taaki files safe rahein
        client = Client(
            name=session_name,
            api_id=API_ID,
            api_hash=API_HASH,
            workdir="/tmp",
            device_model="SudeepStringBot",  # Fixed Device Name
            app_version="1.0.0"
        )
        
        await client.connect()
        try:
            sent_code = await client.send_code(phone)
            await client.disconnect()
            return {"status": "success", "hash": sent_code.phone_code_hash}
        except Exception as e:
            await client.disconnect()
            # Yahan remove_session MAT karo. Agar error aaya to user retry karega.
            return {"status": "error", "message": str(e)}

    return jsonify(run_async(process()))

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    phone = request.json.get('phone')
    code = request.json.get('code')
    hash_code = request.json.get('hash')
    
    async def process():
        session_name = get_session_path(phone)
        
        # Check if session exists in /tmp
        if not os.path.exists(f"/tmp/{session_name}.session"):
             return {"status": "error", "message": "Session Timeout. Click 'Send OTP' again."}

        client = Client(
            name=session_name,
            api_id=API_ID,
            api_hash=API_HASH,
            workdir="/tmp",
            device_model="SudeepStringBot",
            app_version="1.0.0"
        )
        
        await client.connect()
        try:
            await client.sign_in(phone, hash_code, code)
            string_session = await client.export_session_string()
            await client.disconnect()
            remove_session(phone) # SUCCESS! Ab delete karo safe hai.
            return {"status": "success", "session": string_session}
        except Exception as e:
            error_msg = str(e)
            if "SESSION_PASSWORD_NEEDED" in error_msg:
                await client.disconnect()
                return {"status": "2fa_required"}
            else:
                await client.disconnect()
                # Yahan bhi file delete MAT karo. Shayad OTP typo ho.
                return {"status": "error", "message": error_msg}

    return jsonify(run_async(process()))

@app.route('/verify_password', methods=['POST'])
def verify_password():
    phone = request.json.get('phone')
    password = request.json.get('password')
    
    async def process():
        session_name = get_session_path(phone)
        client = Client(
            name=session_name,
            api_id=API_ID,
            api_hash=API_HASH,
            workdir="/tmp",
            device_model="SudeepStringBot",
            app_version="1.0.0"
        )
        
        await client.connect()
        try:
            await client.check_password(password)
            string_session = await client.export_session_string()
            await client.disconnect()
            remove_session(phone)
            return {"status": "success", "session": string_session}
        except Exception as e:
            await client.disconnect()
            return {"status": "error", "message": str(e)}

    return jsonify(run_async(process()))

if __name__ == '__main__':
    app.run(debug=True)
