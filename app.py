from flask import Flask, render_template, request, jsonify
from pyrogram import Client
import asyncio
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- CONFIGURATION ---
# Bhai ye dhyan dena, API_ID bina quotes ke hona chahiye
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

# Helper: Session Path in /tmp (Safe folder for Render)
def get_session_name(phone):
    return f"sess_{str(phone).strip()}"

# Helper: Remove session
def remove_session(phone):
    try:
        session_name = get_session_name(phone)
        file_path = f"/tmp/{session_name}.session"
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
    # Force String Conversion for Phone
    phone = str(request.json.get('phone')).strip()
    
    if not phone:
        return jsonify({"status": "error", "message": "Phone number required"})

    remove_session(phone)

    async def process():
        session_name = get_session_name(phone)
        
        # API_ID ko int() me wrap kiya hai taaki error na aaye
        client = Client(
            name=session_name,
            api_id=int(API_ID), 
            api_hash=API_HASH,
            workdir="/tmp"
        )
        
        await client.connect()
        try:
            sent_code = await client.send_code(phone)
            await client.disconnect()
            return {"status": "success", "hash": sent_code.phone_code_hash}
        except Exception as e:
            await client.disconnect()
            return {"status": "error", "message": str(e)}

    return jsonify(run_async(process()))

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    # Sab kuch Force Convert karo taaki Type Error na aaye
    phone = str(request.json.get('phone')).strip()
    code = str(request.json.get('code')).strip()
    hash_code = request.json.get('hash')
    
    async def process():
        session_name = get_session_name(phone)
        
        if not os.path.exists(f"/tmp/{session_name}.session"):
             return {"status": "error", "message": "Session Timeout. Click 'Send OTP' again."}

        client = Client(
            name=session_name,
            api_id=int(API_ID), # Yaha bhi int() lagaya hai
            api_hash=API_HASH,
            workdir="/tmp"
        )
        
        await client.connect()
        try:
            # Code ko bhi str() me wrap kiya hai
            await client.sign_in(phone, hash_code, code)
            
            string_session = await client.export_session_string()
            await client.disconnect()
            remove_session(phone)
            return {"status": "success", "session": string_session}
        except Exception as e:
            error_msg = str(e)
            if "SESSION_PASSWORD_NEEDED" in error_msg:
                await client.disconnect()
                return {"status": "2fa_required"}
            else:
                await client.disconnect()
                return {"status": "error", "message": error_msg}

    return jsonify(run_async(process()))

@app.route('/verify_password', methods=['POST'])
def verify_password():
    phone = str(request.json.get('phone')).strip()
    password = str(request.json.get('password')).strip()
    
    async def process():
        session_name = get_session_name(phone)
        client = Client(
            name=session_name,
            api_id=int(API_ID),
            api_hash=API_HASH,
            workdir="/tmp"
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
