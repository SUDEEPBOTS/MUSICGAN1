from flask import Flask, render_template, request, jsonify
from pyrogram import Client
import asyncio
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- RAM DATABASE ---
# Phone number ke sath API ID aur Hash bhi save karenge
TEMP_DB = {}

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def clean_phone(phone):
    return str(phone).replace('+', '').replace(' ', '').strip()

@app.route('/health', methods=['GET', 'HEAD'])
def health_check():
    return 'Alive', 200

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/send_otp', methods=['POST'])
def send_otp():
    data = request.json
    raw_phone = str(data.get('phone'))
    phone = clean_phone(raw_phone)
    
    # 1. API ID aur HASH user se lo
    raw_api_id = data.get('api_id')
    api_hash = data.get('api_hash')

    # 2. Validation & Integer Conversion (Ye hai main FIX)
    try:
        api_id = int(raw_api_id) # Zabardasti number banao
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "API ID must be a number (Integer)."})

    if not phone or not api_hash:
        return jsonify({"status": "error", "message": "All fields are required."})

    async def process():
        # Step 3: Client banao user ke credentials se
        client = Client(
            name="temp_sender", 
            api_id=api_id, 
            api_hash=api_hash, 
            in_memory=True
        )
        
        await client.connect()
        try:
            sent_code = await client.send_code(raw_phone)
            
            # 4. Session + Credentials RAM me save karo
            temp_session = await client.export_session_string()
            TEMP_DB[phone] = {
                "session": temp_session,
                "api_id": api_id,
                "api_hash": api_hash
            }
            
            await client.disconnect()
            return {"status": "success", "hash": sent_code.phone_code_hash}
        except Exception as e:
            await client.disconnect()
            return {"status": "error", "message": str(e)}

    return jsonify(run_async(process()))

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    data = request.json
    raw_phone = str(data.get('phone'))
    phone = clean_phone(raw_phone)
    code = str(data.get('code')).strip()
    hash_code = data.get('hash')
    
    # RAM check
    if phone not in TEMP_DB:
        return jsonify({"status": "error", "message": "Session Expired. Please Send OTP again."})

    user_data = TEMP_DB[phone]

    async def process():
        client = Client(
            name="temp_verifier", 
            api_id=user_data['api_id'],      # Saved API ID
            api_hash=user_data['api_hash'],  # Saved API Hash
            session_string=user_data['session'],
            in_memory=True
        )
        
        await client.connect()
        try:
            await client.sign_in(raw_phone, hash_code, code)
            final_string = await client.export_session_string()
            await client.disconnect()
            
            # Clear RAM
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
    data = request.json
    raw_phone = str(data.get('phone'))
    phone = clean_phone(raw_phone)
    password = str(data.get('password')).strip()
    
    if phone not in TEMP_DB:
        return jsonify({"status": "error", "message": "Session Expired."})

    user_data = TEMP_DB[phone]
    
    async def process():
        client = Client(
            name="temp_password", 
            api_id=user_data['api_id'],
            api_hash=user_data['api_hash'],
            session_string=user_data['session'],
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
    # Threaded=False aur Processes=1 jaruri hai RAM database ke liye
    app.run(debug=True)
