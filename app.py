from flask import Flask, render_template, request, jsonify
from pyrogram import Client
import asyncio
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- CONFIGURATION (FIXED) ---
API_ID = 33917975
API_HASH = "9ded8160307386acef2451d464e7a9b9"

# Helper to run async pyrogram methods
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# Helper: Get Session Path (Saves in /tmp folder)
def get_session_path(phone):
    clean_phone = phone.replace('+', '').replace(' ', '')
    # Render par /tmp folder writable hota hai
    return f"/tmp/sess_{clean_phone}"

# Helper to delete session file after work is done
def remove_session(phone):
    try:
        session_path = get_session_path(phone)
        # Pyrogram .session extension khud add karta hai, isliye hume check karna padega
        if os.path.exists(f"{session_path}.session"):
            os.remove(f"{session_path}.session")
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

    remove_session(phone) # Purana file saaf karo

    async def process():
        session_path = get_session_path(phone)
        # Session path /tmp me point karega
        client = Client(session_path, api_id=API_ID, api_hash=API_HASH)
        
        await client.connect()
        try:
            sent_code = await client.send_code(phone)
            await client.disconnect()
            return {"status": "success", "hash": sent_code.phone_code_hash}
        except Exception as e:
            await client.disconnect()
            remove_session(phone)
            return {"status": "error", "message": str(e)}

    return jsonify(run_async(process()))

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    phone = request.json.get('phone')
    code = request.json.get('code')
    hash_code = request.json.get('hash')
    
    async def process():
        session_path = get_session_path(phone)
        
        # Check karo agar file exist karti hai
        if not os.path.exists(f"{session_path}.session"):
             return {"status": "error", "message": "Session file not found. Please resend OTP."}

        client = Client(session_path, api_id=API_ID, api_hash=API_HASH)
        
        await client.connect()
        try:
            await client.sign_in(phone, hash_code, code)
            string_session = await client.export_session_string()
            await client.disconnect()
            remove_session(phone) # Success! File delete
            return {"status": "success", "session": string_session}
        except Exception as e:
            error_msg = str(e)
            if "SESSION_PASSWORD_NEEDED" in error_msg:
                await client.disconnect()
                return {"status": "2fa_required"}
            else:
                await client.disconnect()
                # File delete mat karo, user code re-try kar sakta hai
                return {"status": "error", "message": error_msg}

    return jsonify(run_async(process()))

@app.route('/verify_password', methods=['POST'])
def verify_password():
    phone = request.json.get('phone')
    password = request.json.get('password')
    
    async def process():
        session_path = get_session_path(phone)
        client = Client(session_path, api_id=API_ID, api_hash=API_HASH)
        
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
