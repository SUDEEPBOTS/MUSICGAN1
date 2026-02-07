from flask import Flask, render_template, request, jsonify
from pyrogram import Client
import asyncio
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- CONFIGURATION ---
API_ID = 33917975
API_HASH = "9ded8160307386acef2451d464e7a9b9"

# --- MEMORY STORAGE (Files ka jhanjhat khatam) ---
# Kyunki hum -w 1 use kar rahe hain, hum global variable use kar sakte hain.
# Ye data seedha RAM me rahega.
TEMP_SESSIONS = {}

# Helper to run async methods
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

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

    async def process():
        # Step 1: Naya session banao memory mein
        client = Client(
            name="temp_session", 
            api_id=API_ID, 
            api_hash=API_HASH, 
            in_memory=True  # Sab kuch RAM mein
        )
        
        await client.connect()
        try:
            sent_code = await client.send_code(phone)
            
            # CRITICAL: Abhi jo session (Auth Key) bana hai, usse save kar lo
            # Taaki verify karte waqt wahi same key use ho.
            session_string = await client.export_session_string()
            TEMP_SESSIONS[phone] = session_string
            
            await client.disconnect()
            return {"status": "success", "hash": sent_code.phone_code_hash}
        except Exception as e:
            await client.disconnect()
            return {"status": "error", "message": str(e)}

    return jsonify(run_async(process()))

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    phone = request.json.get('phone')
    code = request.json.get('code')
    hash_code = request.json.get('hash')
    
    # Check karo memory mein purana session hai ya nahi
    if phone not in TEMP_SESSIONS:
        return jsonify({"status": "error", "message": "Session not found. Please click 'Send OTP' again."})
    
    saved_session = TEMP_SESSIONS[phone]

    async def process():
        # Step 2: Wahi purana session string load karo (Resume Connection)
        client = Client(
            name="temp_session", 
            api_id=API_ID, 
            api_hash=API_HASH, 
            session_string=saved_session, # Resume from RAM
            in_memory=True
        )
        
        await client.connect()
        try:
            await client.sign_in(phone, hash_code, code)
            
            # Login Success! Final string generate karo
            final_string = await client.export_session_string()
            await client.disconnect()
            
            # Kaam ho gaya, memory clear kar do
            del TEMP_SESSIONS[phone]
            return {"status": "success", "session": final_string}
            
        except Exception as e:
            error_msg = str(e)
            if "SESSION_PASSWORD_NEEDED" in error_msg:
                await client.disconnect()
                # Password chahiye, abhi delete mat karo
                return {"status": "2fa_required"}
            else:
                await client.disconnect()
                # Delete mat karo, user wapas try karega (typo fix etc)
                return {"status": "error", "message": error_msg}

    return jsonify(run_async(process()))

@app.route('/verify_password', methods=['POST'])
def verify_password():
    phone = request.json.get('phone')
    password = request.json.get('password')
    
    if phone not in TEMP_SESSIONS:
        return jsonify({"status": "error", "message": "Session expired."})

    saved_session = TEMP_SESSIONS[phone]
    
    async def process():
        client = Client(
            name="temp_session", 
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
            del TEMP_SESSIONS[phone]
            return {"status": "success", "session": final_string}
        except Exception as e:
            await client.disconnect()
            return {"status": "error", "message": str(e)}

    return jsonify(run_async(process()))

if __name__ == '__main__':
    app.run(debug=True)
