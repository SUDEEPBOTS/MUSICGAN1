from flask import Flask, render_template, request, jsonify
from pyrogram import Client
import asyncio
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- CONFIGURATION ---
API_ID = int(33917975) 
API_HASH = "9ded8160307386acef2451d464e7a9b9"

# --- RAM DATABASE (Global Dictionary) ---
# Yahan hum temporary session strings save karenge
TEMP_DB = {}

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# Phone number clean karne ka helper
def clean_phone_number(phone):
    return str(phone).replace('+', '').replace(' ', '').strip()

@app.route('/health', methods=['GET', 'HEAD'])
def health_check():
    return 'Alive', 200

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/send_otp', methods=['POST'])
def send_otp():
    raw_phone = str(request.json.get('phone'))
    phone = clean_phone_number(raw_phone)
    
    if not phone:
        return jsonify({"status": "error", "message": "Phone number required"})

    async def process():
        # Step 1: Memory me client banao
        client = Client(
            name="temp_sender", 
            api_id=API_ID, 
            api_hash=API_HASH, 
            in_memory=True # File nahi banegi
        )
        
        await client.connect()
        try:
            sent_code = await client.send_code(raw_phone)
            
            # CRITICAL: Session String export karke RAM me save karo
            # Ye 'Auth Key' hai, iske bina Telegram code reject kar dega
            temp_session = await client.export_session_string()
            TEMP_DB[phone] = temp_session
            
            await client.disconnect()
            print(f"✅ OTP Sent to {phone}. Session saved in RAM.")
            return {"status": "success", "hash": sent_code.phone_code_hash}
        except Exception as e:
            await client.disconnect()
            print(f"❌ Error sending OTP: {e}")
            return {"status": "error", "message": str(e)}

    return jsonify(run_async(process()))

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    raw_phone = str(request.json.get('phone'))
    phone = clean_phone_number(raw_phone)
    code = str(request.json.get('code')).strip()
    hash_code = request.json.get('hash')
    
    # Check karo RAM me session hai ya nahi
    if phone not in TEMP_DB:
        print(f"❌ Session missing for {phone}")
        return jsonify({"status": "error", "message": "Session Expired! Please Reload & Send OTP Again."})

    saved_session = TEMP_DB[phone]

    async def process():
        # Step 2: Wahi purana session use karo (Resume Connection)
        client = Client(
            name="temp_verifier", 
            api_id=API_ID, 
            api_hash=API_HASH, 
            session_string=saved_session, # RAM se load kiya
            in_memory=True
        )
        
        await client.connect()
        try:
            await client.sign_in(raw_phone, hash_code, code)
            
            # Login Success -> Final String Generate
            final_string = await client.export_session_string()
            await client.disconnect()
            
            # RAM clear karo
            del TEMP_DB[phone]
            return {"status": "success", "session": final_string}
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
    raw_phone = str(request.json.get('phone'))
    phone = clean_phone_number(raw_phone)
    password = str(request.json.get('password')).strip()
    
    if phone not in TEMP_DB:
        return jsonify({"status": "error", "message": "Session Expired."})

    saved_session = TEMP_DB[phone]
    
    async def process():
        client = Client(
            name="temp_password", 
            api_id=API_ID, 
            api_hash=API_HASH, 
            session_string=saved_session,
            in_memory=True
        )
        
        await client.connect()
        try:
            await client.check_password(password)
            final_string = await client.export_session_string()
            await client.disconnect()
            del TEMP_DB[phone]
            return {"status": "success", "session": final_string}
        except Exception as e:
            await client.disconnect()
            return {"status": "error", "message": str(e)}

    return jsonify(run_async(process()))

if __name__ == '__main__':
    app.run(debug=True)
