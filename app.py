from flask import Flask, render_template, request, jsonify
from pyrogram import Client
from pymongo import MongoClient
from dotenv import load_dotenv
import asyncio
import os

# Local testing ke liye
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- CONFIGURATION FROM ENV ---
MONGO_URL = os.getenv("MONGO_URL")

# --- MONGODB CONNECTION ---
try:
    if not MONGO_URL:
        print("❌ ERROR: MONGO_URL environment variable nahi mila!")
        collection = None
    else:
        mongo_client = MongoClient(MONGO_URL)
        db = mongo_client["StringGenBot"]
        collection = db["temp_sessions"]
        print("✅ MongoDB Connected Successfully!")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")
    collection = None

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
    if collection is None:
        return jsonify({"status": "error", "message": "Database Error: MONGO_URL missing."})

    data = request.json
    raw_phone = str(data.get('phone'))
    phone = clean_phone(raw_phone)
    
    raw_api_id = data.get('api_id') # Ye Text ho sakta hai
    api_hash = data.get('api_hash')

    # --- 🔥 MAIN FIX: Zabardasti Number (Integer) Banao ---
    try:
        api_id = int(raw_api_id) 
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "API ID galat hai. Sirf numbers allow hain."})

    if not phone or not api_hash:
        return jsonify({"status": "error", "message": "All fields are required."})

    async def process():
        # Client ko ab pakka 'int' wala api_id milega
        client = Client(
            name="temp_sender", 
            api_id=api_id, 
            api_hash=api_hash, 
            in_memory=True
        )
        
        await client.connect()
        try:
            sent_code = await client.send_code(raw_phone)
            
            # Save data to MongoDB
            temp_session = await client.export_session_string()
            
            user_data = {
                "phone": phone,
                "session": temp_session,
                "api_id": api_id,     # Saved as Number
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
    if collection is None:
        return jsonify({"status": "error", "message": "Database Error."})

    data = request.json
    raw_phone = str(data.get('phone'))
    phone = clean_phone(raw_phone)
    code = str(data.get('code')).strip()
    
    user_data = collection.find_one({"phone": phone})
    
    if not user_data:
        return jsonify({"status": "error", "message": "Session Expired. Dobara OTP bhejein."})

    # --- 🔥 FIX 2: Retrieval Safety ---
    # Agar DB se text wapas aaya, toh usko phir se Number banao
    try:
        saved_api_id = int(user_data['api_id']) 
    except:
        return jsonify({"status": "error", "message": "API ID corrupted. Retry process."})

    saved_api_hash = str(user_data['api_hash'])
    saved_session = str(user_data['session'])
    saved_hash_code = str(user_data['hash_code'])

    async def process():
        client = Client(
            name="temp_verifier", 
            api_id=saved_api_id,       # Integer Only
            api_hash=saved_api_hash,  
            session_string=saved_session,
            in_memory=True
        )
        
        await client.connect()
        try:
            await client.sign_in(raw_phone, saved_hash_code, code)
            
            final_string = await client.export_session_string()
            await client.disconnect()
            
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
    
    try:
        saved_api_id = int(user_data['api_id'])
    except:
        return jsonify({"status": "error", "message": "Corrupted Data."})

    async def process():
        client = Client(
            name="temp_password", 
            api_id=saved_api_id,
            api_hash=user_data['api_hash'],
            session_string=user_data['session'],
            in_memory=True
        )
        
        await client.connect()
        try:
            await client.check_password(password)
            final_string = await client.export_session_string()
            await client.disconnect()
            
            collection.delete_one({"phone": phone})
            return {"status": "success", "session": final_string}
        except Exception as e:
            await client.disconnect()
            return {"status": "error", "message": str(e)}

    return jsonify(run_async(process()))

if __name__ == '__main__':
    app.run(debug=True)
    
