import os
import io
import json
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
import google.generativeai as genai
from PIL import Image

app = FastAPI(title="Prism Logistics TMS Engine")

# CORS setup for Web Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment Configurations
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    ai_model = genai.GenerativeModel('gemini-1.5-flash')

@app.get("/")
def home():
    return {"message": "Prism Logistics TMS Backend Engine is Live!"}

# AI Receipt & Expense Scanner (OCR + Extraction)
@app.post("/api/expenses/scan-receipt")
async def scan_receipt(trip_id: str = Form(...), file: UploadFile = File(...)):
    try:
        if not GEMINI_API_KEY:
            raise HTTPException(status_code=500, detail="Gemini API Key missing")
            
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes))

        prompt = """
        Analyze this transport expense receipt/bill.
        Extract the following information in strict JSON format:
        {
            "expense_type": "Fuel" or "Toll" or "Maintenance" or "Driver Allowance" or "Other",
            "amount": float (total numeric amount paid),
            "liters": float (liters of fuel if applicable, else 0.0),
            "vendor_name": "string (name of fuel station or merchant)",
            "vehicle_number": "string (vehicle reg number if written on receipt, else null)",
            "date": "YYYY-MM-DD"
        }
        Do not add any markdown formatting or extra text outside the JSON.
        """

        response = ai_model.generate_content([prompt, image])
        clean_json_str = response.text.replace("```json", "").replace("```", "").strip()
        extracted_data = json.loads(clean_json_str)

        expense_record = {
            "trip_id": trip_id,
            "expense_type": extracted_data.get("expense_type", "Other"),
            "amount": extracted_data.get("amount", 0.0),
            "liters": extracted_data.get("liters", 0.0),
            "ai_extracted_data": extracted_data
        }

        db_response = supabase.table("expenses").insert(expense_record).execute()

        return {
            "status": "success",
            "message": "Receipt processed with AI Studio and saved successfully!",
            "extracted_data": extracted_data,
            "record": db_response.data
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Dashboard Stats Endpoint
@app.get("/api/dashboard/stats")
def get_dashboard_stats():
    try:
        vehicles = supabase.table("vehicles").select("*").execute()
        trips = supabase.table("trips").select("*").execute()
        
        total_vehicles = len(vehicles.data) if vehicles.data else 0
        active_trips = len([t for t in trips.data if t.get("status") == "In-Transit"]) if trips.data else 0
        
        return {
            "company": "Prism Logistics",
            "total_vehicles": total_vehicles,
            "active_trips": active_trips,
            "recent_trips": trips.data[:5] if trips.data else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))@app.post("/api/customers/add")
def add_customer(
    client_name: str = Form(...),
    phone: str = Form(...),
    billing_type: str = Form(...)
):
    row = [client_name, "", phone, "", billing_type, ""]
    worksheet = get_sheet_tab("Clients_Master")
    worksheet.append_row(row)
    return {"status": "Success", "message": "Customer added to Google Sheet!"}

@app.post("/api/vendors/add")
def add_vendor(
    vendor_name: str = Form(...),
    assigned_vehicle: str = Form(...),
    fuel_terms: str = Form(...)
):
    row = [vendor_name, "", assigned_vehicle, "Vendor Fleet", fuel_terms, ""]
    worksheet = get_sheet_tab("Vendors_Master")
    worksheet.append_row(row)
    return {"status": "Success", "message": "Vendor added to Google Sheet!"}
