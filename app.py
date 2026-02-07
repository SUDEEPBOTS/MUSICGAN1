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

# Helper to delete session file after work is done
def remove_session(phone):
    try:
        # Phone number se symbols hata kar filename banao
        clean_phone = phone.replace('+', '').replace(' ', '')
        filename = f"sess_{clean_phone}.session"
        if os.path.exists(filename):
            os.remove(filename)
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

    # Purani file agar ho toh delete karo
    remove_session(phone)

    async def process():
        clean_phone = phone.replace('+', '').replace(' ', '')
        # Yaha hum 'in_memory' HATA rahe hain aur file banayenge
        client = Client(f"sess_{clean_phone}", api_id=API_ID, api_hash=API_HASH)
        
        await client.connect()
        try:
            sent_code = await client.send_code(phone)
            # Connection disconnect karo par FILE rehne do
            await client.disconnect()
            return {"status": "success", "hash": sent_code.phone_code_hash}
        except Exception as e:
            await client.disconnect()
            remove_session(phone) # Error aaya toh file hata do
            return {"status": "error", "message": str(e)}

    return jsonify(run_async(process()))

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    phone = request.json.get('phone')
    code = request.json.get('code')
    hash_code = request.json.get('hash')
    
    async def process():
        clean_phone = phone.replace('+', '').replace(' ', '')
        # Wahi same session file dobara load karo
        client = Client(f"sess_{clean_phone}", api_id=API_ID, api_hash=API_HASH)
        
        await client.connect()
        try:
            await client.sign_in(phone, hash_code, code)
            string_session = await client.export_session_string()
            await client.disconnect()
            remove_session(phone) # Kaam ho gaya, file delete
            return {"status": "success", "session": string_session}
        except Exception as e:
            error_msg = str(e)
            if "SESSION_PASSWORD_NEEDED" in error_msg:
                await client.disconnect()
                # File delete mat karo, password step abhi baaki hai
                return {"status": "2fa_required"}
            else:
                await client.disconnect()
                return {"status": "error", "message": error_msg}

    return jsonify(run_async(process()))

@app.route('/verify_password', methods=['POST'])
def verify_password():
    phone = request.json.get('phone')
    password = request.json.get('password')
    
    async def process():
        clean_phone = phone.replace('+', '').replace(' ', '')
        # Same file load karo
        client = Client(f"sess_{clean_phone}", api_id=API_ID, api_hash=API_HASH)
        
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
