from flask import Flask, render_template, request, jsonify
from pyrogram import Client
from pymongo import MongoClient
from dotenv import load_dotenv
import asyncio
import os

# Local testing ke liye .env file load karega
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- CONFIGURATION FROM ENV ---
# Render ke "Environment Variables" section se ye value uthayega
MONGO_URL = os.getenv("MONGO_URL")

if not MONGO_URL:
    print("❌ ERROR: MONGO_URL environment variable nahi mila!")

# --- MONGODB CONNECTION ---
try:
    mongo_client = MongoClient(MONGO_URL)
    db = mongo_client["StringGenBot"]
    collection = db["temp_sessions"]
    print("✅ MongoDB Connected Successfully!")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")

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
    
    raw_api_id = data.get('api_id')
    api_hash = data.get('api_hash')

    # FIX: API ID ko Integer banao
    try:
        api_id = int(raw_api_id)
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "API ID must be a number."})

    if not phone or not api_hash:
        return jsonify({"status": "error", "message": "All fields are required."})

    async def process():
        client = Client(
            name="temp_sender", 
            api_id=api_id, 
            api_hash=api_hash, 
            in_memory=True
        )
        
        await client.connect()
        try:
            sent_code = await client.send_code(raw_phone)
            
            # --- SAVE TO MONGODB ---
            temp_session = await client.export_session_string()
            
            # Agar purana data hai to update karo, nahi to naya banao (upsert=True)
            user_data = {
                "phone": phone,
                "session": temp_session,
                "api_id": api_id,
                "api_hash": api_hash,
                "hash_code": sent_code.phone_code_hash
            }
            collection.update_one({"phone": phone}, {"$set": user_data}, upsert=True)
            
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
    
    # --- CHECK MONGODB ---
    user_data = collection.find_one({"phone": phone})
    
    if not user_data:
        return jsonify({"status": "error", "message": "Session Expired or Not Found."})

    async def process():
        client = Client(
            name="temp_verifier", 
            api_id=user_data['api_id'],      
            api_hash=user_data['api_hash'],  
            session_string=user_data['session'],
            in_memory=True
        )
        
        await client.connect()
        try:
            # MongoDB se saved hash use karo ya request wala
            hash_code = user_data.get('hash_code')
            await client.sign_in(raw_phone, hash_code, code)
            
            final_string = await client.export_session_string()
            await client.disconnect()
            
            # Success! Data delete kar do DB se
            collection.delete_one({"phone": phone})
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
    
    user_data = collection.find_one({"phone": phone})
    
    if not user_data:
        return jsonify({"status": "error", "message": "Session Expired."})
    
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
            
            # Success! Delete from DB
            collection.delete_one({"phone": phone})
            return {"status": "success", "session": final_string}
        except Exception as e:
            await client.disconnect()
            return {"status": "error", "message": str(e)}

    return jsonify(run_async(process()))

if __name__ == '__main__':
    app.run(debug=True)
