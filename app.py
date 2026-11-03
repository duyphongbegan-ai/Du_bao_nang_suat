import streamlit as st
import requests
import pandas as pd
import os
from io import BytesIO
from datetime import datetime
import plotly.express as px

# Cấu hình trang Web
st.set_page_config(
    page_title="Cố vấn Năng suất Cây trồng AI",
    page_icon="🌾",
    layout="wide"
)

# Từ điển Việt hóa tên cây trồng (hiển thị song ngữ thân thiện với người dân)
ITEM_VI_MAP = {
    "Cassava": "Cassava (Sắn / Khoai mì)",
    "Maize": "Maize (Ngô / Bắp)",
    "Rice": "Rice (Lúa)",
    "Rice, paddy": "Rice, paddy (Lúa nước)",
    "Paddy_Rice": "Paddy_Rice (Lúa nước)",
    "Potatoes": "Potatoes (Khoai tây)",
    "Soybeans": "Soybeans (Đậu tương / Đậu nành)",
    "Sweet potatoes": "Sweet potatoes (Khoai lang)",
    "Sorghum": "Sorghum (Cao lương)",
    "Wheat": "Wheat (Lúa mì)",
    "Yams": "Yams (Khoai mỡ / Củ từ)",
    "Plantains and others": "Plantains (Chuối nấu)"
}

def get_item_display_name(item_code):
    return ITEM_VI_MAP.get(item_code, item_code)

st.title("🌾 Trợ Lý Nông Nghiệp Thông Minh")
st.markdown("Hệ thống dự báo năng suất cây trồng tích hợp AI, Đồng bộ Khí tượng Vệ tinh, Quét Cây trồng Thay thế & Ước tính Kinh tế Nông hộ.")
st.markdown("---")

# Khởi tạo Session State cho lịch sử và thông số thời tiết tự động
if 'history' not in st.session_state:
    st.session_state.history = []
if 'rain_val' not in st.session_state:
    st.session_state.rain_val = 1200.0
if 'temp_val' not in st.session_state:
    st.session_state.temp_val = 24.5
if 'weather_info' not in st.session_state:
    st.session_state.weather_info = None

# Thanh bên: Cho phép người dùng tự tải file dữ liệu CSV tùy chỉnh
st.sidebar.header("📁 Dữ liệu đầu vào")
uploaded_file = st.sidebar.file_uploader("Tải lên file CSV của bạn (Tùy chọn)", type=["csv"])

@st.cache_data
def load_dataset(uploaded_file):
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            return df
        except Exception as e:
            st.sidebar.error(f"Lỗi đọc file: {e}")
            return None
    else:
        csv_path = "yield_df.csv"
        if os.path.exists(csv_path):
            return pd.read_csv(csv_path)
        else:
            return None

df_raw = load_dataset(uploaded_file)

# Trích xuất danh sách Area và Item động từ dữ liệu
if df_raw is not None and not df_raw.empty:
    areas = sorted(df_raw['Area'].dropna().unique().tolist()) if 'Area' in df_raw.columns else ['Vietnam', 'India', 'Brazil']
    items = sorted(df_raw['Item'].dropna().unique().tolist()) if 'Item' in df_raw.columns else ['Cassava', 'Maize', 'Rice']
else:
    areas = ['Vietnam', 'India', 'Brazil']
    items = ['Cassava', 'Maize', 'Rice']

# Hàm chuyển đổi DataFrame sang file Excel (BytesIO) để tải về
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Bao_Cao_Nang_Suat')
    return output.getvalue()

# Hàm gọi API lấy dữ liệu khí hậu thực tế theo tên Khu vực (có cơ chế dự phòng an toàn khi mất mạng)
def fetch_real_weather(area_name):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={area_name}&count=1&language=en&format=json"
        geo_res = requests.get(geo_url, timeout=5).json()
        
        if "results" not in geo_res or len(geo_res["results"]) == 0:
            return True, {"name": area_name, "lat": 21.0, "lon": 105.8, "avg_temp": 25.0, "total_rain": 1500.0}
        
        location = geo_res["results"][0]
        lat = location["latitude"]
        lon = location["longitude"]
        resolved_name = location.get("name", area_name)
        
        weather_url = (
            f"https://archive-api.open-meteo.com/v1/archive?"
            f"latitude={lat}&longitude={lon}&start_date=2025-01-01&end_date=2025-12-31"
            f"&daily=temperature_2m_mean,precipitation_sum&timezone=auto"
        )
        weather_res = requests.get(weather_url, timeout=5).json()
        
        if "daily" not in weather_res:
            return True, {"name": resolved_name, "lat": lat, "lon": lon, "avg_temp": 25.0, "total_rain": 1500.0}
            
        temps = [t for t in weather_res["daily"]["temperature_2m_mean"] if t is not None]
        rains = [r for r in weather_res["daily"]["precipitation_sum"] if r is not None]
        
        avg_temp = round(sum(temps) / len(temps), 1) if temps else 24.5
        total_rain = round(sum(rains), 1) if rains else 1200.0
        
        return True, {
            "name": resolved_name,
            "lat": lat,
            "lon": lon,
            "avg_temp": avg_temp,
            "total_rain": total_rain
        }
    except Exception:
        return True, {
            "name": area_name,
            "lat": 21.0,
            "lon": 105.8,
            "avg_temp": 25.0,
            "total_rain": 1500.0
        }

# Hàm tự động quét các cây trồng khác để gợi ý chuyển đổi cơ cấu mùa vụ
def scan_alternative_crops(api_url, area, candidate_items, current_item, year, rain, pesticide, temp):
    recommendations = []
    for item_candidate in candidate_items:
        if item_candidate == current_item:
            continue
        payload = {
            "Area": area,
            "Item": item_candidate,
            "Year": int(year),
            "average_rain_fall_mm_per_year": float(rain),
            "pesticides_tonnes": float(pesticide),
            "avg_temp": float(temp)
        }
        try:
            res = requests.post(api_url, json=payload, timeout=3)
            if res.status_code == 200:
                data = res.json()
                pred_raw = str(data.get("predicted_label", "")).strip().lower()
                probs = data.get("probabilities", {})
                
                # Tìm xác suất mức Cao và Trung bình
                high_prob = 0.0
                med_prob = 0.0
                for k, v in probs.items():
                    k_low = str(k).strip().lower()
                    if k_low in ["high", "2", "cao"]:
                        high_prob = float(v)
                    elif k_low in ["medium", "1", "trung bình"]:
                        med_prob = float(v)
                
                if pred_raw in ["high", "2", "cao"]:
                    level_vi = "CAO"
                    priority = 2
                elif pred_raw in ["medium", "1", "trung bình"]:
                    level_vi = "TRUNG BÌNH"
                    priority = 1
                else:
                    level_vi = "THẤP"
                    priority = 0
                
                if priority > 0:
                    recommendations.append({
                        "Cây trồng đề xuất": get_item_display_name(item_candidate),
                        "Dự báo năng suất": level_vi,
                        "Xác suất mức Cao (%)": round(high_prob, 1),
                        "Xác suất mức TB (%)": round(med_prob, 1),
                        "_priority": priority,
                        "_score": high_prob * 100 + med_prob
                    })
        except Exception:
            continue
            
    recommendations.sort(key=lambda x: (x["_priority"], x["_score"]), reverse=True)
    return recommendations

# Form nhập liệu trên Sidebar (Thanh bên trái)
st.sidebar.header("⚙️ Thông số canh tác đầu vào")

selected_area = st.sidebar.selectbox("Khu vực canh tác (Area)", areas)

if st.sidebar.button("🌦️ Tự động lấy thời tiết khu vực"):
    with st.sidebar:
        with st.spinner(f"Đang quét vệ tinh thời tiết tại {selected_area}..."):
            success, data = fetch_real_weather(selected_area)
            if success:
                st.session_state.rain_val = float(data["total_rain"])
                st.session_state.temp_val = float(data["avg_temp"])
                st.session_state.weather_info = (
                    f"📍 **Tọa độ ({data['name']}):** {data['lat']}°N, {data['lon']}°E\n\n"
                    f"🌧️ **Tổng mưa năm:** {data['total_rain']} mm\n\n"
                    f"🌡️ **Nhiệt độ TB:** {data['avg_temp']} °C"
                )

if st.session_state.weather_info:
    st.sidebar.info(st.session_state.weather_info)

selected_item = st.sidebar.selectbox(
    "Loại cây trồng (Item)", 
    items,
    format_func=get_item_display_name
)
selected_item_display = get_item_display_name(selected_item)

year = st.sidebar.number_input("Năm canh tác (Year)", min_value=1990, max_value=2030, value=2026)

rain = st.sidebar.number_input(
    "Lượng mưa trung bình năm (mm)", 
    min_value=0.0, 
    step=50.0,
    key="rain_val"
)
pesticide = st.sidebar.number_input("Lượng thuốc BVTV (Tấn)", min_value=0.0, value=15000.0, step=500.0)
temp = st.sidebar.number_input(
    "Nhiệt độ trung bình (°C)", 
    min_value=-20.0, 
    max_value=60.0, 
    step=0.5,
    key="temp_val"
)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Thông số Kinh tế Nông hộ")
farm_area_ha = st.sidebar.number_input("Diện tích canh tác (Hecta - ha)", min_value=0.1, value=1.0, step=0.5)
crop_price_vnd = st.sidebar.number_input("Giá thu mua dự kiến (VNĐ/kg)", min_value=500, value=6000, step=500)

predict_btn = st.sidebar.button("🚀 Dự báo Năng suất ngay", type="primary")

# Tạo giao diện 4 Tab chức năng
tab_predict, tab_eda, tab_history, tab_info = st.tabs([
    "🎯 Dự báo & Tư vấn", 
    "📊 Phân tích Dữ liệu (EDA)", 
    "📜 Lịch sử & Xuất Excel", 
    "ℹ️ Thông tin Mô hình"
])

with tab_predict:
    if predict_btn:
        api_url = "http://localhost:8000/predict"
        
        payload = {
            "Area": selected_area,
            "Item": selected_item,
            "Year": int(year),
            "average_rain_fall_mm_per_year": float(rain),
            "pesticides_tonnes": float(pesticide),
            "avg_temp": float(temp)
        }
        
        try:
            with st.spinner("Đang gửi yêu cầu phân tích tới Server AI..."):
                response = requests.post(api_url, json=payload)
                
            if response.status_code == 200:
                result = response.json()
                predicted_label = result.get("predicted_label", "").lower()
                probabilities = result.get("probabilities", {})
                
                # Chuẩn hóa nhãn dự báo
                p_lower = str(predicted_label).strip().lower()
                is_low = p_lower in ["low", "0", "thấp"]
                is_medium = p_lower in ["medium", "1", "trung bình"]
                
                if is_low:
                    predicted_label_vi = "THẤP"
                    yield_multiplier = 0.75
                elif is_medium:
                    predicted_label_vi = "TRUNG BÌNH"
                    yield_multiplier = 1.0
                else:
                    predicted_label_vi = "CAO"
                    yield_multiplier = 1.25
                
                st.success("✅ Phân tích và dự báo thành công!")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric(label="🌍 Khu vực", value=selected_area)
                with col2:
                    st.metric(label="🌱 Cây trồng", value=selected_item_display)
                with col3:
                    st.metric(label="📊 Cấp độ năng suất", value=predicted_label_vi)
                
                # Tính toán ước tính sản lượng & doanh thu dựa trên dữ liệu lịch sử
                base_hg_ha = 150000.0
                if df_raw is not None and 'hg/ha_yield' in df_raw.columns:
                    df_sub = df_raw[(df_raw['Area'] == selected_area) & (df_raw['Item'] == selected_item)]
                    if not df_sub.empty:
                        base_hg_ha = float(df_sub['hg/ha_yield'].mean())
                    else:
                        df_item_only = df_raw[df_raw['Item'] == selected_item]
                        if not df_item_only.empty:
                            base_hg_ha = float(df_item_only['hg/ha_yield'].mean())
                
                # Quy đổi: 1 hg/ha = 0.1 kg/ha = 0.0001 tấn/ha (chia 10,000)
                est_ton_per_ha = (base_hg_ha / 10000.0) * yield_multiplier
                est_total_tons = est_ton_per_ha * farm_area_ha
                est_revenue_million = (est_total_tons * 1000.0 * crop_price_vnd) / 1_000_000.0
                
                st.markdown("### 💰 Ước tính Sản lượng & Hiệu quả Kinh tế Nông hộ:")
                ec1, ec2, ec3 = st.columns(3)
                ec1.metric("📦 Năng suất quy đổi dự kiến", f"{est_ton_per_ha:,.2f} tấn/ha")
                ec2.metric(f"🌾 Tổng sản lượng ({farm_area_ha} ha)", f"{est_total_tons:,.2f} tấn")
                ec3.metric("💵 Doanh thu ước tính", f"{est_revenue_million:,.1f} triệu VNĐ")
                
                st.markdown("### 📊 Biểu đồ trực quan độ tin cậy xác suất:")
                
                label_name_vi = {
                    "low": "Mức Thấp",
                    "0": "Mức Thấp",
                    "medium": "Mức Trung bình",
                    "1": "Mức Trung bình",
                    "high": "Mức Cao",
                    "2": "Mức Cao"
                }
                
                chart_labels = []
                chart_values = []
                for label_name, prob_value in probabilities.items():
                    name_vi = label_name_vi.get(str(label_name).strip().lower(), str(label_name).capitalize())
                    chart_labels.append(name_vi)
                    chart_values.append(prob_value)
                
                df_plotly = pd.DataFrame({
                    "Cấp độ năng suất": chart_labels,
                    "Xác suất (%)": chart_values
                })
                
                fig = px.bar(
                    df_plotly, 
                    x="Cấp độ năng suất", 
                    y="Xác suất (%)", 
                    text="Xác suất (%)",
                    color="Cấp độ năng suất",
                    color_discrete_map={"Mức Thấp": "#FF5733", "Mức Trung bình": "#FFC300", "Mức Cao": "#28B463"}
                )
                fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                fig.update_layout(uniformtext_minsize=8, uniformtext_mode='hide', showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("### 💡 Khuyến nghị, Tư vấn canh tác chuyên sâu & Chuyển đổi cơ cấu")
                
                if is_low:
                    recommendation = (
                        f"Cảnh báo năng suất thấp: Điều kiện khí tượng (Mưa: {rain}mm, Nhiệt độ: {temp}°C) "
                        f"hoặc vật tư nông nghiệp chưa tối ưu cho cây {selected_item_display} tại {selected_area}. "
                        "Cần điều chỉnh hệ thống tưới tiêu, cân đối dinh dưỡng đất và xem xét chuyển đổi giống cây."
                    )
                    st.warning(f"⚠️ **{recommendation}**")
                    
                    st.markdown(f"""
                    * **🔍 Phân tích nguyên nhân tiềm ẩn:**
                      * Lượng mưa trung bình năm (`{rain} mm`) hoặc nhiệt độ (`{temp} °C`) đang lệch khỏi biên độ sinh trưởng lý tưởng của giống cây **{selected_item_display}**.
                      * Lượng thuốc bảo vệ thực vật (`{pesticide} tấn`) chưa đáp ứng đủ hoặc bị lạm dụng gây suy thoái đất.
                    * **🛠️ Giải pháp kỹ thuật cấp bách:**
                      * **Quản lý nước:** Xây dựng hệ thống thoát nước chống úng hoặc bổ sung tưới nhỏ giọt nếu thiếu hụt nguồn nước.
                      * **Cải tạo đất:** Kiểm tra độ pH của đất tại `{selected_area}`, bổ sung phân hữu cơ vi sinh để khôi phục độ phì nhiêu.
                    """)
                    
                elif is_medium:
                    recommendation = (
                        f"Năng suất trung bình: Vụ mùa phát triển ổn định. "
                        f"Tuy nhiên với điều kiện tại {selected_area}, vẫn còn dư địa để tối ưu hóa sản lượng cho cây {selected_item_display}."
                    )
                    st.info(f"ℹ️ **{recommendation}**")
                    
                    st.markdown(f"""
                    * **📈 Đánh giá hiện trạng & Tối ưu chi phí:** 
                      * Các thông số môi trường (`{temp}°C`, `{rain}mm`) đang đáp ứng ở mức cơ bản. 
                      * **Khuyến nghị tối ưu vật tư:** Tránh lạm dụng phân bón hóa học quá mức. Nên áp dụng mô hình *Bón phân cân đối theo giai đoạn* để tiết kiệm từ 15-20% chi phí vật tư đầu vào mà vẫn giữ nguyên sản lượng.
                    """)
                    
                else:
                    recommendation = (
                        f"Năng suất cao: Tổ hợp thông số thời tiết và canh tác tại {selected_area} "
                        f"đang tạo ra môi trường sinh trưởng lý tưởng tuyệt đối cho cây {selected_item_display}!"
                    )
                    st.success(f"🌟 **{recommendation}**")
                    
                    st.markdown(f"""
                    * **🏆 Phân tích ưu thế & Phát triển bền vững:**
                      * Sự kết hợp hài hòa giữa nhiệt độ (`{temp}°C`), lượng mưa (`{rain}mm`) và lượng vật tư (`{pesticide} tấn`) giúp cây trồng đạt hiệu suất quang hợp tối đa.
                      * **Định hướng kinh tế địa phương:** Khuyến nghị nhân rộng mô hình canh tác này cho các hộ dân lân cận, đồng thời xây dựng chuỗi liên kết tiêu thụ nông sản sạch đạt chuẩn để nâng cao giá trị thương phẩm.
                    """)
                
                # Nếu năng suất Thấp hoặc Trung bình -> Tự động quét AI tìm cây trồng thay thế tốt hơn
                if is_low or is_medium:
                    st.markdown(f"#### 🔄 Đề xuất Chuyển đổi Cơ cấu Cây trồng Thông minh tại `{selected_area}`")
                    with st.spinner("Đang quét mô hình AI trên toàn bộ danh mục cây trồng để tìm giống thay thế tối ưu..."):
                        alt_crops = scan_alternative_crops(
                            api_url, selected_area, items, selected_item, year, rain, pesticide, temp
                        )
                    
                    if len(alt_crops) > 0:
                        st.write(
                            f"Với cùng điều kiện thời tiết hiện tại (`Mưa: {rain} mm`, `Nhiệt độ: {temp} °C`), "
                            f"hệ thống AI phát hiện **{len(alt_crops)} loại cây trồng khác** cho năng suất khả quan hơn **{selected_item_display}**:"
                        )
                        df_alt = pd.DataFrame(alt_crops).drop(columns=["_priority", "_score"])
                        st.dataframe(df_alt, use_container_width=True, hide_index=True)
                    else:
                        st.error(
                            f"Qua quét tự động, tất cả các cây trồng khác trong danh mục đều gặp rủi ro năng suất thấp dưới điều kiện khí hậu hiện tại (`{rain} mm`, `{temp} °C`). "
                            "Khuyến nghị bà con tập trung cải tạo hệ thống thủy lợi, nhà màng hoặc điều chỉnh lịch thời vụ trước khi xuống giống."
                        )
                
                timestamp = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
                current_record = {
                    "Thời gian": timestamp,
                    "Khu vực": selected_area,
                    "Cây trồng": selected_item_display,
                    "Năm": year,
                    "Diện tích (ha)": farm_area_ha,
                    "Lượng mưa (mm)": rain,
                    "Thuốc BVTV (Tấn)": pesticide,
                    "Nhiệt độ (°C)": temp,
                    "Kết quả dự báo": predicted_label_vi,
                    "Sản lượng dự kiến (Tấn)": round(est_total_tons, 2),
                    "Doanh thu ước tính (Triệu VNĐ)": round(est_revenue_million, 1),
                    "Khuyến nghị": recommendation
                }
                st.session_state.history.insert(0, current_record)
                
                df_single = pd.DataFrame([current_record])
                excel_single = convert_df_to_excel(df_single)
                st.download_button(
                    label="📥 Tải Phiếu Kết Quả & Hạch Toán Kinh Tế này (.xlsx)",
                    data=excel_single,
                    file_name=f"Bao_cao_{selected_area}_{selected_item}_{year}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                    
            else:
                st.error(f"Lỗi từ máy chủ FastAPI (Mã: {response.status_code})")
                
        except Exception as e:
            st.error(f"❌ Không thể kết nối tới Server FastAPI tại `{api_url}`.\nHãy chắc chắn rằng cửa sổ dòng lệnh chạy uvicorn vẫn đang mở!\n\nChi tiết lỗi: {e}")

    else:
        st.info("👈 Hãy chọn Khu vực, bấm **'Tự động lấy thời tiết khu vực'** (hoặc tự chỉnh thông số) rồi nhấn **'Dự báo Năng suất ngay'**.")

with tab_eda:
    st.subheader(f"📊 Phân tích Dữ liệu Lịch sử (EDA) - Khu vực: {selected_area}")
    if df_raw is not None and 'hg/ha_yield' in df_raw.columns:
        df_area = df_raw[df_raw['Area'] == selected_area]
        df_area_item = df_area[df_area['Item'] == selected_item]
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Tổng số bản ghi trong dữ liệu", f"{len(df_raw):,} mẫu")
        c2.metric(f"Số mẫu tại {selected_area}", f"{len(df_area):,} mẫu")
        avg_yield_val = df_area_item['hg/ha_yield'].mean() if not df_area_item.empty else 0
        c3.metric(f"Năng suất TB {selected_item_display}", f"{avg_yield_val:,.0f} hg/ha (~{avg_yield_val/10000:,.1f} tấn/ha)")
        
        st.markdown("---")
        col_eda1, col_eda2 = st.columns(2)
        
        with col_eda1:
            st.markdown(f"**1. Xu hướng năng suất `{selected_item_display}` tại `{selected_area}` qua các năm**")
            if not df_area_item.empty:
                df_trend = df_area_item.groupby('Year', as_index=False)['hg/ha_yield'].mean()
                fig_trend = px.line(
                    df_trend, x='Year', y='hg/ha_yield', markers=True,
                    labels={'Year': 'Năm', 'hg/ha_yield': 'Năng suất (hg/ha)'}
                )
                st.plotly_chart(fig_trend, use_container_width=True)
            else:
                st.warning(f"Không có dữ liệu lịch sử của cây {selected_item_display} tại {selected_area}.")
                
        with col_eda2:
            st.markdown(f"**2. So sánh năng suất trung bình các cây trồng tại `{selected_area}`**")
            if not df_area.empty:
                df_compare = df_area.groupby('Item', as_index=False)['hg/ha_yield'].mean().sort_values(by='hg/ha_yield', ascending=True)
                df_compare['Item_VI'] = df_compare['Item'].apply(get_item_display_name)
                fig_compare = px.bar(
                    df_compare, x='hg/ha_yield', y='Item_VI', orientation='h',
                    color='hg/ha_yield', color_continuous_scale='Viridis',
                    labels={'Item_VI': 'Loại cây trồng', 'hg/ha_yield': 'Năng suất TB (hg/ha)'}
                )
                st.plotly_chart(fig_compare, use_container_width=True)
            else:
                st.warning(f"Không có dữ liệu lịch sử tại {selected_area}.")
                
        st.markdown(f"**3. Tương quan giữa Lượng mưa, Nhiệt độ và Năng suất tại `{selected_area}`**")
        if not df_area.empty and 'average_rain_fall_mm_per_year' in df_area.columns:
            df_scatter_plot = df_area.copy()
            df_scatter_plot['Cây trồng'] = df_scatter_plot['Item'].apply(get_item_display_name)
            fig_scatter = px.scatter(
                df_scatter_plot, x='avg_temp', y='hg/ha_yield', color='Cây trồng',
                size='pesticides_tonnes' if 'pesticides_tonnes' in df_scatter_plot.columns else None,
                hover_data=['Year', 'average_rain_fall_mm_per_year'],
                labels={'avg_temp': 'Nhiệt độ TB (°C)', 'hg/ha_yield': 'Năng suất (hg/ha)', 'Cây trồng': 'Cây trồng'}
            )
            st.plotly_chart(fig_scatter, use_container_width=True)
    else:
        st.warning("⚠️ Không tìm thấy file dữ liệu hoặc thiếu cột `hg/ha_yield` để vẽ biểu đồ EDA.")

with tab_history:
    st.subheader("📜 Lịch sử các lần dự báo & Xuất báo cáo Excel")
    if len(st.session_state.history) > 0:
        df_history = pd.DataFrame(st.session_state.history)
        st.dataframe(df_history, use_container_width=True)
        
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            excel_all = convert_df_to_excel(df_history)
            st.download_button(
                label="📥 Xuất toàn bộ Lịch sử ra Excel (.xlsx)",
                data=excel_all,
                file_name=f"Lich_su_du_bao_nang_suat_{datetime.now().strftime('%d%m%Y_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
        with col_btn2:
            if st.button("🗑️ Xóa lịch sử"):
                st.session_state.history = []
                st.rerun()
    else:
        st.info("Chưa có lịch sử dự báo nào trong phiên làm việc này. Hãy thực hiện dự báo ở tab đầu tiên!")

with tab_info:
    st.subheader("ℹ️ Giới thiệu hệ thống đồ án")
    st.markdown("""
    - **Tên đề tài:** Nghiên cứu và ứng dụng mô hình học máy dự báo năng suất cây trồng.
    - **Công nghệ sử dụng:** 
      - **Backend:** FastAPI (Python) quản lý RESTful API và mô hình Machine Learning.
      - **Machine Learning:** Thuật toán K-Nearest Neighbors (KNN) huấn luyện dựa trên tập dữ liệu lịch sử nông nghiệp.
      - **Tích hợp Dữ liệu Thực tế:** Open-Meteo Geocoding & Historical Climate API tự động đồng bộ tổng lượng mưa và nhiệt độ trung bình theo tọa độ từng quốc gia.
      - **Tư vấn Chuyển đổi Cơ cấu & Kinh tế Nông hộ:** Tự động quét đa kịch bản tìm cây trồng thay thế tối ưu và hạch toán sản lượng, doanh thu dự kiến.
      - **Phân tích & Báo cáo:** Tích hợp Exploratory Data Analysis (EDA) và xuất báo cáo tự động ra file Microsoft Excel (`.xlsx`).
    """)