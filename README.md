# Tool Compare Batiment - PDF Comparison Tool

Công cụ so sánh PDF chuyên dụng cho tài liệu xây dựng (Batiment) với 3 chế độ so sánh khác nhau.

## 🚀 Features

### Mode 1: PAGES-2025 Comparison
- So sánh kích thước trang (page dimensions)
- Kiểm tra kích thước hình ảnh chính (main image size)
- Highlight các sai lệch

### Mode 2: PAGES-LaSolution-2026 với GPT AI
- Đọc popup annotations từ PDF reference
- Sử dụng GPT API để kiểm tra xem corrections đã được implement chưa
- Hiển thị kết quả chi tiết với status (✅/❌/⚠️/❓)
- Color-coded annotations trên PDF

### Mode 3: 0ASSEMBLAGE_PDF Text Comparison
- So sánh word-by-word
- Phát hiện text bị thiếu (🟠 orange)
- Phát hiện text thừa (🔵 blue)
- Merge nearby annotations để dễ đọc

## 📋 Requirements

- Python 3.12+
- Virtual environment (recommended)

## 🔧 Installation

1. **Clone hoặc navigate đến project directory:**
```bash
cd /home/hault/Tool_compare_Batiment
```

2. **Activate virtual environment:**
```bash
source venv/bin/activate
```

3. **Install dependencies:**
```bash
pip install -r requirements_full.txt
```

4. **Setup API Key (cho Mode 2):**
```bash
cp .env.example .env
# Edit .env và thêm OPENAI_API_KEY của bạn
```

## 🎯 Usage

### Run Streamlit App

```bash
source venv/bin/activate
streamlit run streamlit_app.py
```

Hoặc sử dụng script:
```bash
./run_streamlit.sh
```

### Run Desktop App (Tkinter)

```bash
source venv/bin/activate
python tool_compare_app.py
```

## 📖 How to Use

1. **Select Mode** trong sidebar (Mode 1, 2, hoặc 3)
2. **Upload 2 PDF files**:
   - Reference PDF (bên trái)
   - Final PDF (bên phải - cần kiểm tra)
3. **(Mode 2 only)** Configure OpenAI API key
4. Click **"Compare PDFs"**
5. Xem kết quả trong PDF viewer với annotations
6. Download annotated PDF nếu cần

## 🔑 API Key Setup (Mode 2)

### Option 1: Environment Variable (Recommended)

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Edit `.env` và thêm API key:
```
OPENAI_API_KEY=sk-your-actual-api-key-here
GPT_MODEL=gpt-4o-mini
```

3. **IMPORTANT**: Đảm bảo `.env` đã có trong `.gitignore`

### Option 2: Manual Input in UI

Nếu không có `.env` file, app sẽ hiển thị input field để nhập API key manually.

## 📁 Project Structure

```
Tool_compare_Batiment/
├── streamlit_app.py              # Web app (NEW - rebuilt)
├── streamlit_helpers.py          # Helper functions (NEW)
├── tool_compare_app.py           # Desktop app (Tkinter)
├── tool_compare_pages_2025.py    # Mode 1 logic
├── tool_compare_lasolution_2026.py # Mode 2 logic + GPT
├── tool_compare_assemblage.py    # Mode 3 logic
├── requirements_full.txt         # Dependencies (NEW)
├── .env.example                  # Environment template (NEW)
├── .gitignore                    # Git ignore file (NEW)
└── PDF-Diff-Viewer/              # External PDF viewer module
```

## 🔒 Security Notes

- ✅ API key bây giờ được load từ environment variables
- ✅ `.env` file đã được gitignored
- ⚠️ Không bao giờ commit API keys vào Git
- ⚠️ Revoke old API key nếu đã bị leak

## 💡 Tips

- **Mode 2 costs**: GPT API calls có chi phí. App hiển thị estimated cost trước khi chạy
- **PDF Viewer**: Annotations có thể được view trực tiếp trong app, không cần render images
- **Temp files**: App tự động cleanup temp files khi session kết thúc
- **Performance**: PDF viewer nhanh hơn nhiều so với image rendering

## 🐛 Troubleshooting

### PDF Viewer không hiển thị
```bash
pip install --upgrade streamlit-pdf-viewer
```

### OpenAI API Error
- Kiểm tra API key trong `.env`
- Verify key còn valid tại https://platform.openai.com/api-keys
- Đảm bảo có credits trong account

### PyMuPDF không load được
```bash
pip install --upgrade PyMuPDF
```

## 📝 Changelog

### v2.0 (Latest)
- ✅ Integrated Mode 1, Mode 2, Mode 3 vào Streamlit app
- ✅ Rebuilt PDF viewer using `streamlit-pdf-viewer`
- ✅ Fixed API key security (environment variables)
- ✅ Improved error handling
- ✅ Better UI/UX với metrics và progress bars
- ✅ Added temp file management

### v1.0 (Original)
- Basic Tkinter app
- Image-based PDF rendering
- Mode 3 only trong Streamlit

## 👨‍💻 Author

Tool developed for Batiment PDF comparison workflow.

## 📄 License

Internal use only.
