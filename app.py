from flask import Flask, render_template, request, jsonify, session
from pyrogram import Client
import asyncio
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- CONFIGURATION (FIXED) ---
API_ID = 33917975  
API_HASH = "9ded8160307386acef2451d464e7a9b9"

# Helper to run async pyrogram methods in flask
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/send_otp', methods=['POST'])
def send_otp():
    phone_number = request.json.get('phone')
    
    async def process():
        client = Client(
            name="temp_session",
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True
        )
        await client.connect()
        try:
            sent_code = await client.send_code(phone_number)
            await client.disconnect()
            return {"status": "success", "hash": sent_code.phone_code_hash}
        except Exception as e:
            await client.disconnect()
            return {"status": "error", "message": str(e)}

    result = run_async(process())
    return jsonify(result)

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    phone = request.json.get('phone')
    code = request.json.get('code')
    hash_code = request.json.get('hash')
    
    async def process():
        client = Client(
            name="temp_session",
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True
        )
        await client.connect()
        try:
            await client.sign_in(phone, hash_code, code)
            string_session = await client.export_session_string()
            await client.disconnect()
            return {"status": "success", "session": string_session}
        except Exception as e:
            error_msg = str(e)
            if "SESSION_PASSWORD_NEEDED" in error_msg:
                await client.disconnect()
                return {"status": "2fa_required"}
            else:
                await client.disconnect()
                return {"status": "error", "message": error_msg}

    result = run_async(process())
    return jsonify(result)

@app.route('/verify_password', methods=['POST'])
def verify_password():
    phone = request.json.get('phone')
    code = request.json.get('code')
    hash_code = request.json.get('hash')
    password = request.json.get('password')
    
    async def process():
        client = Client(
            name="temp_session",
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True
        )
        await client.connect()
        try:
            # Login flow replay
            await client.sign_in(phone, hash_code, code)
        except Exception as e:
            if "SESSION_PASSWORD_NEEDED" in str(e):
                try:
                    await client.check_password(password)
                    string_session = await client.export_session_string()
                    await client.disconnect()
                    return {"status": "success", "session": string_session}
                except Exception as inner_e:
                    await client.disconnect()
                    return {"status": "error", "message": str(inner_e)}
            
            await client.disconnect()
            return {"status": "error", "message": str(e)}

    result = run_async(process())
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)
