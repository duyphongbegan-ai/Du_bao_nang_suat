from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import joblib
import pandas as pd

app = FastAPI(title="Crop Yield Mobile API")

# Cấu hình CORS để Mobile App kết nối không bị chặn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Nạp mô hình và danh sách cột đã huấn luyện
model = joblib.load('crop_yield_knn_model.pkl')
columns = joblib.load('model_columns.pkl')

class CropInput(BaseModel):
    Area: str
    Item: str
    Year: int
    average_rain_fall_mm_per_year: float
    pesticides_tonnes: float
    avg_temp: float

@app.post("/predict")
def predict_yield(data: CropInput):
    # 1. Nhận dữ liệu và chuyển thành DataFrame
    df = pd.DataFrame([data.dict()])
    
    # 2. One-Hot Encoding và chuẩn hóa khớp 115 cột
    df_encoded = pd.get_dummies(df, columns=['Area', 'Item'])
    df_ready = df_encoded.reindex(columns=columns, fill_value=0)
    
    # 3. Dự đoán mức năng suất và tính xác suất
    pred = model.predict(df_ready)[0]
    prob = model.predict_proba(df_ready)[0]
    label_map = {0: "Thấp", 1: "Trung bình", 2: "Cao"}
    
    return {
        "status": "success",
        "predicted_label": label_map[pred],
        "probabilities": {
            "low": round(float(prob[0]) * 100, 1),
            "medium": round(float(prob[1]) * 100, 1),
            "high": round(float(prob[2]) * 100, 1)
        }
    }