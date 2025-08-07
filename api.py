from fastapi import FastAPI, File, UploadFile, HTTPException
import shutil
import os
import subprocess
import json

app = FastAPI()

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Load extracted JSON data
def load_data():
    with open('combined.json', 'r', encoding='utf-8') as f:
        return json.load(f)

@app.get("/")
def root():
    return {"message": "Hello World"}

@app.post("/upload")
def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    save_path = os.path.join(UPLOAD_FOLDER, file.filename)

    # Save uploaded file
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Run your main parser on this file
    try:
        import main
        main.run_from_api(save_path)  # call your function that accepts a file path
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running parser: {str(e)}")

    return load_data()



    
